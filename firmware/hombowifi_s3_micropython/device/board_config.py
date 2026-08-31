# EN: Hombo3 hardware baseline for ESP32-S3-DevKitC-1 N16R8.
# RU: Зафиксированная аппаратная конфигурация Hombo3 для ESP32-S3-DevKitC-1 N16R8.
PROJECT_NAME = "hombo3"
RUNTIME_VERSION = "3.0.0"
BOARD_NAME = "ESP32-S3-DevKitC-1 N16R8"
BOARD_FAMILY = "ESP32-S3"
FLASH_MB = 16
PSRAM_MB = 8
PSRAM_MODE = "octal"

# ---------------------------------------------------------------------------
# Drive: two TB6612 boards, one physical side per driver.
# TB6612-L: A+B control inputs are paralleled -> FL + BL.
# TB6612-R: A+B control inputs are paralleled -> FR + BR.
# ---------------------------------------------------------------------------
PIN_LEFT_IN1 = 18
PIN_LEFT_IN2 = 17
PIN_LEFT_PWM = 14
PIN_RIGHT_IN1 = 21
PIN_RIGHT_IN2 = 10
PIN_RIGHT_PWM = 12
PIN_STBY = 40

# Three HC-SR04. Every ECHO MUST pass through its own 5V -> 3.3V divider.
PIN_HC_FRONT_TRIG = 1
PIN_HC_FRONT_ECHO = 7
PIN_HC_REAR_TRIG = 6
PIN_HC_REAR_ECHO = 5
PIN_HC_THIRD_TRIG = 4
PIN_HC_THIRD_ECHO = 16

# Shared I2C for VL53L0X and possible future current/voltage monitor.
PIN_I2C_SDA = 8
PIN_I2C_SCL = 9

# MAX98357A. DOUT was deliberately moved from GPIO2 to GPIO15 in Hombo3.
# GPIO2 is ADC1_CH1 and is reserved for battery measurement while Wi-Fi is active.
PIN_I2S_BCLK = 11
PIN_I2S_LRCK = 13
PIN_I2S_DOUT = 15

# Battery: confirmed project baseline is a 2S2P Li-ion pack (8.4V max).
# Divider: battery+ -> 2k + 1k (top, 3k total) -> ADC node -> 1k -> GND.
# Ratio = (3k + 1k) / 1k = 4.0. At 8.4V the ADC sees about 2.10V.
# GPIO2 is ADC1_CH1: unlike ADC2 it remains usable while Wi-Fi is active and it is
# not a strapping pin on ESP32-S3.
PIN_BATTERY_ADC = 2
BATTERY_CELLS = 2
BATTERY_DIVIDER_RATIO = 4.0
BATTERY_CALIBRATION = 1.0
BATTERY_LOW_PERCENT = 25
BATTERY_RETURN_PERCENT = 15
BATTERY_CRITICAL_PERCENT = 8

HTTP_PORT = 80
AUDIO_PORT = 3333
DISCOVERY_PORT = 32320

PWM_FREQUENCY_HZ = 16000
PWM_MAX = 255
DRIVE_DEADBAND_PERCENT = 8
DEFAULT_RAMP_STEP_PWM = 2
DEFAULT_RAMP_PERIOD_MS = 20
DEFAULT_COMMAND_TTL_MS = 1000
DEFAULT_FRONT_STOP_CM = 18
DEFAULT_REAR_STOP_CM = 15
DEFAULT_TOF_STOP_MM = 150
SENSOR_SLOT_MS = 70
