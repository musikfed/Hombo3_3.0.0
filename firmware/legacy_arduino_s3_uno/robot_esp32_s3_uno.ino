/*
  Robot ESP32-S3 UNO firmware
  ---------------------------------
  Confirmed hardware only:
    - ESP32-S3 UNO N16R8
    - 2x TB6612FNG, four TT motors
    - 3x HC-SR04
    - 1x VL53L0X GY-530
    - 1x MAX98357A + speaker
    - REGGO IP camera is NOT connected to ESP32 GPIO; it works over Wi-Fi/ONVIF.

  Network API exposed by ESP32:
    GET  /api/status
    GET  /api/telemetry
    POST /api/command   JSON: {"left":-100..100,"right":-100..100,"ttl_ms":1000,"seq":1}
    POST /api/stop
    POST /api/test/pwm JSON: {"left_pwm":-255..255,"right_pwm":-255..255,"sensor_safety":true,"ttl_ms":1500,"seq":1}
    GET/POST /api/tuning  runtime ramp + distance STOP thresholds pushed by Acer

  Audio:
    TCP port 3333 accepts raw signed 16-bit mono PCM, 16000 Hz, little-endian.
    The Acer Python application opens the TCP connection, sends a 12-byte header:
      bytes 0..3   = ASCII "PCM1"
      bytes 4..7   = uint32 sample rate, little-endian
      bytes 8..11  = uint32 payload byte count, little-endian
    Then it sends the PCM payload. The ESP32 streams it to MAX98357A through I2S.

  Safety rules:
    - local watchdog stops motors when commands expire;
    - ultrasonic/ToF emergency stop works locally in normal/assembled test mode;
    - raw PWM calibration endpoint can explicitly disable only distance-sensor blocking for bench tests;
    - LLM never talks directly to motor pins.

  Arduino core target: ESP32 Arduino Core 3.x.
  Required external library: Adafruit VL53L0X.
*/

#include <Arduino.h>
#include <WiFi.h>
#include <WebServer.h>
#include <Wire.h>
#include <ArduinoJson.h>
#include <ESP_I2S.h>
#include <Adafruit_VL53L0X.h>

// -------------------------- User settings --------------------------
// Keep private Wi-Fi credentials in secrets.h (not in the release archive).
// Copy secrets.h.example to secrets.h and fill in your local values.
#if __has_include("secrets.h")
#include "secrets.h"
#endif
#ifndef ROBOT_WIFI_SSID
#define ROBOT_WIFI_SSID "PFtochka"
#endif
#ifndef ROBOT_WIFI_PASSWORD
#define ROBOT_WIFI_PASSWORD "1234q1234a"
#endif
const char* WIFI_SSID = ROBOT_WIFI_SSID;
const char* WIFI_PASSWORD = ROBOT_WIFI_PASSWORD;

// Optional static IP. Leave USE_STATIC_IP=false for DHCP during first tests.
const bool USE_STATIC_IP = false;
IPAddress LOCAL_IP(192, 168, 1, 90);
IPAddress GATEWAY(192, 168, 1, 1);
IPAddress SUBNET(255, 255, 255, 0);
IPAddress DNS1(192, 168, 1, 1);

// -------------------------- Confirmed GPIO map --------------------------
// IMPORTANT CHASSIS TOPOLOGY: ONE TB6612 BOARD = ONE PHYSICAL SIDE.
// Left TB6612 drives FL + BL. Right TB6612 drives FR + BR.
// Within EACH board, channels A and B receive the same logical side command:
//   LEFT:  GPIO18 -> AIN1+BIN1, GPIO17 -> AIN2+BIN2, GPIO14 -> PWMA+PWMB
//   RIGHT: GPIO21 -> AIN1+BIN1, GPIO10 -> AIN2+BIN2, GPIO12 -> PWMA+PWMB
// STBY GPIO40 goes to STBY on both boards.
// This uses six motion GPIOs while keeping the two H-bridges on each board electrically separate at the motor outputs.
constexpr uint8_t PIN_LEFT_IN1 = 18;
constexpr uint8_t PIN_LEFT_IN2 = 17;
constexpr uint8_t PIN_LEFT_PWM = 14;
constexpr uint8_t PIN_RIGHT_IN1 = 21;
constexpr uint8_t PIN_RIGHT_IN2 = 10;
constexpr uint8_t PIN_RIGHT_PWM = 12;
constexpr uint8_t PIN_STBY = 40;

