"""SQLite event log, telemetry snapshots and JSONL dataset exporter.

All persistent logs are written on Acer. ESP32 keeps only live state and small
buffers required for control and audio playback.
"""
from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from typing import Any

from .config import settings

_lock = threading.Lock()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _connect() -> sqlite3.Connection:
    connection = sqlite3.connect(settings.database_path)
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA synchronous=NORMAL")
    return connection


def init_database() -> None:
    settings.database_path.parent.mkdir(parents=True, exist_ok=True)
    settings.dataset_path.parent.mkdir(parents=True, exist_ok=True)
    with _connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                level TEXT NOT NULL,
                category TEXT NOT NULL,
                message TEXT NOT NULL,
                payload_json TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(timestamp);
            CREATE INDEX IF NOT EXISTS idx_events_category ON events(category);

            CREATE TABLE IF NOT EXISTS telemetry_samples (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                payload_json TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_telemetry_timestamp ON telemetry_samples(timestamp);
            """
        )
        conn.commit()


def log_event(level: str, category: str, message: str, payload: dict[str, Any] | None = None) -> None:
    record = payload or {}
    with _lock, _connect() as conn:
        conn.execute(
            "INSERT INTO events(timestamp, level, category, message, payload_json) VALUES(?,?,?,?,?)",
            (_utc_now(), level, category, message, json.dumps(record, ensure_ascii=False)),
        )
        conn.commit()


def log_telemetry(payload: dict[str, Any]) -> None:
    with _lock, _connect() as conn:
        conn.execute(
            "INSERT INTO telemetry_samples(timestamp, payload_json) VALUES(?,?)",
            (_utc_now(), json.dumps(payload, ensure_ascii=False, separators=(",", ":"))),
        )
        conn.commit()


def list_events(limit: int = 200, category: str = "") -> list[dict[str, Any]]:
    limit = max(1, min(limit, 2000))
    with _connect() as conn:
        conn.row_factory = sqlite3.Row
        if category:
            rows = conn.execute(
                "SELECT id,timestamp,level,category,message,payload_json FROM events WHERE category=? ORDER BY id DESC LIMIT ?",
                (category, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT id,timestamp,level,category,message,payload_json FROM events ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
    result: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        item["payload"] = json.loads(item.pop("payload_json"))
        result.append(item)
    return result


def append_dataset_record(record: dict[str, Any]) -> None:
    """Append a validated interaction for future skill analysis/model training."""
    line = json.dumps({"timestamp": _utc_now(), **record}, ensure_ascii=False)
    with _lock, settings.dataset_path.open("a", encoding="utf-8") as file:
        file.write(line + "\n")
