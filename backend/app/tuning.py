"""Persistent named chassis-tuning profiles on Acer.

ESP32 keeps only live runtime values. The Acer station owns persistence and
version history, then pushes the active profile to ESP32 after reconnect.
"""
from __future__ import annotations

import json
import re
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import settings
from .database import log_event
from .models import DriveTuningSettings

_lock = threading.Lock()
_SAFE_NAME = re.compile(r"[^0-9A-Za-zА-Яа-яЁё _.-]+")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_name(value: str) -> str:
    value = _SAFE_NAME.sub("_", value.strip())
    return value[:64] or "default"


class TuningStore:
    def __init__(self) -> None:
        self.path = Path(settings.root_dir) / "data" / "settings" / "drive_tuning.json"
        self.history_path = Path(settings.root_dir) / "data" / "settings" / "drive_tuning_history.jsonl"
        self._data: dict[str, Any] = {}
        self.reload()

    def _default_profile(self) -> DriveTuningSettings:
        return DriveTuningSettings()

    def reload(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            default = self._default_profile()
            self._data = {
                "active": "default",
                "revision": 1,
                "profiles": {"default": default.model_dump()},
                "updated_at": _now(),
            }
            self._write()
            return
        try:
            self._data = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            default = self._default_profile()
            self._data = {
                "active": "default",
                "revision": 1,
                "profiles": {"default": default.model_dump()},
                "updated_at": _now(),
            }
            self._write()

        profiles = self._data.setdefault("profiles", {})
        if not profiles:
            profiles["default"] = self._default_profile().model_dump()
        active = self._data.get("active")
        if active not in profiles:
            self._data["active"] = next(iter(profiles))
        self._data.setdefault("revision", 1)

    def _write(self) -> None:
        temp = self.path.with_suffix(".tmp")
        temp.write_text(json.dumps(self._data, ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(self.path)

    def _history(self, action: str, name: str, profile: dict[str, Any]) -> None:
        record = {
            "timestamp": _now(),
            "revision": int(self._data.get("revision", 1)),
            "action": action,
            "name": name,
            "profile": profile,
        }
        with self.history_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    def current(self) -> DriveTuningSettings:
        name = str(self._data.get("active") or "default")
        raw = dict(self._data.get("profiles", {}).get(name) or self._default_profile().model_dump())
        raw["name"] = name
        return DriveTuningSettings.model_validate(raw)

    def list(self) -> dict[str, Any]:
        current = self.current()
        return {
            "active": current.name,
            "revision": int(self._data.get("revision", 1)),
            "updated_at": self._data.get("updated_at", ""),
            "current": current.model_dump(),
            "profiles": sorted(self._data.get("profiles", {}).keys()),
        }

    def save(self, name: str, profile: DriveTuningSettings, activate: bool = True) -> dict[str, Any]:
        clean_name = _normalize_name(name)
        validated = profile.model_copy(update={"name": clean_name})
        with _lock:
            self._data.setdefault("profiles", {})[clean_name] = validated.model_dump()
            if activate:
                self._data["active"] = clean_name
            self._data["revision"] = int(self._data.get("revision", 0)) + 1
            self._data["updated_at"] = _now()
            self._write()
            self._history("save", clean_name, validated.model_dump())
        log_event("INFO", "tuning", "Drive tuning profile saved", {
            "name": clean_name,
            "revision": self._data["revision"],
            "profile": validated.model_dump(),
        })
        return self.list()

    def load(self, name: str) -> dict[str, Any]:
        clean_name = _normalize_name(name)
        if clean_name not in self._data.get("profiles", {}):
            raise KeyError(clean_name)
        with _lock:
            self._data["active"] = clean_name
            self._data["revision"] = int(self._data.get("revision", 0)) + 1
            self._data["updated_at"] = _now()
            self._write()
            self._history("load", clean_name, self._data["profiles"][clean_name])
        log_event("INFO", "tuning", "Drive tuning profile activated", {"name": clean_name})
        return self.list()

    def history(self, limit: int = 100) -> list[dict[str, Any]]:
        if not self.history_path.exists():
            return []
        lines = self.history_path.read_text(encoding="utf-8").splitlines()
        result: list[dict[str, Any]] = []
        for line in reversed(lines[-max(1, min(limit, 1000)):]):
            try:
                result.append(json.loads(line))
            except Exception:
                continue
        return result


tuning_store = TuningStore()