// HC-SR04 GPIO map. Sensor modules are powered from the confirmed 5V rail.
constexpr uint8_t PIN_HC_FRONT_TRIG = 1;
constexpr uint8_t PIN_HC_FRONT_ECHO = 7;
constexpr uint8_t PIN_HC_REAR_TRIG  = 6;
constexpr uint8_t PIN_HC_REAR_ECHO  = 5;
constexpr uint8_t PIN_HC_THIRD_TRIG = 4;
constexpr uint8_t PIN_HC_THIRD_ECHO = 16;

// I2C for VL53L0X.
constexpr uint8_t PIN_I2C_SDA = 8;
constexpr uint8_t PIN_I2C_SCL = 9;

// MAX98357A I2S.
constexpr uint8_t PIN_I2S_BCLK = 11;
constexpr uint8_t PIN_I2S_LRCK = 13;
constexpr uint8_t PIN_I2S_DOUT = 15;  // Hombo3: GPIO2 reserved for battery ADC1

// -------------------------- Motion tuning --------------------------
// Start conservatively. Raise only after mechanical tests.
constexpr int PWM_FREQUENCY_HZ = 16000;
constexpr int PWM_RESOLUTION_BITS = 8;
constexpr int PWM_MAX = 255;
constexpr int DRIVE_PWM_LIMIT = PWM_MAX;  // full 8-bit range for calibration: 0..255
constexpr int DRIVE_DEADBAND_PERCENT = 8;
constexpr int DEFAULT_RAMP_STEP_PWM = 2;
constexpr uint32_t DEFAULT_RAMP_PERIOD_MS = 20;
constexpr uint32_t DEFAULT_COMMAND_TTL_MS = 1000;

// Safe defaults. Acer may update these at runtime from a named tuning profile.
constexpr uint16_t DEFAULT_FRONT_STOP_CM = 18;
constexpr uint16_t DEFAULT_REAR_STOP_CM = 15;
constexpr uint16_t DEFAULT_TOF_STOP_MM = 150;

// Sensor scheduling: HC-SR04 modules are triggered one at a time to avoid crosstalk.
constexpr uint32_t SENSOR_SLOT_MS = 70;
constexpr uint32_t TELEMETRY_CACHE_MS = 50;

WebServer httpServer(80);
WiFiServer audioServer(3333);
I2SClass i2s;
Adafruit_VL53L0X tof;

struct MotionState {
  int targetLeftPercent = 0;
  int targetRightPercent = 0;
  int targetLeftRawPwm = 0;
  int targetRightRawPwm = 0;
  bool rawPwmMode = false;
  bool sensorSafetyEnabled = true;
  int currentLeftPwm = 0;
  int currentRightPwm = 0;
  uint32_t lastCommandMs = 0;
  uint32_t ttlMs = DEFAULT_COMMAND_TTL_MS;
  uint32_t lastSeq = 0;
  bool emergencyStop = false;
  char lastStopReason[64] = "boot";
};

struct RuntimeTuning {
  int rampStepPwm = DEFAULT_RAMP_STEP_PWM;
  uint32_t rampPeriodMs = DEFAULT_RAMP_PERIOD_MS;
  uint16_t frontStopCm = DEFAULT_FRONT_STOP_CM;
  uint16_t rearStopCm = DEFAULT_REAR_STOP_CM;
  uint16_t tofStopMm = DEFAULT_TOF_STOP_MM;
};

struct TelemetryState {
  uint16_t frontCm = 0;
  uint16_t rearCm = 0;
  uint16_t thirdCm = 0;
  uint16_t tofMm = 0;
  bool tofOk = false;
  int8_t wifiRssi = -127;
  uint32_t uptimeMs = 0;
  uint32_t commandAgeMs = 0;
  bool commandExpired = true;
};

MotionState motion;
RuntimeTuning runtimeTuning;
TelemetryState telemetry;
uint32_t lastRampMs = 0;
uint32_t lastSensorSlotMs = 0;
uint8_t sensorSlot = 0;
uint32_t lastTelemetryBuildMs = 0;
bool tofPresent = false;
bool audioActive = false;
uint8_t activeSensorSlot = 255;

