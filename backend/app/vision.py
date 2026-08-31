"""Local object detection on Acer using a small Ultralytics YOLO model.

This module never calls Ollama. Hermes remains the only model used on the
Huananzhi server. Camera frames are already decoded by CameraHub; this worker
samples the latest JPEG at a low rate and performs CPU inference locally.
"""
from __future__ import annotations

import asyncio
import importlib.util
import os
import time
from contextlib import suppress
from dataclasses import dataclass, field
from pathlib import Path
from typing import Awaitable, Callable, Any

import cv2
import numpy as np

from .config import settings
from .database import log_event

FrameProvider = Callable[[], Awaitable[bytes | None]]
Announce = Callable[[str, str, float], Awaitable[bool]]

_LABEL_RU = {
    "person": "человека",
    "chair": "стул",
    "table": "стол",
    "bottle": "бутылку",
    "cup": "чашку",
    "cat": "кошку",
    "dog": "собаку",
    "car": "машину",
    "bicycle": "велосипед",
    "backpack": "рюкзак",
    "laptop": "ноутбук",
    "phone": "телефон",
    "tv": "телевизор",
    "sofa": "диван",
}

_ALIASES = {
    "dining table": "table",
    "cell phone": "phone",
    "couch": "sofa",
    "television": "tv",
}


