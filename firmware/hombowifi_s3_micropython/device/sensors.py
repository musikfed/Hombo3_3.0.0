# EN: Three HC-SR04 sensors are sampled sequentially to reduce acoustic crosstalk.
# RU: Три HC-SR04 опрашиваются по очереди, чтобы уменьшить акустические взаимные помехи.
import asyncio
import time
from machine import Pin, I2C
from board_config import *

class Ultrasonic:
    def __init__(self, trig, echo):
        self.trig=Pin(trig,Pin.OUT,value=0)
        self.echo=Pin(echo,Pin.IN)
    def cm(self):
        self.trig.value(0); time.sleep_us(3); self.trig.value(1); time.sleep_us(10); self.trig.value(0)
        try: duration=time_pulse(self.echo)
        except Exception: return 0
        return duration//58 if duration and duration>0 else 0

def time_pulse(pin):
    try:
        from machine import time_pulse_us
        return time_pulse_us(pin,1,25000)
    except Exception:
        return -1

class Sensors:
    def __init__(self):
        self.front=Ultrasonic(PIN_HC_FRONT_TRIG,PIN_HC_FRONT_ECHO)
        self.rear=Ultrasonic(PIN_HC_REAR_TRIG,PIN_HC_REAR_ECHO)
        self.third=Ultrasonic(PIN_HC_THIRD_TRIG,PIN_HC_THIRD_ECHO)
        self.front_cm=self.rear_cm=self.third_cm=0
        self.tof_mm=0; self.tof_ok=False; self.active_sensor_slot=255
        self.i2c=I2C(0,sda=Pin(PIN_I2C_SDA),scl=Pin(PIN_I2C_SCL),freq=400000)
        self.tof=None
        try:
            from vl53l0x import VL53L0X
            self.tof=VL53L0X(self.i2c)
        except Exception as exc:
            print("VL53L0X optional driver unavailable:",exc)

    def _read_tof(self):
        if self.tof is None:
            self.tof_ok=False; self.tof_mm=0; return
        try:
            # EN: Common MicroPython VL53L0X drivers expose .range.
            # RU: Большинство MicroPython-драйверов VL53L0X предоставляют свойство .range.
            value=self.tof.range
            if callable(value): value=value()
            self.tof_mm=int(value); self.tof_ok=self.tof_mm>0
        except Exception:
            self.tof_ok=False; self.tof_mm=0

    async def loop(self):
        slot=0
        while True:
            self.active_sensor_slot=slot
            if slot==0: self.front_cm=self.front.cm()
            elif slot==1: self.rear_cm=self.rear.cm()
            elif slot==2: self.third_cm=self.third.cm()
            else: self._read_tof()
            slot=(slot+1)%4
            await asyncio.sleep_ms(SENSOR_SLOT_MS)