// -------------------------- Helpers --------------------------
int percentToPwm(int percent) {
  percent = constrain(percent, -100, 100);
  if (abs(percent) < DRIVE_DEADBAND_PERCENT) return 0;
  const int magnitude = map(abs(percent), DRIVE_DEADBAND_PERCENT, 100, 0, DRIVE_PWM_LIMIT);
  return percent < 0 ? -magnitude : magnitude;
}

int approachValue(int current, int target, int step) {
  if (current < target) return min(current + step, target);
  if (current > target) return max(current - step, target);
  return current;
}

void setMotorChannel(uint8_t in1, uint8_t in2, uint8_t pwmPin, int signedPwm) {
  signedPwm = constrain(signedPwm, -PWM_MAX, PWM_MAX);
  if (signedPwm > 0) {
    digitalWrite(in1, HIGH);
    digitalWrite(in2, LOW);
    ledcWrite(pwmPin, signedPwm);
  } else if (signedPwm < 0) {
    digitalWrite(in1, LOW);
    digitalWrite(in2, HIGH);
    ledcWrite(pwmPin, -signedPwm);
  } else {
    ledcWrite(pwmPin, 0);
    digitalWrite(in1, LOW);
    digitalWrite(in2, LOW);
  }
}

void applyMotorOutputs() {
  setMotorChannel(PIN_LEFT_IN1, PIN_LEFT_IN2, PIN_LEFT_PWM, motion.currentLeftPwm);
  setMotorChannel(PIN_RIGHT_IN1, PIN_RIGHT_IN2, PIN_RIGHT_PWM, motion.currentRightPwm);
}

void hardStop(const char* reason) {
  strlcpy(motion.lastStopReason, reason, sizeof(motion.lastStopReason));
  motion.targetLeftPercent = 0;
  motion.targetRightPercent = 0;
  motion.targetLeftRawPwm = 0;
  motion.targetRightRawPwm = 0;
  motion.rawPwmMode = false;
  motion.currentLeftPwm = 0;
  motion.currentRightPwm = 0;
  applyMotorOutputs();
  Serial.printf("STOP: %s\n", reason);
}

uint16_t readUltrasonicCm(uint8_t trigPin, uint8_t echoPin) {
  digitalWrite(trigPin, LOW);
  delayMicroseconds(3);
  digitalWrite(trigPin, HIGH);
  delayMicroseconds(10);
  digitalWrite(trigPin, LOW);

  // 25 ms corresponds to roughly 4.3 m. Zero means timeout/no echo.
  const uint32_t durationUs = pulseIn(echoPin, HIGH, 25000UL);
  if (durationUs == 0) return 0;
  return static_cast<uint16_t>(durationUs / 58UL);
}

void updateOneSensorSlot() {
  const uint32_t now = millis();
  if (now - lastSensorSlotMs < SENSOR_SLOT_MS) return;
  lastSensorSlotMs = now;

  activeSensorSlot = sensorSlot;
  switch (sensorSlot) {
    case 0:
      telemetry.frontCm = readUltrasonicCm(PIN_HC_FRONT_TRIG, PIN_HC_FRONT_ECHO);
      break;
    case 1:
      telemetry.rearCm = readUltrasonicCm(PIN_HC_REAR_TRIG, PIN_HC_REAR_ECHO);
      break;
    case 2:
      telemetry.thirdCm = readUltrasonicCm(PIN_HC_THIRD_TRIG, PIN_HC_THIRD_ECHO);
      break;
    case 3:
      if (tofPresent) {
        VL53L0X_RangingMeasurementData_t measurement;
        tof.rangingTest(&measurement, false);
        if (measurement.RangeStatus != 4) {
          telemetry.tofMm = measurement.RangeMilliMeter;
          telemetry.tofOk = true;
        } else {
          telemetry.tofOk = false;
          telemetry.tofMm = 0;
        }
      }
      break;
  }
  sensorSlot = (sensorSlot + 1) % 4;
}

bool movingForward() {
  return motion.currentLeftPwm > 0 || motion.currentRightPwm > 0;
}

bool movingBackward() {
  return motion.currentLeftPwm < 0 || motion.currentRightPwm < 0;
}