@dataclass
class VisionManager:
    enabled: bool = False
    classes: list[str] = field(default_factory=lambda: [
        "person", "chair", "table", "bottle", "cup", "cat", "dog",
        "car", "bicycle", "backpack", "laptop", "phone", "tv", "sofa",
    ])
    detections: list[dict[str, Any]] = field(default_factory=list)
    error: str = ""
    inference_ms: float = 0.0
    loaded: bool = False

    _task: asyncio.Task[None] | None = field(default=None, init=False, repr=False)
    _frame_provider: FrameProvider | None = field(default=None, init=False, repr=False)
    _announce: Announce | None = field(default=None, init=False, repr=False)
    _last_labels: tuple[str, ...] = field(default_factory=tuple, init=False, repr=False)
    _model: Any | None = field(default=None, init=False, repr=False)

    @property
    def bundled_model_path(self) -> Path:
        return settings.root_dir / "data" / "models" / settings.vision_model

    @property
    def model_path(self) -> Path:
        value = settings.vision_model_path.strip()
        if value:
            configured = Path(value)
            if configured.exists():
                return configured
            # A moved/renamed project must not break detection when the release
            # already ships the requested model in data/models.
            if self.bundled_model_path.exists():
                return self.bundled_model_path
            return configured
        return self.bundled_model_path

    @property
    def model_path_source(self) -> str:
        value = settings.vision_model_path.strip()
        if value and Path(value).exists():
            return "VISION_MODEL_PATH"
        if self.bundled_model_path.exists():
            return "bundled"
        return "configured_missing" if value else "bundled_missing"

    def availability(self) -> dict[str, object]:
        provider_ok = settings.vision_provider.strip().lower() in {"acer", "local_yolo", "ultralytics", "local"}
        package_ok = importlib.util.find_spec("ultralytics") is not None
        model_exists = self.model_path.exists()
        return {
            "provider_ok": provider_ok,
            "package_ok": package_ok,
            "model_exists": model_exists,
            "available": provider_ok and package_ok and model_exists,
        }

    @property
    def available(self) -> bool:
        return bool(self.availability()["available"])

    def status(self) -> dict[str, object]:
        availability = self.availability()
        return {
            "enabled": self.enabled,
            "available": availability["available"],
            "provider_ok": availability["provider_ok"],
            "package_ok": availability["package_ok"],
            "model_exists": availability["model_exists"],
            "provider": settings.vision_provider,
            "model": self.model_path.name,
            "model_path": str(self.model_path),
            "model_path_source": self.model_path_source,
            "configured_model_path": settings.vision_model_path,
            "device": settings.vision_device,
            "imgsz": settings.vision_imgsz,
            "classes": self.classes,
            "detections": self.detections,
            "loaded": self.loaded,
            "inference_ms": round(self.inference_ms, 1),
            "error": self.error,
        }

    async def start(self, frame_provider: FrameProvider, announce: Announce) -> None:
        self._frame_provider = frame_provider
        self._announce = announce
        if self._task is None:
            self._task = asyncio.create_task(self._run(), name="local-yolo-vision-worker")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        self._model = None
        self.loaded = False

    def configure(self, enabled: bool, classes: list[str]) -> dict[str, object]:
        if classes:
            normalized = [item.strip().lower() for item in classes if item.strip()]
            self.classes = list(dict.fromkeys(normalized))[:80]

        self.enabled = bool(enabled and self.available)
        if enabled and not self.available:
            availability = self.availability()
            problems = []
            if not availability["provider_ok"]:
                problems.append(f"VISION_PROVIDER={settings.vision_provider!r}")
            if not availability["package_ok"]:
                problems.append("ultralytics is not installed in project .venv")
            if not availability["model_exists"]:
                problems.append(f"model file not found: {self.model_path}")
            self.error = "Local detector is unavailable: " + "; ".join(problems)
            log_event("WARNING", "vision", "Local detector requested but unavailable", {
                "provider": settings.vision_provider,
                "model_path": str(self.model_path),
            })
        else:
            self.error = ""
            log_event("INFO", "vision", "Vision configuration changed", {
                "enabled": self.enabled,
                "provider": settings.vision_provider,
                "classes": self.classes,
            })
        return self.status()

    def _load_model_sync(self) -> Any:
        if self._model is not None:
            return self._model

        os.environ.setdefault("OMP_NUM_THREADS", str(max(1, settings.vision_cpu_threads)))
        os.environ.setdefault("MKL_NUM_THREADS", str(max(1, settings.vision_cpu_threads)))

        from ultralytics import YOLO

        try:
            import torch
            torch.set_num_threads(max(1, settings.vision_cpu_threads))
            with suppress(RuntimeError):
                torch.set_num_interop_threads(1)
        except Exception:
            pass

        self._model = YOLO(str(self.model_path))
        self.loaded = True
        log_event("INFO", "vision", "Local YOLO model loaded on Acer", {
            "model": str(self.model_path),
            "device": settings.vision_device,
            "imgsz": settings.vision_imgsz,
            "threads": settings.vision_cpu_threads,
        })
        return self._model

    def _recognize_sync(self, jpeg: bytes) -> list[dict[str, Any]]:
        model = self._load_model_sync()
        image = cv2.imdecode(np.frombuffer(jpeg, dtype=np.uint8), cv2.IMREAD_COLOR)
        if image is None:
            raise RuntimeError("Could not decode camera JPEG for local detection")

        started = time.perf_counter()
        results = model.predict(
            source=image,
            imgsz=settings.vision_imgsz,
            conf=settings.vision_min_confidence,
            device=settings.vision_device,
            max_det=24,
            verbose=False,
        )
        self.inference_ms = (time.perf_counter() - started) * 1000.0

        if not results:
            return []
        result = results[0]
        boxes = getattr(result, "boxes", None)
        if boxes is None or len(boxes) == 0:
            return []

        names = getattr(result, "names", {}) or {}
        allowed = set(self.classes)
        xyxyn = boxes.xyxyn.cpu().numpy()
        confidences = boxes.conf.cpu().numpy()
        class_ids = boxes.cls.cpu().numpy().astype(int)

        detections: list[dict[str, Any]] = []
        for coords, confidence, class_id in zip(xyxyn, confidences, class_ids):
            raw_label = str(names.get(int(class_id), class_id)).strip().lower()
            label = _ALIASES.get(raw_label, raw_label)
            if allowed and label not in allowed:
                continue
            x1, y1, x2, y2 = [float(value) for value in coords]
            detections.append({
                "label": label,
                "confidence": round(float(confidence), 3),
                "x": round(max(0.0, min(1.0, x1)), 4),
                "y": round(max(0.0, min(1.0, y1)), 4),
                "width": round(max(0.0, min(1.0, x2 - x1)), 4),
                "height": round(max(0.0, min(1.0, y2 - y1)), 4),
            })
        return detections

    async def _announce_new_objects(self, labels: tuple[str, ...]) -> None:
        if self._announce is None:
            return
        new_labels = [label for label in labels if label not in self._last_labels]
        if not new_labels:
            return
        first = new_labels[0]
        spoken = _LABEL_RU.get(first, first)
        await self._announce(f"Создатель, вижу {spoken}.", "observation", 6.0)

    async def _run(self) -> None:
        while True:
            if not self.enabled or self._frame_provider is None:
                await asyncio.sleep(0.35)
                continue
            try:
                jpeg = await self._frame_provider()
                if not jpeg:
                    await asyncio.sleep(0.6)
                    continue
                detections = await asyncio.to_thread(self._recognize_sync, jpeg)
                labels = tuple(sorted({str(item["label"]) for item in detections}))
                if labels != self._last_labels:
                    log_event("INFO", "vision", "Visible object set changed", {
                        "detections": detections,
                        "inference_ms": round(self.inference_ms, 1),
                    })
                    await self._announce_new_objects(labels)
                self._last_labels = labels
                self.detections = detections
                self.error = ""
            except Exception as exc:
                self.error = str(exc)
                log_event("ERROR", "vision", "Local detection failed", {"error": str(exc)})
            await asyncio.sleep(max(0.35, settings.vision_interval_s))


vision = VisionManager()
