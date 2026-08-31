"""Battery trend estimator for the existing divider-only Hombo3 hardware.

No current sensor is required for the first build. The ESP32 reports calibrated pack
voltage and a conservative voltage->SOC estimate. Acer observes the time trend while
the motors are stopped to infer whether the wireless charger is raising the pack
voltage and to provide a rough learned ETA. This is deliberately labelled as an
estimate; adding INA226 later can improve it without changing the rest of the API.
"""
from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any


@dataclass
class BatteryTrendEstimator:
    samples: deque[tuple[float, float, float, bool]] = field(default_factory=lambda: deque(maxlen=360))
    _last_sample: float = 0.0

    def enrich(self, telemetry: dict[str, Any]) -> dict[str, Any]:
        voltage = telemetry.get("battery_voltage")
        percent = telemetry.get("battery_percent")
        if voltage is None or percent is None:
            return telemetry
        now = time.monotonic()
        stationary = abs(int(telemetry.get("current_left_pwm", 0) or 0)) <= 2 and abs(int(telemetry.get("current_right_pwm", 0) or 0)) <= 2
        if now - self._last_sample >= 5.0:
            self._last_sample = now
            self.samples.append((now, float(voltage), float(percent), stationary))

        recent = [s for s in self.samples if now - s[0] <= 180.0 and s[3]]
        charging = False
        eta_min = None
        charge_rate_pct_min = None
        voltage_rate_v_min = None
        if len(recent) >= 8:
            t0, v0, p0, _ = recent[0]
            t1, v1, p1, _ = recent[-1]
            minutes = max(0.05, (t1 - t0) / 60.0)
            voltage_rate_v_min = (v1 - v0) / minutes
            charge_rate_pct_min = (p1 - p0) / minutes
            # Require both a measurable voltage rise and a stationary chassis.
            # This avoids declaring "charging" just because motor load disappeared.
            charging = voltage_rate_v_min > 0.006 and (p1 >= p0)
            if charging and charge_rate_pct_min > 0.08 and float(percent) < 99.0:
                eta_min = min(24 * 60.0, (100.0 - float(percent)) / charge_rate_pct_min)

        pct = int(percent)
        return {
            **telemetry,
            "charging_estimated": charging,
            "charge_eta_min_estimated": round(eta_min, 1) if eta_min is not None else None,
            "charge_rate_pct_min_estimated": round(charge_rate_pct_min, 3) if charge_rate_pct_min is not None else None,
            "voltage_rate_v_min": round(voltage_rate_v_min, 4) if voltage_rate_v_min is not None else None,
            "battery_policy": (
                "critical" if pct <= 8 else
                "return_to_charger" if pct <= 15 else
                "plan_charge" if pct <= 25 else
                "normal"
            ),
        }


battery_trend = BatteryTrendEstimator()
