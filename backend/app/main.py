"""FastAPI application for Acer Swift 3 robot control station."""
from __future__ import annotations

import asyncio
import math
import time
from contextlib import asynccontextmanager, suppress
from typing import Any

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .announcer import announcer
from .battery_estimator import battery_trend
from .autonomy import AutonomyManager
from .camera import camera_hub
from .config import settings
from .database import init_database, list_events, log_event, log_telemetry
from .memory import build_agent_context
from .mapping import mapping
from .mcp_bridge import RobotMcpBridge
from .models import (
    AutonomyConfigRequest,
    DriveCommand,
    DriveTuningSettings,
    LlmRequest,
    ManualVector,
    PwmTestCommand,
    SpeechRequest,
    StopRequest,
    TuningLoadRequest,
    TuningProfileSaveRequest,
    VisionConfigRequest,
    VoiceConfigRequest,
)
from .ollama_client import OllamaClient
from .preferences import preferences
from .robot_client import RobotClient
from .scenarios import ScenarioEngine
from .skills import skill_store
from .tts import render_pcm
from .tuning import tuning_store
from .vision import vision
from .device_update import DeviceUpdater

robot = RobotClient()
device_updater = DeviceUpdater(robot)
ollama = OllamaClient()
scenarios = ScenarioEngine()
telemetry_cache: dict[str, Any] = {"connected": False}
telemetry_clients: set[WebSocket] = set()
telemetry_task: asyncio.Task[None] | None = None
_previous_connected = False
_previous_emergency = False
_last_telemetry_log = 0.0
_scenario_sensor_safety_enabled = True


autonomy = AutonomyManager(
    robot=robot,
    ollama=ollama,
    tuning=tuning_store,
    telemetry=lambda: telemetry_cache,
    vision=vision.status,
    announce=announcer.say,
)

mcp = RobotMcpBridge(robot, camera_hub, mapping, lambda: telemetry_cache, announcer.say)


class PtzRequest(BaseModel):
    pan: float = Field(ge=-1.0, le=1.0)
    tilt: float = Field(ge=-1.0, le=1.0)
    zoom: float = Field(default=0.0, ge=-1.0, le=1.0)


class MapPoseRequest(BaseModel):
    x_m: float = 0.0
    y_m: float = 0.0
    heading_deg: float = 0.0


class MapZoneRequest(BaseModel):
    id: str = ""
    name: str = Field(min_length=1, max_length=80)
    kind: str = Field(default="room", max_length=32)
    points: list[dict[str, float]] = Field(min_length=3, max_length=64)


class MapWallRequest(BaseModel):
    id: str = ""
    name: str = Field(default="стена", max_length=80)
    kind: str = Field(default="wall", max_length=32)
    a: dict[str, float]
    b: dict[str, float]
    enabled: bool = True


class MapAnchorRequest(BaseModel):
    id: str = ""
    label: str = Field(min_length=1, max_length=80)
    name: str = Field(default="", max_length=120)
    x_m: float
    y_m: float
    kind: str = Field(default="static", max_length=32)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    notes: str = Field(default="", max_length=300)


class MapPromoteRequest(BaseModel):
    object_id: str = Field(min_length=1, max_length=120)
    name: str = Field(default="", max_length=120)


class MapPlanRequest(BaseModel):
    zone: str = Field(default="", max_length=120)
    x_m: float | None = None
    y_m: float | None = None


