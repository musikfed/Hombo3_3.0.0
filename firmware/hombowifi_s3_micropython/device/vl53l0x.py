# Hombo3 VL53L0X MicroPython driver.
# EN: Self-contained single-sensor driver for the ST VL53L0X used by Hombo3.
# RU: Самодостаточный драйвер одного VL53L0X для MicroPython/Hombo3.
#
# The implementation follows the public VL53L0X register interface and the
# conventional ST/Pololu initialization flow. It is intentionally small: one
# sensor at the default I2C address, single-shot ranging, bounded timeouts.
import time

_ADDR = 0x29
_SYSRANGE_START = 0x00
_SYSTEM_SEQUENCE_CONFIG = 0x01
_SYSTEM_INTERRUPT_CONFIG_GPIO = 0x0A
_SYSTEM_INTERRUPT_CLEAR = 0x0B
_RESULT_INTERRUPT_STATUS = 0x13
_RESULT_RANGE_STATUS = 0x14
_GPIO_HV_MUX_ACTIVE_HIGH = 0x84
_FINAL_RANGE_CONFIG_MIN_COUNT_RATE_RTN_LIMIT = 0x44
_GLOBAL_CONFIG_SPAD_ENABLES_REF_0 = 0xB0
_DYNAMIC_SPAD_NUM_REQUESTED_REF_SPAD = 0x4E
_DYNAMIC_SPAD_REF_EN_START_OFFSET = 0x4F
_GLOBAL_CONFIG_REF_EN_START_SELECT = 0xB6

# Register tuning settings used by ST's standard initialization profile.
# These are register/value facts, not executable vendor code.
_TUNING = (
    (0xFF,0x01),(0x00,0x00),(0xFF,0x00),(0x09,0x00),(0x10,0x00),(0x11,0x00),
    (0x24,0x01),(0x25,0xFF),(0x75,0x00),(0xFF,0x01),(0x4E,0x2C),(0x48,0x00),
    (0x30,0x20),(0xFF,0x00),(0x30,0x09),(0x54,0x00),(0x31,0x04),(0x32,0x03),
    (0x40,0x83),(0x46,0x25),(0x60,0x00),(0x27,0x00),(0x50,0x06),(0x51,0x00),
    (0x52,0x96),(0x56,0x08),(0x57,0x30),(0x61,0x00),(0x62,0x00),(0x64,0x00),
    (0x65,0x00),(0x66,0xA0),(0xFF,0x01),(0x22,0x32),(0x47,0x14),(0x49,0xFF),
    (0x4A,0x00),(0xFF,0x00),(0x7A,0x0A),(0x7B,0x00),(0x78,0x21),(0xFF,0x01),
    (0x23,0x34),(0x42,0x00),(0x44,0xFF),(0x45,0x26),(0x46,0x05),(0x40,0x40),
    (0x0E,0x06),(0x20,0x1A),(0x43,0x40),(0xFF,0x00),(0x34,0x03),(0x35,0x44),
    (0xFF,0x01),(0x31,0x04),(0x4B,0x09),(0x4C,0x05),(0x4D,0x04),(0xFF,0x00),
    (0x44,0x00),(0x45,0x20),(0x47,0x08),(0x48,0x28),(0x67,0x00),(0x70,0x04),
    (0x71,0x01),(0x72,0xFE),(0x76,0x00),(0x77,0x00),(0xFF,0x01),(0x0D,0x01),
    (0xFF,0x00),(0x80,0x01),(0x01,0xF8),(0xFF,0x01),(0x8E,0x01),(0x00,0x01),
    (0xFF,0x00),(0x80,0x00),
)