void updateSafety() {
  const uint32_t now = millis();
  telemetry.commandAgeMs = now - motion.lastCommandMs;
  telemetry.commandExpired = telemetry.commandAgeMs > motion.ttlMs;

  const bool hasMotionTarget = motion.rawPwmMode
    ? (motion.targetLeftRawPwm != 0 || motion.targetRightRawPwm != 0)
    : (motion.targetLeftPercent != 0 || motion.targetRightPercent != 0);

  if (telemetry.commandExpired && hasMotionTarget) {
    hardStop("command TTL expired");
  }

  if (motion.sensorSafetyEnabled) {
    bool obstacle = false;
    if (movingForward()) {
      if (telemetry.frontCm > 0 && telemetry.frontCm <= runtimeTuning.frontStopCm) obstacle = true;
      if (telemetry.tofOk && telemetry.tofMm > 0 && telemetry.tofMm <= runtimeTuning.tofStopMm) obstacle = true;
    }
    if (movingBackward()) {
      if (telemetry.rearCm > 0 && telemetry.rearCm <= runtimeTuning.rearStopCm) obstacle = true;
    }

    if (obstacle) {
      motion.emergencyStop = true;
      hardStop("local obstacle safety");
    }
  }
}

void updateMotionRamp() {
  const uint32_t now = millis();
  if (now - lastRampMs < runtimeTuning.rampPeriodMs) return;
  lastRampMs = now;

  const int targetLeftPwm = motion.rawPwmMode
    ? constrain(motion.targetLeftRawPwm, -PWM_MAX, PWM_MAX)
    : percentToPwm(motion.targetLeftPercent);
  const int targetRightPwm = motion.rawPwmMode
    ? constrain(motion.targetRightRawPwm, -PWM_MAX, PWM_MAX)
    : percentToPwm(motion.targetRightPercent);
  motion.currentLeftPwm = approachValue(motion.currentLeftPwm, targetLeftPwm, runtimeTuning.rampStepPwm);
  motion.currentRightPwm = approachValue(motion.currentRightPwm, targetRightPwm, runtimeTuning.rampStepPwm);
  applyMotorOutputs();
}

const char* directionName(int pwm) {
  if (pwm > 0) return "forward";
  if (pwm < 0) return "reverse";
  return "stopped";
}

String makeTelemetryJson() {
  StaticJsonDocument<1280> doc;
  telemetry.wifiRssi = WiFi.isConnected() ? WiFi.RSSI() : -127;
  telemetry.uptimeMs = millis();

  doc["ok"] = true;
  doc["ip"] = WiFi.localIP().toString();
  doc["wifi_rssi"] = telemetry.wifiRssi;
  doc["uptime_ms"] = telemetry.uptimeMs;
  doc["front_cm"] = telemetry.frontCm;
  doc["rear_cm"] = telemetry.rearCm;
  doc["third_cm"] = telemetry.thirdCm;
  doc["tof_mm"] = telemetry.tofMm;
  doc["tof_ok"] = telemetry.tofOk;
  doc["target_left_percent"] = motion.targetLeftPercent;
  doc["target_right_percent"] = motion.targetRightPercent;
  doc["current_left_pwm"] = motion.currentLeftPwm;
  doc["current_right_pwm"] = motion.currentRightPwm;
  doc["pwm_limit"] = PWM_MAX;
  doc["raw_pwm_mode"] = motion.rawPwmMode;
  doc["sensor_safety_enabled"] = motion.sensorSafetyEnabled;
  doc["ramp_step_pwm"] = runtimeTuning.rampStepPwm;
  doc["ramp_period_ms"] = runtimeTuning.rampPeriodMs;
  doc["front_stop_cm"] = runtimeTuning.frontStopCm;
  doc["rear_stop_cm"] = runtimeTuning.rearStopCm;
  doc["tof_stop_mm"] = runtimeTuning.tofStopMm;
  doc["target_left_raw_pwm"] = motion.targetLeftRawPwm;
  doc["target_right_raw_pwm"] = motion.targetRightRawPwm;
  doc["left_direction"] = directionName(motion.currentLeftPwm);
  doc["right_direction"] = directionName(motion.currentRightPwm);
  // Side-oriented names are the canonical telemetry contract in v1.2.
  doc["left_in1"] = motion.currentLeftPwm > 0;
  doc["left_in2"] = motion.currentLeftPwm < 0;
  doc["right_in1"] = motion.currentRightPwm > 0;
  doc["right_in2"] = motion.currentRightPwm < 0;
  doc["left_pwm"] = abs(motion.currentLeftPwm);
  doc["right_pwm"] = abs(motion.currentRightPwm);
  // Backward-compatible aliases for old v0.4/v1.1 dashboards.
  doc["ain1"] = doc["left_in1"];
  doc["ain2"] = doc["left_in2"];
  doc["bin1"] = doc["right_in1"];
  doc["bin2"] = doc["right_in2"];
  doc["pwma"] = doc["left_pwm"];
  doc["pwmb"] = doc["right_pwm"];
  doc["stby"] = digitalRead(PIN_STBY) == HIGH;
  doc["audio_active"] = audioActive;
  doc["active_sensor_slot"] = activeSensorSlot;
  doc["last_stop_reason"] = motion.lastStopReason;
  doc["command_age_ms"] = telemetry.commandAgeMs;
  doc["command_expired"] = telemetry.commandExpired;
  doc["emergency_stop"] = motion.emergencyStop;
  doc["last_seq"] = motion.lastSeq;

  String json;
  serializeJson(doc, json);
  return json;
}