class McpCallRequest(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    arguments: dict[str, Any] = Field(default_factory=dict)


class WifiNetworkRequest(BaseModel):
    ssid: str = Field(min_length=1, max_length=64)
    password: str = Field(default="", max_length=128)
    priority: int = Field(default=0, ge=-1000, le=1000)


class WifiNetworksRequest(BaseModel):
    networks: list[WifiNetworkRequest] = Field(min_length=1, max_length=6)


def enrich_telemetry(data: dict[str, Any]) -> dict[str, Any]:
    """Add display estimates on Acer without growing ESP32 firmware."""
    left_pwm = int(data.get("current_left_pwm", 0) or 0)
    right_pwm = int(data.get("current_right_pwm", 0) or 0)
    pwm_limit = max(1, int(data.get("pwm_limit", settings.drive_pwm_limit) or settings.drive_pwm_limit))
    left_rpm = abs(left_pwm) / pwm_limit * settings.motor_estimated_max_rpm
    right_rpm = abs(right_pwm) / pwm_limit * settings.motor_estimated_max_rpm
    circumference_m = math.pi * settings.wheel_diameter_mm / 1000.0
    direction_sign = 0 if left_pwm + right_pwm == 0 else (1 if left_pwm + right_pwm > 0 else -1)
    speed_mps = ((left_rpm + right_rpm) / 2.0) * circumference_m / 60.0 * direction_sign

    if left_pwm > 0 and right_pwm > 0:
        drive_state = "forward"
    elif left_pwm < 0 and right_pwm < 0:
        drive_state = "reverse"
    elif left_pwm < right_pwm:
        drive_state = "turn_left"
    elif left_pwm > right_pwm:
        drive_state = "turn_right"
    else:
        drive_state = "stopped"

    enriched = {
        **data,
        "pwm_limit": pwm_limit,
        "estimated_left_rpm": round(left_rpm, 1),
        "estimated_right_rpm": round(right_rpm, 1),
        "estimated_speed_mps": round(speed_mps, 3),
        "drive_state": drive_state,
    }
    return battery_trend.enrich(enriched)


async def _announce_state_changes(data: dict[str, Any]) -> None:
    global _previous_connected, _previous_emergency
    connected = bool(data.get("connected"))
    emergency = bool(data.get("emergency_stop"))

    if connected and not _previous_connected:
        await announcer.say("Создатель, связь с контроллером установлена.", "critical", 10.0)
        log_event("INFO", "system", "ESP32 connected", {"ip": data.get("ip")})
        try:
            await robot.apply_tuning(tuning_store.current())
        except Exception as exc:
            log_event("WARNING", "tuning", "Could not push active tuning after ESP32 connect", {"error": str(exc)})
    elif not connected and _previous_connected:
        await announcer.say("Создатель, потеряна связь с контроллером.", "critical", 10.0)
        log_event("ERROR", "system", "ESP32 disconnected")

    if emergency and not _previous_emergency:
        reason = str(data.get("last_stop_reason") or "сработала локальная защита")
        await announcer.say(f"Остановка. {reason}.", "critical", 5.0)
        log_event("WARNING", "safety", "Local safety stop", {"reason": reason})

    _previous_connected = connected
    _previous_emergency = emergency


async def telemetry_loop() -> None:
    global telemetry_cache, _last_telemetry_log
    while True:
        try:
            raw = await robot.telemetry()
            telemetry_cache = enrich_telemetry({"connected": True, **raw})
            mapping.update(telemetry_cache, vision.status(), camera_hub.status())
            await _announce_state_changes(telemetry_cache)

            if _scenario_sensor_safety_enabled:
                # Scenarios are observations/training records only. Motor safety
                # is enforced locally by ESP32 using the active tuning profile.
                scenarios.evaluate(telemetry_cache)

            now = time.monotonic()
            if now - _last_telemetry_log >= settings.telemetry_log_interval_s:
                log_telemetry(telemetry_cache)
                _last_telemetry_log = now

            stale: list[WebSocket] = []
            for websocket in list(telemetry_clients):
                try:
                    await websocket.send_json(telemetry_cache)
                except Exception:
                    stale.append(websocket)
            for websocket in stale:
                telemetry_clients.discard(websocket)
        except Exception as exc:
            telemetry_cache = {"connected": False, "error": str(exc)}
            await _announce_state_changes(telemetry_cache)
        await asyncio.sleep(settings.telemetry_interval_s)


@asynccontextmanager
async def lifespan(app: FastAPI):
    del app
    global telemetry_task
    init_database()
    # Restore non-dangerous operator preferences. Autonomous motion is never
    # auto-enabled after a backend restart; only its goal text is restored.
    voice_pref = preferences.get("voice")
    announcer.configure(voice_pref)
    vision_pref = preferences.get("vision")
    vision.configure(bool(vision_pref.get("enabled", False)), list(vision_pref.get("classes", []) or []))
    autonomy_pref = preferences.get("autonomy")
    autonomy.goal = str(autonomy_pref.get("goal") or autonomy.goal)
    log_event("INFO", "system", "Hombo3 control station started", {"version": "3.0.1b", "board": "ESP32-S3-DevKitC-1 N16R8", "spatial_engine": "VectorProbe"})
    await announcer.start(robot.send_pcm)
    await camera_hub.start()
    await vision.start(camera_hub.latest_jpeg, announcer.say)
    telemetry_task = asyncio.create_task(telemetry_loop(), name="robot-telemetry")
    yield
    if telemetry_task:
        telemetry_task.cancel()
        with suppress(asyncio.CancelledError):
            await telemetry_task
    await autonomy.stop()
    await vision.stop()
    await camera_hub.stop()
    await announcer.stop()
    await robot.close()
    await ollama.close()


app = FastAPI(title="Hombo3 Robot Control Station", version="3.0.1b", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
async def health() -> dict[str, Any]:
    return {
        "ok": True,
        "esp32": telemetry_cache,
        "ollama_model": settings.ollama_model,
        "camera_configured": camera_hub.configured,
        "camera": camera_hub.status(),
        "vision": vision.status(),
        "voice": announcer.status(),
        "map": {"pose": mapping.pose(), "zones": len(mapping.zones), "points": len(mapping.points)},
    }


@app.get("/api/dashboard/config")
async def dashboard_config() -> dict[str, Any]:
    profile = tuning_store.current()
    return {
        "wheel_diameter_mm": settings.wheel_diameter_mm,
        "motor_estimated_max_rpm": settings.motor_estimated_max_rpm,
        "drive_pwm_limit": 255,
        "telemetry_interval_s": settings.telemetry_interval_s,
        "active_profile": profile.name,
    }


@app.get("/api/telemetry")
async def telemetry() -> dict[str, Any]:
    return telemetry_cache


@app.websocket("/ws/telemetry")
async def telemetry_ws(websocket: WebSocket) -> None:
    await websocket.accept()
    telemetry_clients.add(websocket)
    try:
        await websocket.send_json(telemetry_cache)
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        telemetry_clients.discard(websocket)


def _movement_phrase(vector: ManualVector) -> str:
    if vector.throttle > 0 and abs(vector.turn) < 5:
        return f"Еду прямо. Скорость команды {abs(vector.throttle)} процентов."
    if vector.throttle < 0 and abs(vector.turn) < 5:
        return f"Еду назад. Скорость команды {abs(vector.throttle)} процентов."
    if vector.turn < 0:
        return f"Поворачиваю налево. Интенсивность {abs(vector.turn)} процентов."
    if vector.turn > 0:
        return f"Поворачиваю направо. Интенсивность {abs(vector.turn)} процентов."
    return "Остановка."


@app.post("/api/drive")
async def drive(command: DriveCommand) -> dict[str, Any]:
    global _scenario_sensor_safety_enabled
    if autonomy.enabled:
        raise HTTPException(status_code=409, detail="Autonomous mode is active; only Hermes may command motion. STOP remains available.")
    _scenario_sensor_safety_enabled = True
    try:
        return await robot.drive(command)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"ESP32 command failed: {exc}") from exc


@app.post("/api/vector")
async def vector(command: ManualVector) -> dict[str, Any]:
    global _scenario_sensor_safety_enabled
    if autonomy.enabled:
        raise HTTPException(status_code=409, detail="Autonomous mode is active; only Hermes may command motion. STOP remains available.")
    _scenario_sensor_safety_enabled = True
    try:
        response = await robot.vector(command)
        if command.voice:
            await announcer.say(_movement_phrase(command), "action", 1.8)
        return response
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"ESP32 command failed: {exc}") from exc


