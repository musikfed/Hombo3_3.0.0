"""Deterministic scenario engine.

Rules are intentionally simple and inspectable. They produce logs and future
training examples without allowing an LLM to bypass motor safety.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .config import settings
from .database import append_dataset_record, log_event


class ScenarioEngine:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or settings.scenario_path
        self.rules: list[dict[str, Any]] = []
        self.reload()

    def reload(self) -> None:
        if not self.path.exists():
            self.rules = []
            return
        self.rules = json.loads(self.path.read_text(encoding="utf-8"))

    def evaluate(self, telemetry: dict[str, Any]) -> list[dict[str, Any]]:
        fired: list[dict[str, Any]] = []
        for rule in self.rules:
            if not rule.get("enabled", True):
                continue
            condition = rule.get("condition", {})
            field = condition.get("field")
            operator = condition.get("operator")
            expected = condition.get("value")
            actual = telemetry.get(field)
            if actual is None:
                continue
            # Distance sensors use zero as timeout/no-valid-reading. Do not turn
            # a missing echo into a false obstacle stop on Acer.
            if field in {"front_cm", "rear_cm", "third_cm", "tof_mm"} and actual == 0:
                continue
            matched = {
                "lt": actual < expected,
                "lte": actual <= expected,
                "gt": actual > expected,
                "gte": actual >= expected,
                "eq": actual == expected,
            }.get(operator, False)
            if matched:
                event = {"rule": rule.get("name", "unnamed"), "action": rule.get("action", {}), "telemetry": telemetry}
                fired.append(event)
                log_event("INFO", "scenario", "Scenario fired", event)
                append_dataset_record({"type": "scenario", **event})
        return fired