void sendJson(int code, const String& json) {
  httpServer.sendHeader("Cache-Control", "no-store");
  httpServer.send(code, "application/json; charset=utf-8", json);
}

void handleStatus() {
  sendJson(200, makeTelemetryJson());
}

void handleCommand() {
  if (!httpServer.hasArg("plain")) {
    sendJson(400, "{\"ok\":false,\"error\":\"missing JSON body\"}");
    return;
  }

  StaticJsonDocument<512> input;
  const DeserializationError error = deserializeJson(input, httpServer.arg("plain"));
  if (error) {
    sendJson(400, "{\"ok\":false,\"error\":\"invalid JSON\"}");
    return;
  }

  const int left = input["left"] | 0;
  const int right = input["right"] | 0;
  const uint32_t ttlMs = input["ttl_ms"] | DEFAULT_COMMAND_TTL_MS;
  const uint32_t seq = input["seq"] | (motion.lastSeq + 1);

  if (left < -100 || left > 100 || right < -100 || right > 100) {
    sendJson(422, "{\"ok\":false,\"error\":\"left/right must be -100..100\"}");
    return;
  }

  motion.rawPwmMode = false;
  motion.sensorSafetyEnabled = true;
  motion.targetLeftRawPwm = 0;
  motion.targetRightRawPwm = 0;
  motion.targetLeftPercent = left;
  motion.targetRightPercent = right;
  motion.ttlMs = constrain(ttlMs, 100UL, 5000UL);
  motion.lastCommandMs = millis();
  motion.lastSeq = seq;
  motion.emergencyStop = false;

  StaticJsonDocument<256> output;
  output["ok"] = true;
  output["seq"] = seq;
  output["accepted_left"] = left;
  output["accepted_right"] = right;
  String json;
  serializeJson(output, json);
  sendJson(200, json);
}

void handlePwmTest() {
  if (!httpServer.hasArg("plain")) {
    sendJson(400, "{\"ok\":false,\"error\":\"missing JSON body\"}");
    return;
  }

  StaticJsonDocument<512> input;
  const DeserializationError error = deserializeJson(input, httpServer.arg("plain"));
  if (error) {
    sendJson(400, "{\"ok\":false,\"error\":\"invalid JSON\"}");
    return;
  }

  const int leftPwm = input["left_pwm"] | 0;
  const int rightPwm = input["right_pwm"] | 0;
  const bool sensorSafety = input["sensor_safety"] | true;
  const uint32_t ttlMs = input["ttl_ms"] | 1500UL;
  const uint32_t seq = input["seq"] | (motion.lastSeq + 1);

  if (leftPwm < -PWM_MAX || leftPwm > PWM_MAX || rightPwm < -PWM_MAX || rightPwm > PWM_MAX) {
    sendJson(422, "{\"ok\":false,\"error\":\"left_pwm/right_pwm must be -255..255\"}");
    return;
  }

  motion.rawPwmMode = true;
  motion.sensorSafetyEnabled = sensorSafety;
  motion.targetLeftPercent = 0;
  motion.targetRightPercent = 0;
  motion.targetLeftRawPwm = leftPwm;
  motion.targetRightRawPwm = rightPwm;
  motion.ttlMs = constrain(ttlMs, 100UL, 5000UL);
  motion.lastCommandMs = millis();
  motion.lastSeq = seq;
  motion.emergencyStop = false;

  StaticJsonDocument<320> output;
  output["ok"] = true;
  output["seq"] = seq;
  output["accepted_left_pwm"] = leftPwm;
  output["accepted_right_pwm"] = rightPwm;
  output["sensor_safety_enabled"] = sensorSafety;
  output["mode"] = "raw_pwm_test";
  String json;
  serializeJson(output, json);
  sendJson(200, json);
}