def _pwm_test_phrase(command: PwmTestCommand) -> str:
    left = command.left_pwm
    right = command.right_pwm
    level = max(abs(left), abs(right))
    safety = "с защитой дальномеров" if command.sensor_safety else "без блокировки дальномерами"
    if left == 0 and right == 0:
        return f"Тест PWM ноль, остановка, {safety}."
    if left > 0 and right > 0:
        return f"Тест PWM {level}. Еду прямо, {safety}."
    if left < 0 and right < 0:
        return f"Тест PWM {level}. Еду назад, {safety}."
    if left < right:
        return f"Тест PWM {level}. Поворот налево, {safety}."
    if left > right:
        return f"Тест PWM {level}. Поворот направо, {safety}."
    return f"Тест PWM {level}, {safety}."


@app.post("/api/pwm-test")
async def pwm_test(command: PwmTestCommand) -> dict[str, Any]:
    global _scenario_sensor_safety_enabled
    if autonomy.enabled:
        raise HTTPException(status_code=409, detail="Autonomous mode is active; raw/manual motor commands are locked. STOP remains available.")
    _scenario_sensor_safety_enabled = command.sensor_safety
    try:
        response = await robot.pwm_test(command)
        if command.voice:
            await announcer.say(_pwm_test_phrase(command), "action", 1.2)
        return response
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"ESP32 raw PWM test failed: {exc}") from exc