class VL53L0X:
    def __init__(self, i2c, address=_ADDR, io_timeout_ms=500):
        self.i2c=i2c
        self.address=int(address)
        self.io_timeout_ms=int(io_timeout_ms)
        self._stop_variable=0
        self._init()

    def _w8(self, reg, val):
        self.i2c.writeto_mem(self.address, reg, bytes((val & 0xFF,)))

    def _r8(self, reg):
        return self.i2c.readfrom_mem(self.address, reg, 1)[0]

    def _w16(self, reg, val):
        self.i2c.writeto_mem(self.address, reg, bytes(((val >> 8) & 0xFF, val & 0xFF)))

    def _r16(self, reg):
        b=self.i2c.readfrom_mem(self.address, reg, 2)
        return (b[0] << 8) | b[1]

    def _read(self, reg, n):
        return bytearray(self.i2c.readfrom_mem(self.address, reg, n))

    def _write(self, reg, data):
        self.i2c.writeto_mem(self.address, reg, bytes(data))

    def _wait(self, predicate, message):
        start=time.ticks_ms()
        while not predicate():
            if self.io_timeout_ms > 0 and time.ticks_diff(time.ticks_ms(), start) >= self.io_timeout_ms:
                raise OSError(message)
            time.sleep_ms(1)

    def _spad_info(self):
        self._w8(0x80,0x01); self._w8(0xFF,0x01); self._w8(0x00,0x00)
        self._w8(0xFF,0x06); self._w8(0x83,self._r8(0x83)|0x04); self._w8(0xFF,0x07)
        self._w8(0x81,0x01); self._w8(0x80,0x01); self._w8(0x94,0x6B); self._w8(0x83,0x00)
        self._wait(lambda: self._r8(0x83) != 0x00, 'VL53L0X SPAD timeout')
        self._w8(0x83,0x01)
        tmp=self._r8(0x92)
        count=tmp & 0x7F; aperture=bool(tmp & 0x80)
        self._w8(0x81,0x00); self._w8(0xFF,0x06); self._w8(0x83,self._r8(0x83)&~0x04)
        self._w8(0xFF,0x01); self._w8(0x00,0x01); self._w8(0xFF,0x00); self._w8(0x80,0x00)
        return count, aperture

    def _ref_cal(self, vhv):
        self._w8(_SYSRANGE_START, 0x01 | vhv)
        self._wait(lambda: (self._r8(_RESULT_INTERRUPT_STATUS) & 0x07) != 0, 'VL53L0X calibration timeout')
        self._w8(_SYSTEM_INTERRUPT_CLEAR,0x01); self._w8(_SYSRANGE_START,0x00)

    def _init(self):
        # Product ID sanity check. 0xEE/0xAA/0x10 is the standard VL53L0X signature.
        sig=(self._r8(0xC0),self._r8(0xC1),self._r8(0xC2))
        if sig != (0xEE,0xAA,0x10):
            raise OSError('VL53L0X not found at 0x29; ID=%s' % (str(sig),))
        self._w8(0x88,0x00)
        self._w8(0x80,0x01); self._w8(0xFF,0x01); self._w8(0x00,0x00)
        self._stop_variable=self._r8(0x91)
        self._w8(0x00,0x01); self._w8(0xFF,0x00); self._w8(0x80,0x00)
        self._w8(0x60, self._r8(0x60) | 0x12)
        self.set_signal_rate_limit(0.25)
        self._w8(_SYSTEM_SEQUENCE_CONFIG,0xFF)
        count, aperture=self._spad_info()
        spads=self._read(_GLOBAL_CONFIG_SPAD_ENABLES_REF_0,6)
        self._w8(0xFF,0x01); self._w8(_DYNAMIC_SPAD_REF_EN_START_OFFSET,0x00)
        self._w8(_DYNAMIC_SPAD_NUM_REQUESTED_REF_SPAD,0x2C); self._w8(0xFF,0x00)
        self._w8(_GLOBAL_CONFIG_REF_EN_START_SELECT,0xB4)
        first=12 if aperture else 0; enabled=0
        for i in range(48):
            byte=i//8; bit=1 << (i%8)
            if i < first or enabled >= count:
                spads[byte] &= ~bit
            elif spads[byte] & bit:
                enabled += 1
        self._write(_GLOBAL_CONFIG_SPAD_ENABLES_REF_0,spads)
        for reg,val in _TUNING: self._w8(reg,val)
        self._w8(_SYSTEM_INTERRUPT_CONFIG_GPIO,0x04)
        self._w8(_GPIO_HV_MUX_ACTIVE_HIGH,self._r8(_GPIO_HV_MUX_ACTIVE_HIGH)&~0x10)
        self._w8(_SYSTEM_INTERRUPT_CLEAR,0x01)
        # Reference calibration with the conventional pre/final range sequence.
        self._w8(_SYSTEM_SEQUENCE_CONFIG,0x01); self._ref_cal(0x40)
        self._w8(_SYSTEM_SEQUENCE_CONFIG,0x02); self._ref_cal(0x00)
        self._w8(_SYSTEM_SEQUENCE_CONFIG,0xE8)

    def set_signal_rate_limit(self, mcps):
        if mcps < 0 or mcps > 511.99:
            raise ValueError('signal rate limit out of range')
        self._w16(_FINAL_RANGE_CONFIG_MIN_COUNT_RATE_RTN_LIMIT, int(mcps * 128.0))

    def read_range_single_millimeters(self):
        self._w8(0x80,0x01); self._w8(0xFF,0x01); self._w8(0x00,0x00)
        self._w8(0x91,self._stop_variable); self._w8(0x00,0x01); self._w8(0xFF,0x00); self._w8(0x80,0x00)
        self._w8(_SYSRANGE_START,0x01)
        self._wait(lambda: (self._r8(_SYSRANGE_START)&0x01)==0, 'VL53L0X start timeout')
        self._wait(lambda: (self._r8(_RESULT_INTERRUPT_STATUS)&0x07)!=0, 'VL53L0X range timeout')
        mm=self._r16(_RESULT_RANGE_STATUS+10)
        self._w8(_SYSTEM_INTERRUPT_CLEAR,0x01)
        return int(mm)

    @property
    def range(self):
        return self.read_range_single_millimeters()

    def ping(self):
        return self.read_range_single_millimeters()
