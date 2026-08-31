"""Application settings loaded from environment variables or .env."""
from __future__ import annotations

from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """All network addresses and mechanical estimates are explicit."""

    model_config = SettingsConfigDict(
        env_file=ROOT_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    root_dir: Path = ROOT_DIR

    app_host: str = "0.0.0.0"
    app_port: int = 8088

    esp32_base_url: str = "http://192.168.1.61"
    esp32_audio_host: str = "192.168.1.61"
    esp32_audio_port: int = 3333
    esp32_request_timeout_s: float = 1.5
    esp32_api_token: str = ""

    ollama_base_url: str = "http://192.168.0.100:11434"
    ollama_model: str = "hf.co/bartowski/NousResearch_Hermes-4-14B-GGUF:Q4_K_M"
    ollama_timeout_s: float = 180.0

    camera_rtsp_url: str = ""
    camera_onvif_host: str = "192.168.1.62"
    camera_onvif_port: int = 8000
    camera_username: str = ""
    camera_password: str = ""
    camera_profile_mode: str = "low"
    camera_mjpeg_width: int = 640
    camera_mjpeg_fps: float = 10.0
    camera_jpeg_quality: int = 55
    camera_audio_enabled: bool = True
    camera_hfov_deg: float = 72.0
    # API uses semantic directions: pan<0 = left, pan>0 = right.
    # Flip only if a specific ONVIF camera implements the axis backwards.
    camera_pan_invert: bool = False
    camera_tilt_invert: bool = False
    camera_autofocus: bool = True
    # auto = FFmpeg image pipe when available, OpenCV fallback otherwise.
    camera_video_backend: str = "auto"
    camera_rtsp_transport: str = "tcp"
    camera_stall_timeout_s: float = 2.5

    # Local object detector on Acer. It never uses Ollama or server VRAM.
    vision_provider: str = "acer"
    vision_model: str = "yolo11n.pt"
    vision_model_path: str = ""
    vision_interval_s: float = 1.0
    vision_timeout_s: float = 90.0
    vision_min_confidence: float = 0.45
    vision_imgsz: int = 416
    vision_device: str = "cpu"
    vision_cpu_threads: int = 3

    telemetry_interval_s: float = 0.25
    telemetry_log_interval_s: float = 1.0
    command_ttl_ms: int = 1000

    wheel_diameter_mm: float = 65.0
    track_width_mm: float = 145.0
    head_pan_range_deg: float = 300.0
    head_ptz_step_deg: float = 18.0
    motor_estimated_max_rpm: float = 200.0
    drive_pwm_limit: int = 255

    database_path: Path = ROOT_DIR / "data" / "robot.sqlite3"
    scenario_path: Path = ROOT_DIR / "data" / "scenarios" / "default.json"
    dataset_path: Path = ROOT_DIR / "data" / "logs" / "behavior_dataset.jsonl"
    frontend_dist: Path = ROOT_DIR / "frontend" / "dist"
    map_state_path: Path = ROOT_DIR / "data" / "map_state.json"


settings = Settings()
