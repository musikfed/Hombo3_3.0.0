"""Operator-confirmed local visual memory. This is NOT neural weight training.

Only verified notes are stored by default. JPEG exemplars require separate
configuration and confirmation; all records remain under Hombo3/data.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sqlite3
import threading
from uuid import uuid4

_IDENT = re.compile(r"[0-9a-f]{32}\Z")


class VisualMemory:
    def __init__(self, db: Path, image_dir: Path):
        self.db = Path(db)
        self.images = Path(image_dir)
        self._lock = threading.RLock()
        self.db.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute("""CREATE TABLE IF NOT EXISTS visual_memories (
                id TEXT PRIMARY KEY, created_utc TEXT NOT NULL,
                label TEXT NOT NULL, note TEXT NOT NULL,
                detected_json TEXT NOT NULL, image_saved INTEGER NOT NULL DEFAULT 0
            )""")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_visual_created ON visual_memories(created_utc)")

    def _connect(self):
        conn = sqlite3.connect(self.db, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    def remember(self, label: str, note: str, detections: list[dict],
                 jpeg: bytes | None = None, *, save_image: bool = False) -> dict:
        label = " ".join(label.split())[:90]
        note = " ".join(note.split())[:500]
        if not label:
            raise ValueError("A human-confirmed object label is required")
        if save_image and (not jpeg or not jpeg.startswith(b"\xff\xd8") or len(jpeg) > 3_000_000):
            raise ValueError("No valid bounded image to remember")
        ident = uuid4().hex
        image_path = self.images / (ident + ".jpg")
        saved = False
        with self._lock:
            try:
                if save_image:
                    self.images.mkdir(parents=True, exist_ok=True)
                    fd = os.open(image_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                    with os.fdopen(fd, "wb") as output:
                        output.write(jpeg)
                    saved = True
                with self._connect() as conn:
                    conn.execute("INSERT INTO visual_memories VALUES(?,?,?,?,?,?)", (
                        ident, datetime.now(timezone.utc).isoformat(), label, note,
                        json.dumps(detections[:30], ensure_ascii=False), int(saved),
                    ))
                    conn.commit()
            except Exception:
                if saved:
                    image_path.unlink(missing_ok=True)
                raise
        return {"id": ident, "label": label, "note": note, "image_saved": saved}

    def list(self, limit: int = 12) -> list[dict]:
        limit = max(1, min(50, int(limit)))
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                "SELECT id,created_utc,label,note,image_saved FROM visual_memories ORDER BY created_utc DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def delete(self, ident: str) -> bool:
        if not _IDENT.fullmatch(ident):
            raise ValueError("Invalid memory id")
        with self._lock, self._connect() as conn:
            result = conn.execute("DELETE FROM visual_memories WHERE id=?", (ident,))
            conn.commit()
        if result.rowcount:
            path = self.images / (ident + ".jpg")
            if not path.is_symlink():
                path.unlink(missing_ok=True)
        return bool(result.rowcount)

    def match_scene(self, jpeg: bytes, limit: int = 12) -> list[dict]:
        """Conservative ORB matching of *scenes*, not guaranteed object identity."""
        if not jpeg.startswith(b"\xff\xd8") or len(jpeg) > 3_000_000:
            return []
        try:
            import cv2
            import numpy as np
            current = cv2.imdecode(np.frombuffer(jpeg, dtype=np.uint8), cv2.IMREAD_GRAYSCALE)
            if current is None:
                return []
            orb = cv2.ORB_create(nfeatures=300)
            _, current_desc = orb.detectAndCompute(current, None)
            if current_desc is None or len(current_desc) < 18:
                return []
            with self._lock, self._connect() as conn:
                rows = conn.execute(
                    "SELECT id,label,note FROM visual_memories WHERE image_saved=1 ORDER BY created_utc DESC LIMIT ?",
                    (max(1, min(30, int(limit))),),
                ).fetchall()
            matcher = cv2.BFMatcher(cv2.NORM_HAMMING)
            matches = []
            for item in rows:
                path = self.images / (item["id"] + ".jpg")
                if path.is_symlink() or not path.is_file():
                    continue
                older = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
                if older is None:
                    continue
                _, old_desc = orb.detectAndCompute(older, None)
                if old_desc is None or len(old_desc) < 18:
                    continue
                pairs = matcher.knnMatch(current_desc, old_desc, k=2)
                good = sum(1 for pair in pairs if len(pair) == 2 and pair[0].distance < .68 * pair[1].distance)
                if good >= 18:
                    matches.append({"id": item["id"], "label": item["label"],
                                    "note": item["note"], "orb_good_matches": good,
                                    "verified_identity": False})
            return sorted(matches, key=lambda item: item["orb_good_matches"], reverse=True)[:3]
        except (OSError, ValueError):
            return []