@app.post("/api/stop")
async def stop(request: StopRequest) -> dict[str, Any]:
    global _scenario_sensor_safety_enabled
    _scenario_sensor_safety_enabled = True
    try:
        response = await robot.stop("web")
        if request.voice:
            await announcer.say("Остановка.", "action", 1.5)
        return response
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"ESP32 stop failed: {exc}") from exc


@app.post("/api/speak")
async def speak(request: SpeechRequest) -> dict[str, Any]:
    try:
        pcm, sample_rate = await render_pcm(request.text, request.rate)
        await robot.send_pcm(pcm, sample_rate)
        announcer.last_phrase = request.text
        log_event("INFO", "speech", "Manual phrase played", {"text": request.text, "bytes": len(pcm)})
        return {"ok": True, "bytes": len(pcm), "sample_rate": sample_rate}
    except Exception as exc:
        log_event("ERROR", "speech", "Speech failed", {"error": str(exc)})
        raise HTTPException(status_code=500, detail=f"Speech failed: {exc}") from exc


@app.get("/api/voice/status")
async def voice_status() -> dict[str, object]:
    return announcer.status()


@app.post("/api/voice/config")
async def voice_config(request: VoiceConfigRequest) -> dict[str, object]:
    values = request.model_dump(exclude_none=True)
    state = announcer.configure(values)
    preferences.update("voice", values)
    return state


@app.get("/api/vision/status")
async def vision_status() -> dict[str, object]:
    return vision.status()


@app.post("/api/vision/config")
async def vision_config(request: VisionConfigRequest) -> dict[str, object]:
    state = vision.configure(request.enabled, request.classes)
    preferences.update("vision", {"enabled": bool(state.get("enabled")), "classes": list(state.get("classes", []))})
    return state


@app.post("/api/llm")
async def llm(request: LlmRequest) -> dict[str, Any]:
    try:
        decision = await ollama.decide(request.prompt, telemetry_cache, request.allow_action, build_agent_context(request.prompt, telemetry_cache, vision.status()))
        if decision.say:
            await announcer.say(decision.say, "observation", 1.0)

        if request.allow_action and autonomy.enabled:
            raise HTTPException(status_code=409, detail="Autonomous mode is active; use the autonomous agent loop instead of one-shot manual LLM actions.")

        if request.allow_action:
            profile = tuning_store.current()
            left, right = AutonomyManager._action_to_pwm(decision.action, decision.speed, profile)
            if decision.action in {"none", "stop"}:
                await robot.stop("hermes-one-shot")
            else:
                await robot.pwm_test(PwmTestCommand(
                    left_pwm=left,
                    right_pwm=right,
                    sensor_safety=True,
                    ttl_ms=max(300, min(decision.duration_ms or profile.autonomy_command_ms, 3000)),
                    voice=False,
                    source="hermes-one-shot",
                ))
        log_event("INFO", "ollama", "LLM decision", decision.model_dump())
        return {"ok": True, "decision": decision.model_dump()}
    except Exception as exc:
        detail = str(exc).strip() or f"{type(exc).__name__}: {exc!r}"
        log_event(
            "ERROR",
            "ollama",
            "LLM request failed",
            {"error": detail, "exception_type": type(exc).__name__},
        )
        raise HTTPException(status_code=502, detail=f"Ollama request failed: {detail}") from exc


@app.get("/api/llm/status")
async def llm_status() -> dict[str, Any]:
    return await ollama.status()


@app.get("/api/agent/context")
async def agent_context(q: str = "текущее состояние") -> dict[str, Any]:
    return build_agent_context(q, telemetry_cache, vision.status())


@app.get("/api/tuning")
async def tuning_status() -> dict[str, Any]:
    return tuning_store.list()


@app.get("/api/tuning/history")
async def tuning_history(limit: int = 100) -> list[dict[str, Any]]:
    return tuning_store.history(limit)


@app.post("/api/tuning/save")
async def tuning_save(request: TuningProfileSaveRequest) -> dict[str, Any]:
    state = tuning_store.save(request.name, request.settings, activate=request.activate)
    if request.activate:
        try:
            state["esp32"] = await robot.apply_tuning(tuning_store.current())
        except Exception as exc:
            state["esp32_error"] = str(exc)
    return state


