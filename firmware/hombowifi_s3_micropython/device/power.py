# EN: Battery voltage/SOC monitor for the Hombo3 2S2P pack.
# RU: Контроль напряжения/SOC аккумулятора Hombo3 2S2P.
import time
try:
    from machine import ADC, Pin
except Exception:
    ADC = None
    Pin = None
from board_config import *

# Rested Li-ion voltage curve per cell. It intentionally remains conservative.
# Under motor load the voltage sags; backend additionally keeps a time trend.
_SOC_CURVE = (
    (4.20, 100), (4.15, 96), (4.10, 90), (4.05, 85), (4.00, 80),
    (3.95, 74), (3.90, 67), (3.85, 60), (3.80, 52), (3.75, 43),
    (3.70, 34), (3.65, 25), (3.60, 18), (3.50, 10), (3.35, 4), (3.20, 0),
)


def _interp_soc(cell_v):
    if cell_v >= _SOC_CURVE[0][0]:
        return 100
    if cell_v <= _SOC_CURVE[-1][0]:
        return 0
    for idx in range(len(_SOC_CURVE) - 1):
        v_hi, p_hi = _SOC_CURVE[idx]
        v_lo, p_lo = _SOC_CURVE[idx + 1]
        if v_lo <= cell_v <= v_hi:
            part = (cell_v - v_lo) / (v_hi - v_lo)
            return int(round(p_lo + part * (p_hi - p_lo)))
    return 0


def _median(values):
    values = sorted(values)
    n = len(values)
    return values[n // 2] if n else 0.0


class PowerMonitor:
    def __init__(self):
        self.available = False
        self.reason = "battery ADC is not configured"
        self.voltage = 0.0
        self.percent = None
        self.raw = 0
        self._adc = None
        if ADC is None or PIN_BATTERY_ADC is None or int(PIN_BATTERY_ADC) < 0:
            return
        try:
            # ATTEN_11DB gives a useful calibrated linear range up to ~2.45 V.
            # The 4:1 divider keeps 8.4V -> ~2.10V.
            try:
                self._adc = ADC(Pin(int(PIN_BATTERY_ADC)), atten=ADC.ATTN_11DB)
            except TypeError:
                self._adc = ADC(Pin(int(PIN_BATTERY_ADC)))
                self._adc.atten(ADC.ATTN_11DB)
            self.available = True
            self.reason = ""
        except Exception as exc:
            self.reason = str(exc)

    def _sample_adc_v(self):
        # Median sampling rejects short motor/commutation spikes. read_uv() uses
        # ESP32 eFuse calibration in MicroPython 1.28 and is preferred when present.
        values = []
        raw_values = []
        for _ in range(7):
            if hasattr(self._adc, "read_uv"):
                uv = int(self._adc.read_uv())
                values.append(uv / 1000000.0)
            else:
                raw = int(self._adc.read_u16())
                raw_values.append(raw)
                # Fallback only. Exact scale should be calibrated with a multimeter.
                values.append((raw / 65535.0) * 2.45)
            time.sleep_ms(2)
        if raw_values:
            self.raw = int(_median(raw_values))
        else:
            try:
                self.raw = int(self._adc.read_u16())
            except Exception:
                self.raw = 0
        return _median(values)

    def read(self):
        if not self.available or self._adc is None:
            return {
                "power_available": False,
                "reason": self.reason,
                "battery_voltage": None,
                "battery_percent": None,
                "battery_cells": int(BATTERY_CELLS or 0),
            }
        try:
            adc_v = self._sample_adc_v()
            pack_v = adc_v * float(BATTERY_DIVIDER_RATIO) * float(BATTERY_CALIBRATION)
            # Slow IIR filter: battery trend is useful; motor spikes are not.
            self.voltage = self.voltage * 0.88 + pack_v * 0.12 if self.voltage else pack_v
            cells = int(BATTERY_CELLS or 0)
            self.percent = _interp_soc(self.voltage / cells) if cells > 0 else None
            pct = self.percent if self.percent is not None else 101
            return {
                "power_available": True,
                "reason": "",
                "battery_voltage": round(self.voltage, 3),
                "battery_percent": self.percent,
                "battery_cells": cells,
                "battery_adc_pin": int(PIN_BATTERY_ADC),
                "battery_adc_raw": self.raw,
                "battery_divider_ratio": float(BATTERY_DIVIDER_RATIO),
                "battery_low": pct <= int(BATTERY_LOW_PERCENT),
                "battery_return_home": pct <= int(BATTERY_RETURN_PERCENT),
                "battery_critical": pct <= int(BATTERY_CRITICAL_PERCENT),
                # Charging is inferred on Acer from voltage trend + zero motor PWM.
                "charging": None,
            }
        except Exception as exc:
            self.reason = str(exc)
            return {
                "power_available": False,
                "reason": self.reason,
                "battery_voltage": None,
                "battery_percent": None,
                "battery_cells": int(BATTERY_CELLS or 0),
            }
