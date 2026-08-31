"""Small persistent control-station preferences stored on Acer.

These are operator/UI preferences, not safety-critical motor calibration.  The
chassis profiles keep their own versioned store in tuning.py.
"""
from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

from .config import settings

_lock = threading.Lock()

_DEFAULT: dict[str, Any] = {
    "vision": {"enabled": False, "classes": []},
    "voice": {
        "enabled": True,
        "announce_actions": True,
        "announce_observations": True,
        "announce_critical": True,
    },
    # Autonomy is deliberately NOT auto-enabled after backend restart.
    "autonomy": {
        "goal": "Безопасно исследовать пространство и не сталкиваться с препятствиями."
    },
}


class PreferencesStore:
    def __init__(self) -> None:
        self.path = Path(settings.root_dir) / "data" / "settings" / "runtime_preferences.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.data: dict[str, Any] = {}
        self.reload()

    def reload(self) -> None:
        try:
            loaded = json.loads(self.path.read_text("utf-8"))
        except Exception:
            loaded = {}
        self.data = {**_DEFAULT, **loaded}
        for section, defaults in _DEFAULT.items():
            if isinstance(defaults, dict):
                current = self.data.get(section)
                if not isinstance(current, dict):
                    current = {}
                self.data[section] = {**defaults, **current}
        self._write()

    def _write(self) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), "utf-8")
        tmp.replace(self.path)

    def get(self, section: str) -> dict[str, Any]:
        value = self.data.get(section, {})
        return dict(value) if isinstance(value, dict) else {}

    def update(self, section: str, values: dict[str, Any]) -> dict[str, Any]:
        with _lock:
            current = self.get(section)
            current.update(values)
            self.data[section] = current
            self._write()
        return dict(current)


preferences = PreferencesStore()