@app.post("/api/tuning/preview")
async def tuning_preview(request: DriveTuningSettings) -> dict[str, Any]:
    """Apply the controller-side subset without changing the saved profile."""
    try:
        reply = await robot.apply_tuning(request)
        return {"ok": True, "temporary": True, "esp32": reply}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"ESP32 tuning preview failed: {exc}") from exc


@app.post("/api/tuning/load")
async def tuning_load(request: TuningLoadRequest) -> dict[str, Any]:
    try:
        state = tuning_store.load(request.name)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Tuning profile not found: {request.name}") from exc
    try:
        state["esp32"] = await robot.apply_tuning(tuning_store.current())
    except Exception as exc:
        state["esp32_error"] = str(exc)
    return state


@app.post("/api/tuning/push")
async def tuning_push() -> dict[str, Any]:
    try:
        return {"ok": True, "esp32": await robot.apply_tuning(tuning_store.current())}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"ESP32 tuning push failed: {exc}") from exc


@app.get("/api/autonomy/status")
async def autonomy_status() -> dict[str, Any]:
    return autonomy.status()


@app.post("/api/autonomy/config")
async def autonomy_config(request: AutonomyConfigRequest) -> dict[str, Any]:
    state = await autonomy.configure(request.enabled, request.goal)
    preferences.update("autonomy", {"goal": state.get("goal", request.goal)})
    return state


@app.get("/api/skills")
async def skills() -> dict[str, Any]:
    return skill_store.list()


@app.post("/api/skills/reload")
async def skills_reload() -> dict[str, Any]:
    skill_store.reload()
    return skill_store.list()


@app.get("/api/logs")
async def logs(limit: int = 200, category: str = "") -> list[dict[str, Any]]:
    return list_events(limit, category)


@app.post("/api/scenarios/reload")
async def reload_scenarios() -> dict[str, Any]:
    scenarios.reload()
    return {"ok": True, "count": len(scenarios.rules)}


@app.get("/api/camera/status")
async def camera_status() -> dict[str, object]:
    return camera_hub.status()


@app.get("/api/camera/stream")
async def camera_stream() -> StreamingResponse:
    if not camera_hub.configured:
        raise HTTPException(status_code=503, detail="Camera is not configured")
    return StreamingResponse(
        camera_hub.mjpeg_stream(),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={"Cache-Control": "no-store, no-cache, must-revalidate"},
    )


@app.websocket("/ws/camera")
async def camera_websocket(websocket: WebSocket) -> None:
    """Latest-frame binary JPEG channel for the dashboard.

    There is intentionally no per-client frame queue. If a browser cannot keep
    up, the generator resumes from the newest frame after send_bytes() returns.
    """
    await websocket.accept()
    if not camera_hub.configured:
        await websocket.close(code=1013, reason="Camera is not configured")
        return
    try:
        async for jpeg in camera_hub.jpeg_stream():
            await websocket.send_bytes(jpeg)
    except (WebSocketDisconnect, asyncio.CancelledError):
        return
    except Exception as exc:
        log_event("WARNING", "camera", "Camera WebSocket closed", {"error": str(exc)})
        with suppress(Exception):
            await websocket.close(code=1011)


@app.get("/api/camera/audio")
async def camera_audio() -> StreamingResponse:
    if not camera_hub.configured:
        raise HTTPException(status_code=503, detail="Camera is not configured")
    if not settings.camera_audio_enabled:
        raise HTTPException(status_code=503, detail="Camera microphone relay is disabled")
    if not camera_hub.status().get("audio_backend"):
        raise HTTPException(status_code=503, detail="FFmpeg audio backend is not installed")
    return StreamingResponse(
        camera_hub.audio_stream(),
        media_type="audio/mpeg",
        headers={"Cache-Control": "no-store"},
    )


@app.post("/api/camera/ptz")
async def camera_ptz(request: PtzRequest) -> dict[str, Any]:
    try:
        await camera_hub.ptz_move(request.pan, request.tilt, request.zoom)
        return {"ok": True, "camera": camera_hub.status()}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"ONVIF PTZ failed: {exc}") from exc


@app.post("/api/camera/autofocus")
async def camera_autofocus() -> dict[str, Any]:
    try:
        result = await camera_hub.autofocus()
        return {"ok": True, "focus": result, "camera": camera_hub.status()}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"ONVIF autofocus unavailable: {exc}") from exc



@app.get("/api/map")
async def map_state() -> dict[str, Any]:
    return mapping.state()


@app.post("/api/map/reset")
async def map_reset() -> dict[str, Any]:
    return mapping.reset()