void sendTuningJson() {
  StaticJsonDocument<320> output;
  output["ok"] = true;
  output["ramp_step_pwm"] = runtimeTuning.rampStepPwm;
  output["ramp_period_ms"] = runtimeTuning.rampPeriodMs;
  output["front_stop_cm"] = runtimeTuning.frontStopCm;
  output["rear_stop_cm"] = runtimeTuning.rearStopCm;
  output["tof_stop_mm"] = runtimeTuning.tofStopMm;
  String json;
  serializeJson(output, json);
  sendJson(200, json);
}

void handleTuningGet() {
  sendTuningJson();
}

void handleTuningPost() {
  if (!httpServer.hasArg("plain")) {
    sendJson(400, "{\"ok\":false,\"error\":\"missing JSON body\"}");
    return;
  }
  StaticJsonDocument<384> input;
  const DeserializationError error = deserializeJson(input, httpServer.arg("plain"));
  if (error) {
    sendJson(400, "{\"ok\":false,\"error\":\"invalid JSON\"}");
    return;
  }

  if (input.containsKey("ramp_step_pwm")) {
    runtimeTuning.rampStepPwm = constrain(static_cast<int>(input["ramp_step_pwm"]), 1, 64);
  }
  if (input.containsKey("ramp_period_ms")) {
    runtimeTuning.rampPeriodMs = constrain(static_cast<uint32_t>(input["ramp_period_ms"]), 5UL, 250UL);
  }
  if (input.containsKey("front_stop_cm")) {
    runtimeTuning.frontStopCm = constrain(static_cast<uint16_t>(input["front_stop_cm"]), static_cast<uint16_t>(2), static_cast<uint16_t>(400));
  }
  if (input.containsKey("rear_stop_cm")) {
    runtimeTuning.rearStopCm = constrain(static_cast<uint16_t>(input["rear_stop_cm"]), static_cast<uint16_t>(2), static_cast<uint16_t>(400));
  }
  if (input.containsKey("tof_stop_mm")) {
    runtimeTuning.tofStopMm = constrain(static_cast<uint16_t>(input["tof_stop_mm"]), static_cast<uint16_t>(20), static_cast<uint16_t>(4000));
  }
  sendTuningJson();
}

void handleStop() {
  hardStop("remote stop endpoint");
  motion.sensorSafetyEnabled = true;
  motion.lastCommandMs = millis();
  motion.emergencyStop = false;
  sendJson(200, "{\"ok\":true,\"stopped\":true}");
}

void handleNotFound() {
  sendJson(404, "{\"ok\":false,\"error\":\"not found\"}");
}

uint32_t readUint32LE(const uint8_t* p) {
  return static_cast<uint32_t>(p[0]) |
         (static_cast<uint32_t>(p[1]) << 8) |
         (static_cast<uint32_t>(p[2]) << 16) |
         (static_cast<uint32_t>(p[3]) << 24);
}

bool readExact(WiFiClient& client, uint8_t* buffer, size_t size, uint32_t timeoutMs) {
  size_t total = 0;
  const uint32_t started = millis();
  while (total < size && millis() - started < timeoutMs) {
    const int available = client.available();
    if (available > 0) {
      const int n = client.read(buffer + total, size - total);
      if (n > 0) total += static_cast<size_t>(n);
    } else {
      delay(1);
    }
  }
  return total == size;
}

void handleAudioClient() {
  WiFiClient client = audioServer.available();
  if (!client) return;

  uint8_t header[12];
  if (!readExact(client, header, sizeof(header), 3000)) {
    client.stop();
    return;
  }
  if (memcmp(header, "PCM1", 4) != 0) {
    client.stop();
    return;
  }

  const uint32_t sampleRate = readUint32LE(header + 4);
  uint32_t remaining = readUint32LE(header + 8);
  if (sampleRate < 8000 || sampleRate > 48000 || remaining > 8UL * 1024UL * 1024UL) {
    client.stop();
    return;
  }

  i2s.configureTX(sampleRate, I2S_DATA_BIT_WIDTH_16BIT, I2S_SLOT_MODE_MONO);
  audioActive = true;
  uint8_t buffer[1024];
  while (remaining > 0 && client.connected()) {
    const size_t wanted = min(static_cast<uint32_t>(sizeof(buffer)), remaining);
    const int n = client.read(buffer, wanted);
    if (n > 0) {
      i2s.write(buffer, static_cast<size_t>(n));
      remaining -= static_cast<uint32_t>(n);
    } else {
      delay(1);
    }
    // Keep HTTP commands, sensors and motor safety alive while speech plays.
    httpServer.handleClient();
    updateOneSensorSlot();
    updateSafety();
    updateMotionRamp();
  }
  audioActive = false;
  client.stop();
}

