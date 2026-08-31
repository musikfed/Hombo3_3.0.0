"""Compact local RAG + explicit robot graph for Hermes.

Important: event logs may themselves contain old LLM inputs/contexts. Feeding those
back verbatim recursively grows the prompt. Retrieval therefore returns a compact,
non-recursive event view and never embeds previous agent contexts or hardware graphs.
"""
from __future__ import annotations

import json
import re
from typing import Any

from .database import list_events
from .tuning import tuning_store
from .skills import skill_store
from .mapping import mapping

_TOKEN = re.compile(r"[0-9A-Za-zА-Яа-яЁё_+-]{3,}")

# Keys that can recursively contain previous RAG/LLM contexts or very large blobs.
_SKIP_KEYS = {
    "context",
    "input",
    "response_schema",
    "hardware_graph",
    "retrieved_memory",
    "retrieved_skills",
    "messages",
    "prompt",
    "frame",
    "image",
    "pcm",
    "audio",
}

ROBOT_GRAPH: dict[str, Any] = {
    "nodes": [
        {"id": "robot", "type": "mobile_robot", "label": "робот-машинка"},
        {"id": "esp32", "type": "controller", "label": "ESP32-S3-DevKitC-1 N16R8"},
        {"id": "left_side", "type": "drive_side", "label": "левый борт, два мотора"},
        {"id": "right_side", "type": "drive_side", "label": "правый борт, два мотора"},
        {"id": "tb6612_left", "type": "motor_driver", "label": "левый TB6612: канал A = FL, канал B = BL, общая команда борта"},
        {"id": "tb6612_right", "type": "motor_driver", "label": "правый TB6612: канал A = FR, канал B = BR, общая команда борта"},
        {"id": "front_hc", "type": "range_sensor", "label": "HC-SR04 передний"},
        {"id": "rear_hc", "type": "range_sensor", "label": "HC-SR04 задний"},
        {"id": "third_hc", "type": "range_sensor", "label": "HC-SR04 третий"},
        {"id": "tof", "type": "range_sensor", "label": "VL53L0X"},
        {"id": "camera", "type": "ip_camera", "label": "REGGO ONVIF"},
        {"id": "speaker", "type": "audio_output", "label": "MAX98357A + динамик"},
        {"id": "acer", "type": "edge_computer", "label": "Acer Swift 3"},
        {"id": "hermes", "type": "llm", "label": "Hermes 4 14B через Ollama на Huananzhi"},
        {"id": "vector_probe", "type": "spatial_engine", "label": "Hombo VectorProbe: эталонная + живая + семантическая карта"},
        {"id": "reference_map", "type": "map_layer", "label": "подтвержденные стены, проходы, зоны и якоря"},
        {"id": "live_map", "type": "map_layer", "label": "дальномерные лучи, временные препятствия и треки"},
        {"id": "inventory", "type": "semantic_memory", "label": "объекты, изменения, временные и динамические сущности"},
    ],
    "edges": [
        ["esp32", "controls", "left_side"],
        ["esp32", "controls", "right_side"],
        ["tb6612_left", "drives", "left_side"],
        ["tb6612_right", "drives", "right_side"],
        ["front_hc", "reports_to", "esp32"],
        ["rear_hc", "reports_to", "esp32"],
        ["third_hc", "reports_to", "esp32"],
        ["tof", "reports_to", "esp32"],
        ["camera", "streams_to", "acer"],
        ["acer", "runs_local_vision", "camera"],
        ["acer", "queries", "hermes"],
        ["acer", "sends_audio", "speaker"],
        ["esp32", "owns", "watchdog_and_obstacle_stop"],
        ["acer", "runs", "vector_probe"],
        ["vector_probe", "fuses", "reference_map"],
        ["vector_probe", "fuses", "live_map"],
        ["vector_probe", "maintains", "inventory"],
        ["reference_map", "contains", "named_zones"],
        ["agent", "uses", "semantic_mcp_tools"],
        ["camera", "microphone_streams_to", "acer"],
        ["speaker", "driven_by", "max98357a"],
    ],
}


def _terms(text: str) -> set[str]:
    return {token.lower() for token in _TOKEN.findall(text)}


def _compact_value(value: Any, depth: int = 0) -> Any:
    """Bound log payload size and remove recursive agent material."""
    if depth >= 3:
        if isinstance(value, (dict, list, tuple)):
            return "[nested omitted]"
        return value
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        text = " ".join(value.split())
        return text if len(text) <= 320 else text[:317] + "..."
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, item in list(value.items())[:24]:
            key_s = str(key)
            if key_s.lower() in _SKIP_KEYS:
                continue
            out[key_s] = _compact_value(item, depth + 1)
            if len(out) >= 12:
                break
        return out
    if isinstance(value, (list, tuple)):
        return [_compact_value(item, depth + 1) for item in list(value)[:6]]
    return _compact_value(str(value), depth + 1)


def _compact_event(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": item.get("id"),
        "timestamp": item.get("timestamp", ""),
        "level": item.get("level", ""),
        "category": item.get("category", ""),
        "message": _compact_value(item.get("message", "")),
        "payload": _compact_value(item.get("payload", {})),
    }


def retrieve_events(query: str, limit: int = 6) -> list[dict[str, Any]]:
    terms = _terms(query)
    raw_events = list_events(250)
    compact = [_compact_event(item) for item in raw_events]

    # Never feed LLM transport diagnostics back into the LLM as memory.
    compact = [
        item for item in compact
        if not (item.get("category") == "ollama" and item.get("level") in {"ERROR", "DEBUG"})
    ]

    if not terms:
        return compact[:limit]

    scored: list[tuple[int, int, dict[str, Any]]] = []
    for item in compact:
        hay = json.dumps(item, ensure_ascii=False).lower()
        score = sum(1 for term in terms if term in hay)
        if score:
            scored.append((score, int(item.get("id") or 0), item))
    scored.sort(key=lambda row: (row[0], row[1]), reverse=True)
    return [item for _, _, item in scored[:limit]]


def build_agent_context(query: str, telemetry: dict[str, Any], vision_status: dict[str, Any]) -> dict[str, Any]:
    tuning = tuning_store.list()
    return {
        "active_tuning": tuning["current"],
        "tuning_revision": tuning["revision"],
        "hardware_graph": ROBOT_GRAPH,
        "retrieved_memory": retrieve_events(query, 6),
        "retrieved_skills": skill_store.relevant(query),
        "skills_version": skill_store.list().get("version", 1),
        "telemetry": _compact_value(telemetry),
        "map": {
            "engine": "Hombo VectorProbe",
            "pose": mapping.pose(),
            "zones": _compact_value(mapping.zones),
            "reference_walls": _compact_value(mapping.walls[-80:]),
            "reference_anchors": _compact_value(mapping.anchors[-80:]),
            "semantic_objects": _compact_value(mapping.objects[-60:]),
            "route": _compact_value(mapping.route[-40:]),
            "inventory": _compact_value(mapping.inventory_summary()),
            "recent_changes": _compact_value(mapping.changes[-20:]),
        },
        "vision": {
            "enabled": vision_status.get("enabled", False),
            "available": vision_status.get("available", False),
            "provider": vision_status.get("provider", ""),
            "detections": _compact_value(vision_status.get("detections", [])),
            "error": _compact_value(vision_status.get("error", "")),
        },
    }