@app.post("/api/map/pose")
async def map_pose(request: MapPoseRequest) -> dict[str, Any]:
    return {"ok": True, "pose": mapping.set_pose(request.x_m, request.y_m, request.heading_deg)}


@app.post("/api/map/zones")
async def map_zone_save(request: MapZoneRequest) -> dict[str, Any]:
    try:
        return {"ok": True, "zone": mapping.add_zone(request.model_dump())}
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.delete("/api/map/zones/{zone_id}")
async def map_zone_delete(zone_id: str) -> dict[str, Any]:
    mapping.delete_zone(zone_id)
    return {"ok": True}


@app.post("/api/map/walls")
async def map_wall_save(request: MapWallRequest) -> dict[str, Any]:
    try:
        return {"ok": True, "wall": mapping.add_wall(request.model_dump())}
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.delete("/api/map/walls/{wall_id}")
async def map_wall_delete(wall_id: str) -> dict[str, Any]:
    mapping.delete_wall(wall_id)
    return {"ok": True}


@app.post("/api/map/anchors")
async def map_anchor_save(request: MapAnchorRequest) -> dict[str, Any]:
    try:
        return {"ok": True, "anchor": mapping.add_anchor(request.model_dump())}
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.delete("/api/map/anchors/{anchor_id}")
async def map_anchor_delete(anchor_id: str) -> dict[str, Any]:
    mapping.delete_anchor(anchor_id)
    return {"ok": True}


@app.post("/api/map/promote")
async def map_promote(request: MapPromoteRequest) -> dict[str, Any]:
    try:
        return {"ok": True, "anchor": mapping.promote_object(request.object_id, request.name)}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/map/plan")
async def map_plan(request: MapPlanRequest) -> dict[str, Any]:
    try:
        if request.zone.strip():
            return mapping.plan_to_zone(request.zone.strip())
        if request.x_m is None or request.y_m is None:
            raise ValueError("zone or x_m/y_m is required")
        target={"x_m": float(request.x_m), "y_m": float(request.y_m)}
        route=mapping.plan_path(target)
        return {"ok": bool(route), "target": target, "route": route, "steering": mapping.steering_hint(target) if route else None}
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/map/reference/clear")
async def map_reference_clear() -> dict[str, Any]:
    return mapping.clear_reference()


@app.get("/api/mcp/tools")
async def mcp_tools() -> dict[str, Any]:
    return {"protocol": "hombo3-mcp/0.2", "tools": mcp.tools()}


@app.post("/api/mcp/call")
async def mcp_call(request: McpCallRequest) -> dict[str, Any]:
    try:
        result = await mcp.call(request.name, request.arguments)
        return {"ok": True, "tool": request.name, "result": result}
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"MCP tool failed: {exc}") from exc


@app.get("/api/device/wifi")
async def device_wifi_status() -> dict[str, Any]:
    try:
        return await device_updater.wifi_status()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"ESP32 Wi-Fi status failed: {exc}") from exc


@app.post("/api/device/wifi")
async def device_wifi_config(request: WifiNetworksRequest) -> dict[str, Any]:
    try:
        return await device_updater.wifi_configure([item.model_dump() for item in request.networks])
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"ESP32 Wi-Fi config failed: {exc}") from exc


@app.get("/api/device/update/status")
async def device_update_status() -> dict[str, Any]:
    try:
        return await device_updater.status()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"ESP32 update status failed: {exc}") from exc


@app.post("/api/device/update/runtime")
async def device_update_runtime() -> dict[str, Any]:
    try:
        return await device_updater.runtime()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Runtime OTA failed: {exc}") from exc


@app.post("/api/device/update/rollback")
async def device_update_rollback() -> dict[str, Any]:
    try:
        return await device_updater.rollback()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Runtime rollback failed: {exc}") from exc


@app.get("/api/device/update/core-files")
async def device_update_core_files() -> dict[str, Any]:
    return {"files": device_updater.core_files()}


class CoreOtaRequest(BaseModel):
    filename: str


@app.post("/api/device/update/core")
async def device_update_core(request: CoreOtaRequest) -> dict[str, Any]:
    try:
        return await device_updater.core(request.filename)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Core OTA failed: {exc}") from exc

if settings.frontend_dist.exists():
    assets_dir = settings.frontend_dist / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    async def spa(path: str) -> FileResponse:
        del path
        return FileResponse(settings.frontend_dist / "index.html")