void connectWiFi() {
  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false);
  if (USE_STATIC_IP) WiFi.config(LOCAL_IP, GATEWAY, SUBNET, DNS1);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  Serial.print("Connecting Wi-Fi");
  const uint32_t started = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - started < 20000) {
    delay(300);
    Serial.print('.');
  }
  Serial.println();
  if (WiFi.status() == WL_CONNECTED) {
    Serial.printf("Wi-Fi OK, IP: %s\n", WiFi.localIP().toString().c_str());
  } else {
    Serial.println("Wi-Fi connection timeout. Firmware keeps retrying in loop.");
  }
}

void setupPins() {
  // Keep both drivers disabled until direction pins and PWM channels are initialized.
  pinMode(PIN_STBY, OUTPUT);
  digitalWrite(PIN_STBY, LOW);

  pinMode(PIN_LEFT_IN1, OUTPUT);
  pinMode(PIN_LEFT_IN2, OUTPUT);
  pinMode(PIN_RIGHT_IN1, OUTPUT);
  pinMode(PIN_RIGHT_IN2, OUTPUT);

  ledcAttach(PIN_LEFT_PWM, PWM_FREQUENCY_HZ, PWM_RESOLUTION_BITS);
  ledcAttach(PIN_RIGHT_PWM, PWM_FREQUENCY_HZ, PWM_RESOLUTION_BITS);
  hardStop("boot");
  digitalWrite(PIN_STBY, HIGH);

  pinMode(PIN_HC_FRONT_TRIG, OUTPUT);
  pinMode(PIN_HC_FRONT_ECHO, INPUT);
  pinMode(PIN_HC_REAR_TRIG, OUTPUT);
  pinMode(PIN_HC_REAR_ECHO, INPUT);
  pinMode(PIN_HC_THIRD_TRIG, OUTPUT);
  pinMode(PIN_HC_THIRD_ECHO, INPUT);
}

void setup() {
  Serial.begin(115200);
  delay(500);
  Serial.println("Robot ESP32-S3 UNO starting");

  setupPins();
  Wire.begin(PIN_I2C_SDA, PIN_I2C_SCL);
  tofPresent = tof.begin(0x29, false, &Wire);
  Serial.printf("VL53L0X: %s\n", tofPresent ? "OK" : "not detected");

  i2s.setPins(PIN_I2S_BCLK, PIN_I2S_LRCK, PIN_I2S_DOUT);
  if (!i2s.begin(I2S_MODE_STD, 16000, I2S_DATA_BIT_WIDTH_16BIT, I2S_SLOT_MODE_MONO)) {
    Serial.println("I2S begin failed");
  }

  connectWiFi();

  httpServer.on("/api/status", HTTP_GET, handleStatus);
  httpServer.on("/api/telemetry", HTTP_GET, handleStatus);
  httpServer.on("/api/command", HTTP_POST, handleCommand);
  httpServer.on("/api/test/pwm", HTTP_POST, handlePwmTest);
  httpServer.on("/api/tuning", HTTP_GET, handleTuningGet);
  httpServer.on("/api/tuning", HTTP_POST, handleTuningPost);
  httpServer.on("/api/stop", HTTP_POST, handleStop);
  httpServer.onNotFound(handleNotFound);
  httpServer.begin();
  audioServer.begin();

  motion.lastCommandMs = millis();
  Serial.println("HTTP API: port 80, raw PCM audio: port 3333");
}

void loop() {
  if (WiFi.status() != WL_CONNECTED) {
    static uint32_t lastReconnectMs = 0;
    if (millis() - lastReconnectMs > 5000) {
      lastReconnectMs = millis();
      WiFi.reconnect();
    }
  }

  httpServer.handleClient();
  handleAudioClient();
  updateOneSensorSlot();
  updateSafety();
  updateMotionRamp();
  delay(1);
}
