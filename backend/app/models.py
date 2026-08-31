"""Pydantic schemas shared by API endpoints and the safety validator."""
from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, Field


class DriveCommand(BaseModel):
    left: int = Field(ge=-100, le=100)
    right: int = Field(ge=-100, le=100)
    ttl_ms: int = Field(default=1000, ge=100, le=5000)
    source: str = "web"


class ManualVector(BaseModel):
    throttle: int = Field(ge=-100, le=100)
    turn: int = Field(ge=-100, le=100)
    ttl_ms: int = Field(default=1000, ge=100, le=5000)
    voice: bool = True


class PwmTestCommand(BaseModel):
    left_pwm: int = Field(ge=-255, le=255)
    right_pwm: int = Field(ge=-255, le=255)
    sensor_safety: bool = True
    ttl_ms: int = Field(default=1500, ge=100, le=5000)
    voice: bool = True
    source: str = "pwm-calibration"


class StopRequest(BaseModel):
    voice: bool = True


class SpeechRequest(BaseModel):
    text: str = Field(min_length=1, max_length=3000)
    rate: int = Field(default=0, ge=-10, le=10)


class VoiceConfigRequest(BaseModel):
    enabled: bool | None = None
    announce_actions: bool | None = None
    announce_observations: bool | None = None
    announce_critical: bool | None = None


class VisionConfigRequest(BaseModel):
    enabled: bool
    classes: list[str] = Field(default_factory=list, max_length=32)


class LlmRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=5000)
    allow_action: bool = False


class LlmDecision(BaseModel):
    """Strict structure expected from Hermes/Ollama.

    Hermes may choose a high-level motion, but Acer maps it through the active
    drive profile and ESP32 still owns watchdog + obstacle safety.
    """

    say: str = Field(default="", max_length=1000)
    action: Literal["none", "stop", "forward", "backward", "left", "right"] = "none"
    speed: int = Field(default=0, ge=0, le=100)
    duration_ms: int = Field(default=0, ge=0, le=3000)
    reason: str = Field(default="", max_length=1000)


class DriveTuningSettings(BaseModel):
    """Persisted chassis tuning profile stored on Acer."""

    name: str = Field(default="default", min_length=1, max_length=64)
    calibration_pwm: int = Field(default=80, ge=0, le=255)
    cruise_pwm: int = Field(default=120, ge=0, le=255)
    max_pwm: int = Field(default=180, ge=1, le=255)
    turn_inner_percent: int = Field(default=35, ge=0, le=100)
    ramp_step_pwm: int = Field(default=2, ge=1, le=64)
    ramp_period_ms: int = Field(default=20, ge=5, le=250)
    front_stop_cm: int = Field(default=18, ge=2, le=400)
    rear_stop_cm: int = Field(default=15, ge=2, le=400)
    tof_stop_mm: int = Field(default=150, ge=20, le=4000)
    sensor_safety_default: bool = True
    autonomy_decision_interval_s: float = Field(default=1.5, ge=0.5, le=15.0)
    autonomy_command_ms: int = Field(default=900, ge=150, le=3000)
    robot_name: str = Field(default="Машинка", min_length=1, max_length=48)


class TuningProfileSaveRequest(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    settings: DriveTuningSettings
    # Save-only is useful while calibrating several profiles. Activation is a
    # separate explicit action and is what pushes the active controller subset.
    activate: bool = False


class TuningLoadRequest(BaseModel):
    name: str = Field(min_length=1, max_length=64)


class AutonomyConfigRequest(BaseModel):
    enabled: bool
    goal: str = Field(default="Безопасно исследовать пространство и не сталкиваться с препятствиями.", max_length=1500)


class ScenarioRule(BaseModel):
    name: str
    enabled: bool = True
    condition: dict
    action: dict
