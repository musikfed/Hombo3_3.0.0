"""Versioned lightweight robot skills stored on Acer.

These are not hard-coded motor scripts. They are compact behavior policies that
Hermes can retrieve and reason over together with telemetry and the robot graph.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .config import settings

_DEFAULT = {
    "version": 1,
    "skills": [
        {
            "id": "explore_space",
            "name": "Исследование пространства",
            "when": "автономный режим и нет конкретной цели",
            "policy": "двигаться короткими безопасными участками, заранее снижать скорость при сокращении дистанции, при блокировке искать свободное направление и продолжать",
        },
        {
            "id": "greet_person",
            "name": "Приветствие человека",
            "when": "локальный детектор Acer устойчиво видит person",
            "policy": "поздороваться; не ехать к человеку, если проход не подтверждён дальномерами; приближение только малой скоростью",
        },
        {
            "id": "obstacle_bypass",
            "name": "Обход препятствия",
            "when": "передняя дистанция уменьшается или ESP32 остановила движение",
            "policy": "остановиться, оценить свободное пространство по дальномерам и камере, выбрать поворот левым/правым бортом, затем продолжить",
        },
        {
            "id": "side_diagnostics",
            "name": "Проверка бортов",
            "when": "стендовая диагностика",
            "policy": "проверять левый и правый борт отдельно на малом RAW PWM; не использовать как автономное поведение",
        },
    ],
}


class SkillStore:
    def __init__(self) -> None:
        self.path = Path(settings.root_dir) / "data" / "skills" / "skills.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.write_text(json.dumps(_DEFAULT, ensure_ascii=False, indent=2), encoding="utf-8")
        self.reload()

    def reload(self) -> None:
        try:
            self.data: dict[str, Any] = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            self.data = dict(_DEFAULT)

    def list(self) -> dict[str, Any]:
        return self.data

    def relevant(self, query: str) -> list[dict[str, Any]]:
        terms = {part.lower() for part in query.replace("/", " ").split() if len(part) > 3}
        skills = list(self.data.get("skills", []))
        if not terms:
            return skills
        scored: list[tuple[int, dict[str, Any]]] = []
        for item in skills:
            text = json.dumps(item, ensure_ascii=False).lower()
            score = sum(1 for term in terms if term in text)
            if score:
                scored.append((score, item))
        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [item for _, item in scored] or skills[:2]


skill_store = SkillStore()
