# EN: Local motor controller. Safety and TTL remain on the ESP32.
# RU: Локальный контроллер моторов. Безопасность и TTL остаются на ESP32.
import asyncio
import time
from machine import Pin, PWM
from board_config import *

class MotionController:
    def __init__(self):
        self.stby = Pin(PIN_STBY, Pin.OUT, value=0)
        self.left_in1 = Pin(PIN_LEFT_IN1, Pin.OUT, value=0)
        self.left_in2 = Pin(PIN_LEFT_IN2, Pin.OUT, value=0)
        self.right_in1 = Pin(PIN_RIGHT_IN1, Pin.OUT, value=0)
        self.right_in2 = Pin(PIN_RIGHT_IN2, Pin.OUT, value=0)
        self.left_pwm = PWM(Pin(PIN_LEFT_PWM), freq=PWM_FREQUENCY_HZ, duty_u16=0)
        self.right_pwm = PWM(Pin(PIN_RIGHT_PWM), freq=PWM_FREQUENCY_HZ, duty_u16=0)
        self.target_left_percent = 0
        self.target_right_percent = 0
        self.target_left_raw_pwm = 0
        self.target_right_raw_pwm = 0
        self.raw_pwm_mode = False
        self.sensor_safety_enabled = True
        self.current_left_pwm = 0
        self.current_right_pwm = 0
        self.last_command_ms = time.ticks_ms()
        self.ttl_ms = DEFAULT_COMMAND_TTL_MS
        self.last_seq = 0
        self.emergency_stop = False
        self.last_stop_reason = "boot"
        self.ramp_step_pwm = DEFAULT_RAMP_STEP_PWM
        self.ramp_period_ms = DEFAULT_RAMP_PERIOD_MS
        self.runtime_max_pwm = PWM_MAX
        self.front_stop_cm = DEFAULT_FRONT_STOP_CM
        self.rear_stop_cm = DEFAULT_REAR_STOP_CM
        self.tof_stop_mm = DEFAULT_TOF_STOP_MM
        self.stby.value(1)

    def _duty(self, value):
        return max(0, min(65535, abs(int(value)) * 257))

    def _set_channel(self, in1, in2, pwm, signed_pwm):
        signed_pwm = max(-PWM_MAX, min(PWM_MAX, int(signed_pwm)))
        if signed_pwm > 0:
            in1.value(1); in2.value(0); pwm.duty_u16(self._duty(signed_pwm))
        elif signed_pwm < 0:
            in1.value(0); in2.value(1); pwm.duty_u16(self._duty(signed_pwm))
        else:
            pwm.duty_u16(0); in1.value(0); in2.value(0)

    def apply_outputs(self):
        self._set_channel(self.left_in1, self.left_in2, self.left_pwm, self.current_left_pwm)
        self._set_channel(self.right_in1, self.right_in2, self.right_pwm, self.current_right_pwm)

    def hard_stop(self, reason, emergency=None):
        self.last_stop_reason = str(reason)[:63]
        self.target_left_percent = self.target_right_percent = 0
        self.target_left_raw_pwm = self.target_right_raw_pwm = 0
        self.raw_pwm_mode = False
        self.current_left_pwm = self.current_right_pwm = 0
        if emergency is not None:
            self.emergency_stop = bool(emergency)
        self.apply_outputs()

    def command(self, left, right, ttl_ms, seq):
        if not (-100 <= left <= 100 and -100 <= right <= 100):
            raise ValueError("left/right must be -100..100")
        self.raw_pwm_mode = False
        self.sensor_safety_enabled = True
        self.target_left_raw_pwm = self.target_right_raw_pwm = 0
        self.target_left_percent = int(left)
        self.target_right_percent = int(right)
        self.ttl_ms = max(100, min(5000, int(ttl_ms)))
        self.last_command_ms = time.ticks_ms()
        self.last_seq = int(seq)
        self.emergency_stop = False

    def pwm_test(self, left_pwm, right_pwm, sensor_safety, ttl_ms, seq):
        if not (-PWM_MAX <= left_pwm <= PWM_MAX and -PWM_MAX <= right_pwm <= PWM_MAX):
            raise ValueError("left_pwm/right_pwm must be -255..255")
        self.raw_pwm_mode = True
        self.sensor_safety_enabled = bool(sensor_safety)
        self.target_left_percent = self.target_right_percent = 0
        self.target_left_raw_pwm = int(left_pwm)
        self.target_right_raw_pwm = int(right_pwm)
        self.ttl_ms = max(100, min(5000, int(ttl_ms)))
        self.last_command_ms = time.ticks_ms()
        self.last_seq = int(seq)
        self.emergency_stop = False

    def apply_tuning(self, data):
        if "ramp_step_pwm" in data: self.ramp_step_pwm=max(1,min(64,int(data["ramp_step_pwm"])))
        if "ramp_period_ms" in data: self.ramp_period_ms=max(5,min(250,int(data["ramp_period_ms"])))
        if "max_pwm" in data: self.runtime_max_pwm=max(1,min(PWM_MAX,int(data["max_pwm"])))
        if "front_stop_cm" in data: self.front_stop_cm=max(2,min(400,int(data["front_stop_cm"])))
        if "rear_stop_cm" in data: self.rear_stop_cm=max(2,min(400,int(data["rear_stop_cm"])))
        if "tof_stop_mm" in data: self.tof_stop_mm=max(20,min(4000,int(data["tof_stop_mm"])))
        if "sensor_safety_default" in data: self.sensor_safety_enabled=bool(data["sensor_safety_default"])

    def tuning(self):
        return {"ok":True,"ramp_step_pwm":self.ramp_step_pwm,"ramp_period_ms":self.ramp_period_ms,
                "max_pwm":self.runtime_max_pwm,"front_stop_cm":self.front_stop_cm,"rear_stop_cm":self.rear_stop_cm,
                "tof_stop_mm":self.tof_stop_mm,"sensor_safety_enabled":self.sensor_safety_enabled}

    def _percent_to_pwm(self, percent):
        percent=max(-100,min(100,int(percent)))
        if abs(percent) < DRIVE_DEADBAND_PERCENT: return 0
        magnitude=(abs(percent)-DRIVE_DEADBAND_PERCENT)*self.runtime_max_pwm//(100-DRIVE_DEADBAND_PERCENT)
        return -magnitude if percent < 0 else magnitude

    @staticmethod
    def _approach(current, target, step):
        if current < target: return min(current+step,target)
        if current > target: return max(current-step,target)
        return current

    def command_age_ms(self):
        return time.ticks_diff(time.ticks_ms(), self.last_command_ms)

    def update_safety(self, sensors):
        age=self.command_age_ms()
        has_target=(self.target_left_raw_pwm or self.target_right_raw_pwm) if self.raw_pwm_mode else (self.target_left_percent or self.target_right_percent)
        if age > self.ttl_ms and has_target:
            self.hard_stop("command TTL expired", emergency=False)
        if not self.sensor_safety_enabled: return
        moving_forward=self.current_left_pwm>0 or self.current_right_pwm>0
        moving_backward=self.current_left_pwm<0 or self.current_right_pwm<0
        obstacle=False
        if moving_forward:
            if 0 < sensors.front_cm <= self.front_stop_cm: obstacle=True
            if sensors.tof_ok and 0 < sensors.tof_mm <= self.tof_stop_mm: obstacle=True
        if moving_backward and 0 < sensors.rear_cm <= self.rear_stop_cm: obstacle=True
        if obstacle:
            self.hard_stop("local obstacle safety", emergency=True)

    async def loop(self, sensors):
        while True:
            self.update_safety(sensors)
            left=max(-PWM_MAX,min(PWM_MAX,self.target_left_raw_pwm)) if self.raw_pwm_mode else self._percent_to_pwm(self.target_left_percent)
            right=max(-PWM_MAX,min(PWM_MAX,self.target_right_raw_pwm)) if self.raw_pwm_mode else self._percent_to_pwm(self.target_right_percent)
            self.current_left_pwm=self._approach(self.current_left_pwm,left,self.ramp_step_pwm)
            self.current_right_pwm=self._approach(self.current_right_pwm,right,self.ramp_step_pwm)
            self.apply_outputs()
            await asyncio.sleep_ms(self.ramp_period_ms)
