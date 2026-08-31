"""Hermes-controlled autonomous mode.

Only Hermes chooses motion in this mode. Acer validates/mixes the chosen action,
and ESP32 can always override it with watchdog/obstacle safety. Manual STOP is
still available at all times.
"""
from __future__ import annotations

import asyncio
from contextlib import suppress
from typing import Any, Awaitable, Callable

from .database import append_dataset_record, log_event
from .memory import build_agent_context
from .models import PwmTestCommand
from .ollama_client import OllamaClient
from .robot_client import RobotClient
from .tuning import TuningStore

TelemetryProvider = Callable[[], dict[str, Any]]
VisionProvider = Callable[[], dict[str, Any]]
Announce = Callable[[str, str, float], Awaitable[bool]]


class AutonomyManager:
    def __init__(
        self,
        robot: RobotClient,
        ollama: OllamaClient,
        tuning: TuningStore,
        telemetry: TelemetryProvider,
        vision: VisionProvider,
        announce: Announce,
    ) -> None:
        self.robot = robot
        self.ollama = ollama
        self.tuning = tuning
        self.telemetry = telemetry
        self.vision = vision
        self.announce = announce
        self.enabled = False
        self.goal = "Безопасно исследовать пространство и не сталкиваться с препятствиями."
        self.last_decision: dict[str, Any] = {}
        self.last_error = ""
        self.cycle = 0
        self._task: asyncio.Task[None] | None = None

    def status(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "goal": self.goal,
            "cycle": self.cycle,
            "last_decision": self.last_decision,
            "last_error": self.last_error,
            "mode": "hermes_only_motion + esp32_safety_override",
        }

    async def configure(self, enabled: bool, goal: str) -> dict[str, Any]:
        self.goal = goal.strip() or self.goal
        if enabled and not self.enabled:
            with suppress(Exception):
                await self.robot.stop("autonomy-on")
            self.enabled = True
            self.last_error = ""
            self._task = asyncio.create_task(self._run(), name="hermes-autonomous-loop")
            log_event("WARNING", "autonomy", "Autonomous Hermes mode enabled", {"goal": self.goal})
            await self.announce("Автономный режим включён. Движением управляет агент.", "critical", 2.0)
        elif not enabled and self.enabled:
            self.enabled = False
            if self._task:
                self._task.cancel()
                with suppress(asyncio.CancelledError):
                    await self._task
                self._task = None
            with suppress(Exception):
                await self.robot.stop("autonomy-off")
            log_event("WARNING", "autonomy", "Autonomous Hermes mode disabled", {})
            await self.announce("Автономный режим выключен.", "critical", 2.0)
        return self.status()

    async def stop(self) -> None:
        if self.enabled:
            await self.configure(False, self.goal)

    @staticmethod
    def _action_to_pwm(action: str, speed: int, profile: Any) -> tuple[int, int]:
        if action in {"none", "stop"}:
            return 0, 0
        max_pwm = max(1, int(profile.max_pwm))
        min_pwm = min(max_pwm, max(0, int(profile.calibration_pwm)))
        requested = round(max_pwm * max(0, min(100, speed)) / 100.0)
        pwm = max(min_pwm, requested) if speed > 0 else int(profile.cruise_pwm)
        pwm = max(0, min(max_pwm, pwm))
        inner = round(pwm * max(0, min(100, int(profile.turn_inner_percent))) / 100.0)
        if action == "forward":
            return pwm, pwm
        if action == "backward":
            return -pwm, -pwm
        if action == "left":
            return inner, pwm
        if action == "right":
            return pwm, inner
        return 0, 0

    async def _run(self) -> None:
        while self.enabled:
            profile = self.tuning.current()
            telemetry = self.telemetry()
            vision = self.vision()
            prompt = (
                f"Автономная цель: {self.goal}\n"
                "Выбери ровно одно следующее безопасное действие. "
                "Используй левый/правый борт, дальномеры и локальные детекции. "
                "Если видишь человека, можно поздороваться; движение к человеку допускается только если проход свободен. "
                "При препятствии разрешены stop/left/right для поиска свободного пространства."
            )
            context = build_agent_context(prompt, telemetry, vision)
            try:
                decision = await self.ollama.decide(prompt, telemetry, True, context)
                self.last_decision = decision.model_dump()
                self.last_error = ""
                self.cycle += 1
                if decision.say:
                    await self.announce(decision.say, "observation", 1.0)
                left, right = self._action_to_pwm(decision.action, decision.speed, profile)
                if decision.action in {"none", "stop"}:
                    await self.robot.stop("hermes-autonomy")
                else:
                    ttl = max(300, min(int(profile.autonomy_command_ms), 3000))
                    await self.robot.pwm_test(PwmTestCommand(
                        left_pwm=left,
                        right_pwm=right,
                        sensor_safety=True,
                        ttl_ms=ttl,
                        voice=False,
                        source="hermes-autonomy",
                    ))
                record = {
                    "type": "autonomy_cycle",
                    "goal": self.goal,
                    "profile": profile.model_dump(),
                    "telemetry": telemetry,
                    "vision": vision,
                    "decision": decision.model_dump(),
                    "applied_pwm": {"left": left, "right": right},
                }
                append_dataset_record(record)
                log_event("INFO", "autonomy", "Hermes autonomous cycle", record)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.last_error = str(exc)
                log_event("ERROR", "autonomy", "Autonomous cycle failed", {"error": str(exc)})
                with suppress(Exception):
                    await self.robot.stop("autonomy-error")
            await asyncio.sleep(max(0.5, float(profile.autonomy_decision_interval_s)))
