"""Hombo3 VectorProbe: fused spatial memory for a known indoor environment.

The engine intentionally does *not* pretend that PWM dead reckoning is precise.
Instead it keeps several layers and lets each layer do the job it is good at:

* reference map: operator-drawn walls, doors, zones and confirmed anchors;
* vector observations: real HC-SR04 / ToF rays collected while the robot moves;
* live pose: short-term PWM dead reckoning corrected against the reference map;
* semantic inventory: YOLO observations split into dynamic/temporary/static candidates;
* trail and route: where the robot moved and the currently planned path.

This is the "vector probe" concept discussed for Hombo3: the robot repeatedly probes
known geometry and allows stable coordinates to push its drifting pose back into a
plausible location. All corrections expose a confidence value and correction metadata.
"""
from __future__ import annotations

import heapq
import json
import math
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from .config import settings
from .database import log_event


def _norm_deg(value: float) -> float:
    return (value + 180.0) % 360.0 - 180.0


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _cross(ax: float, ay: float, bx: float, by: float) -> float:
    return ax * by - ay * bx


def _ray_segment_distance(
    ox: float,
    oy: float,
    angle_deg: float,
    ax: float,
    ay: float,
    bx: float,
    by: float,
) -> float | None:
    """Distance from ray origin to segment intersection, or None."""
    angle = math.radians(angle_deg)
    dx, dy = math.cos(angle), math.sin(angle)
    vx, vy = bx - ax, by - ay
    den = _cross(dx, dy, vx, vy)
    if abs(den) < 1e-9:
        return None
    qx, qy = ax - ox, ay - oy
    t = _cross(qx, qy, vx, vy) / den
    u = _cross(qx, qy, dx, dy) / den
    if t >= 0.0 and 0.0 <= u <= 1.0:
        return t
    return None


def _point_segment_distance(px: float, py: float, ax: float, ay: float, bx: float, by: float) -> float:
    vx, vy = bx - ax, by - ay
    wx, wy = px - ax, py - ay
    vv = vx * vx + vy * vy
    if vv <= 1e-12:
        return math.hypot(px - ax, py - ay)
    t = _clamp((wx * vx + wy * vy) / vv, 0.0, 1.0)
    cx, cy = ax + t * vx, ay + t * vy
    return math.hypot(px - cx, py - cy)


def _point_in_polygon(x: float, y: float, points: list[dict[str, float]]) -> bool:
    inside = False
    j = len(points) - 1
    for i, p in enumerate(points):
        pi, pj = p, points[j]
        xi, yi = float(pi["x_m"]), float(pi["y_m"])
        xj, yj = float(pj["x_m"]), float(pj["y_m"])
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / ((yj - yi) or 1e-12) + xi):
            inside = not inside
        j = i
    return inside


def _dist(a: dict[str, Any], b: dict[str, Any]) -> float:
    return math.hypot(float(a.get("x_m", 0.0)) - float(b.get("x_m", 0.0)), float(a.get("y_m", 0.0)) - float(b.get("y_m", 0.0)))


_DYNAMIC_LABELS = {"person", "cat", "dog"}
_TEMPORARY_LABELS = {
    "chair", "bottle", "cup", "backpack", "laptop", "phone", "bicycle", "car",
    "suitcase", "handbag", "book", "box",
}
_STATIC_CANDIDATE_LABELS = {
    "sofa", "couch", "tv", "television", "refrigerator", "bed", "oven", "sink",
    "cabinet", "door", "window",
}


@dataclass
class VectorProbeEngine:
    path: Path = settings.map_state_path
    enabled: bool = True
    x_m: float = 0.0
    y_m: float = 0.0
    heading_deg: float = 0.0
    confidence: float = 0.72

    zones: list[dict[str, Any]] = field(default_factory=list)
    walls: list[dict[str, Any]] = field(default_factory=list)
    anchors: list[dict[str, Any]] = field(default_factory=list)
    rays: list[dict[str, Any]] = field(default_factory=list)
    objects: list[dict[str, Any]] = field(default_factory=list)
    trail: list[dict[str, Any]] = field(default_factory=list)
    route: list[dict[str, float]] = field(default_factory=list)
    changes: list[dict[str, Any]] = field(default_factory=list)

    _last_update: float = field(default_factory=time.monotonic, init=False)
    _last_semantic_at: float = field(default=0.0, init=False)
    _last_save_at: float = field(default_factory=time.monotonic, init=False)
    _last_trail_at: float = field(default=0.0, init=False)
    _last_correction: dict[str, Any] = field(default_factory=dict, init=False)
    _last_pose_source: str = field(default="pwm_dead_reckoning", init=False)

    def __post_init__(self) -> None:
        self.load()

    # ------------------------------------------------------------------ persistence
    def load(self) -> None:
        try:
            data = json.loads(self.path.read_text("utf-8"))
        except Exception:
            return
        pose = data.get("pose", {})
        self.x_m = float(pose.get("x_m", 0.0))
        self.y_m = float(pose.get("y_m", 0.0))
        self.heading_deg = float(pose.get("heading_deg", 0.0))
        self.confidence = float(pose.get("confidence", 0.72))
        self.zones = list(data.get("zones", []))[:200]
        self.walls = list(data.get("walls", []))[:800]
        self.anchors = list(data.get("anchors", []))[:500]
        self.rays = list(data.get("rays", []))[-5000:]
        self.objects = list(data.get("objects", []))[-1200:]
        self.trail = list(data.get("trail", []))[-6000:]
        self.route = list(data.get("route", []))[:1000]
        self.changes = list(data.get("changes", []))[-600:]
        # Migration from HomboWiFi 2.5 endpoint-only points.
        if not self.rays and data.get("points"):
            for p in list(data.get("points", []))[-2500:]:
                self.rays.append({
                    "ox_m": self.x_m, "oy_m": self.y_m,
                    "x_m": float(p.get("x_m", 0.0)), "y_m": float(p.get("y_m", 0.0)),
                    "distance_m": 0.0, "angle_deg": 0.0,
                    "source": p.get("source", "legacy"), "t": p.get("t", time.time()),
                    "weight": 0.25,
                })

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 3,
            "pose": self.pose(),
            "zones": self.zones,
            "walls": self.walls,
            "anchors": self.anchors,
            "rays": self.rays[-5000:],
            "objects": self.objects[-1200:],
            "trail": self.trail[-6000:],
            "route": self.route[:1000],
            "changes": self.changes[-600:],
        }
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), "utf-8")
        tmp.replace(self.path)

    # ------------------------------------------------------------------ public state
    def pose(self) -> dict[str, Any]:
        return {
            "x_m": round(self.x_m, 3),
            "y_m": round(self.y_m, 3),
            "heading_deg": round(_norm_deg(self.heading_deg), 1),
            "confidence": round(_clamp(self.confidence, 0.0, 1.0), 3),
            "source": self._last_pose_source,
            "last_correction": self._last_correction,
        }

    @property
    def points(self) -> list[dict[str, Any]]:
        """Compatibility endpoint list used by old UI/RAG."""
        return [
            {"x_m": r.get("x_m", 0.0), "y_m": r.get("y_m", 0.0), "source": r.get("source", ""), "t": r.get("t", 0)}
            for r in self.rays[-3000:]
        ]

    def state(self) -> dict[str, Any]:
        now = time.time()
        active_objects = []
        for obj in self.objects[-800:]:
            age = max(0.0, now - float(obj.get("last_seen", now)))
            item = dict(obj)
            item["age_s"] = round(age, 1)
            if item.get("status") == "dynamic":
                item["active"] = age <= 20.0
            elif item.get("status") == "temporary":
                item["active"] = age <= 6 * 3600
            else:
                item["active"] = True
            active_objects.append(item)
        return {
            "engine": "Hombo VectorProbe",
            "enabled": self.enabled,
            "pose": self.pose(),
            "points": self.points[-2500:],
            "rays": self.rays[-1400:],
            "trail": self.trail[-3000:],
            "objects": active_objects[-500:],
            "zones": self.zones,
            "walls": self.walls,
            "anchors": self.anchors,
            "route": self.route,
            "changes": self.changes[-120:],
            "inventory": self.inventory_summary(),
            "meta": {
                "track_width_mm": settings.track_width_mm,
                "wheel_diameter_mm": settings.wheel_diameter_mm,
                "pose_is_fused_estimate": True,
                "reference_geometry_count": len(self.walls),
                "reference_anchor_count": len(self.anchors),
                "vector_probe_ready": len(self.walls) >= 2,
                "note": "PWM odometry drifts; VectorProbe corrects it against operator-confirmed geometry and landmarks.",
            },
        }

    def reset(self) -> dict[str, Any]:
        """Reset live/operational layers but preserve the operator's reference map."""
        self.x_m = self.y_m = self.heading_deg = 0.0
        self.confidence = 0.72
        self.rays.clear()
        self.objects.clear()
        self.trail.clear()
        self.route.clear()
        self.changes.clear()
        self._last_pose_source = "manual_reset"
        self._last_correction = {}
        self.save()
        log_event("WARNING", "vector_probe", "Live VectorProbe layers reset; reference map preserved", {})
        return self.state()

    def clear_reference(self) -> dict[str, Any]:
        self.zones.clear(); self.walls.clear(); self.anchors.clear(); self.route.clear()
        self.save()
        log_event("WARNING", "vector_probe", "Reference map cleared", {})
        return self.state()

    def set_pose(self, x_m: float, y_m: float, heading_deg: float) -> dict[str, Any]:
        self.x_m = float(x_m)
        self.y_m = float(y_m)
        self.heading_deg = _norm_deg(float(heading_deg))
        self.confidence = 0.98
        self._last_pose_source = "manual_reference"
        self._last_correction = {"kind": "manual", "at": round(time.time(), 2)}
        self._append_trail(force=True)
        self.save()
        log_event("INFO", "vector_probe", "Pose corrected manually", self.pose())
        return self.pose()

    # ------------------------------------------------------------------ reference map
    @staticmethod
    def _point(item: dict[str, Any]) -> dict[str, float]:
        return {"x_m": round(float(item.get("x_m", 0.0)), 3), "y_m": round(float(item.get("y_m", 0.0)), 3)}

    def add_zone(self, zone: dict[str, Any]) -> dict[str, Any]:
        name = str(zone.get("name", "")).strip()
        kind = str(zone.get("kind", "room")).strip() or "room"
        pts = [self._point(item) for item in list(zone.get("points", []))[:64] if isinstance(item, dict)]
        if not name or len(pts) < 3:
            raise ValueError("zone requires name and at least 3 points")
        zid = str(zone.get("id") or f"zone-{int(time.time()*1000)}")
        record = {"id": zid, "name": name, "kind": kind, "points": pts}
        self.zones = [z for z in self.zones if z.get("id") != zid]
        self.zones.append(record)
        self.save()
        log_event("INFO", "vector_probe", "Reference zone saved", record)
        return record

    def delete_zone(self, zone_id: str) -> None:
        self.zones = [z for z in self.zones if z.get("id") != zone_id]
        self.save()

    def add_wall(self, wall: dict[str, Any]) -> dict[str, Any]:
        name = str(wall.get("name", "")).strip() or "стена"
        kind = str(wall.get("kind", "wall")).strip() or "wall"
        a = self._point(dict(wall.get("a") or {})); b = self._point(dict(wall.get("b") or {}))
        if math.hypot(a["x_m"] - b["x_m"], a["y_m"] - b["y_m"]) < 0.05:
            raise ValueError("wall segment must be at least 5 cm")
        wid = str(wall.get("id") or f"wall-{int(time.time()*1000)}")
        record = {"id": wid, "name": name, "kind": kind, "a": a, "b": b, "enabled": bool(wall.get("enabled", True))}
        self.walls = [w for w in self.walls if w.get("id") != wid]
        self.walls.append(record)
        self.save()
        log_event("INFO", "vector_probe", "Reference segment saved", record)
        return record

    def delete_wall(self, wall_id: str) -> None:
        self.walls = [w for w in self.walls if w.get("id") != wall_id]
        self.save()

    def add_anchor(self, anchor: dict[str, Any]) -> dict[str, Any]:
        label = str(anchor.get("label", "")).strip().lower()
        name = str(anchor.get("name", "")).strip() or label
        if not label:
            raise ValueError("anchor label is required")
        aid = str(anchor.get("id") or f"anchor-{int(time.time()*1000)}")
        record = {
            "id": aid, "label": label, "name": name,
            "x_m": round(float(anchor.get("x_m", 0.0)), 3),
            "y_m": round(float(anchor.get("y_m", 0.0)), 3),
            "kind": str(anchor.get("kind", "static"))[:32],
            "confidence": round(_clamp(float(anchor.get("confidence", 1.0)), 0.0, 1.0), 3),
            "notes": str(anchor.get("notes", ""))[:300],
        }
        self.anchors = [a for a in self.anchors if a.get("id") != aid]
        self.anchors.append(record)
        self.save()
        log_event("INFO", "vector_probe", "Reference anchor saved", record)
        return record

    def delete_anchor(self, anchor_id: str) -> None:
        self.anchors = [a for a in self.anchors if a.get("id") != anchor_id]
        self.save()

    def promote_object(self, object_id: str, name: str = "") -> dict[str, Any]:
        obj = next((o for o in self.objects if o.get("id") == object_id), None)
        if not obj:
            raise ValueError("semantic object not found")
        anchor = self.add_anchor({
            "label": obj.get("label", "object"),
            "name": name or obj.get("label", "object"),
            "x_m": obj.get("x_m", 0.0), "y_m": obj.get("y_m", 0.0),
            "kind": "confirmed_object", "confidence": obj.get("confidence", 0.8),
            "notes": f"promoted from {object_id}",
        })
        obj["status"] = "confirmed_static"
        obj["anchor_id"] = anchor["id"]
        self.save()
        return anchor

    def resolve_zone(self, name: str) -> dict[str, Any] | None:
        needle = name.strip().lower()
        for zone in self.zones:
            if str(zone.get("name", "")).lower() == needle or str(zone.get("id", "")).lower() == needle:
                pts = zone.get("points", [])
                if pts:
                    cx = sum(float(p.get("x_m", 0.0)) for p in pts) / len(pts)
                    cy = sum(float(p.get("y_m", 0.0)) for p in pts) / len(pts)
                else:
                    cx = cy = 0.0
                return {**zone, "target": {"x_m": round(cx, 3), "y_m": round(cy, 3)}}
        return None

    # ------------------------------------------------------------------ vector observations
    def _append_trail(self, force: bool = False) -> None:
        now = time.monotonic()
        if not force and now - self._last_trail_at < 0.18:
            return
        self._last_trail_at = now
        p = {"x_m": round(self.x_m, 3), "y_m": round(self.y_m, 3), "heading_deg": round(self.heading_deg, 1), "t": round(time.time(), 2)}
        if self.trail and not force:
            last = self.trail[-1]
            if math.hypot(p["x_m"] - float(last.get("x_m", 0.0)), p["y_m"] - float(last.get("y_m", 0.0))) < 0.012 and abs(_norm_deg(p["heading_deg"] - float(last.get("heading_deg", 0.0)))) < 1.5:
                return
        self.trail.append(p)
        if len(self.trail) > 7000:
            del self.trail[:1000]

    def _add_ray(self, distance_m: float, relative_angle_deg: float, source: str, weight: float = 1.0) -> dict[str, Any] | None:
        if distance_m <= 0.03 or distance_m > 6.0:
            return None
        angle_deg = _norm_deg(self.heading_deg + relative_angle_deg)
        angle = math.radians(angle_deg)
        px = self.x_m + distance_m * math.cos(angle)
        py = self.y_m + distance_m * math.sin(angle)
        record = {
            "ox_m": round(self.x_m, 3), "oy_m": round(self.y_m, 3),
            "x_m": round(px, 3), "y_m": round(py, 3),
            "distance_m": round(distance_m, 3), "angle_deg": round(angle_deg, 1),
            "relative_angle_deg": round(relative_angle_deg, 1),
            "source": source, "weight": round(weight, 2), "t": round(time.time(), 2),
        }
        self.rays.append(record)
        if len(self.rays) > 6000:
            del self.rays[:1200]
        return record

    def _expected_range(self, x_m: float, y_m: float, angle_deg: float, max_range: float = 6.0) -> float | None:
        best: float | None = None
        for wall in self.walls:
            if not wall.get("enabled", True):
                continue
            # Door/reference markers help localization but an explicitly open doorway is
            # not treated as a blocking surface.
            if str(wall.get("kind", "wall")) in {"door_open", "opening"}:
                continue
            a, b = wall.get("a", {}), wall.get("b", {})
            d = _ray_segment_distance(x_m, y_m, angle_deg, float(a.get("x_m", 0)), float(a.get("y_m", 0)), float(b.get("x_m", 0)), float(b.get("y_m", 0)))
            if d is not None and 0.03 < d <= max_range and (best is None or d < best):
                best = d
        return best

    def _pose_score(self, x: float, y: float, heading: float, measurements: list[dict[str, float]]) -> tuple[float, int]:
        total = 0.0; used = 0
        for m in measurements:
            expected = self._expected_range(x, y, heading + m["relative_angle_deg"], max_range=max(2.0, m["distance_m"] + 1.5))
            weight = m.get("weight", 1.0)
            if expected is None:
                total += 0.65 * weight
                continue
            # Huber-ish residual: do not let one bad ultrasonic echo dominate.
            err = abs(expected - m["distance_m"])
            total += (err if err < 0.45 else 0.45 + (err - 0.45) * 0.25) * weight
            used += 1
        if not measurements:
            return 99.0, 0
        return total / max(0.25, sum(m.get("weight", 1.0) for m in measurements)), used

    def _correct_pose_from_walls(self, measurements: list[dict[str, float]]) -> None:
        if len(self.walls) < 2 or len(measurements) < 2:
            return
        current_score, current_used = self._pose_score(self.x_m, self.y_m, self.heading_deg, measurements)
        best = (current_score, self.x_m, self.y_m, self.heading_deg, current_used)
        # 9 x 9 x 7 = 567 candidates; four rays and a small wall set keep this cheap on Acer.
        xy_steps = (-0.20, -0.15, -0.10, -0.05, 0.0, 0.05, 0.10, 0.15, 0.20)
        h_steps = (-10.0, -6.0, -3.0, 0.0, 3.0, 6.0, 10.0)
        for dx in xy_steps:
            for dy in xy_steps:
                for dh in h_steps:
                    if dx == dy == dh == 0:
                        continue
                    score, used = self._pose_score(self.x_m + dx, self.y_m + dy, self.heading_deg + dh, measurements)
                    # Gentle penalty keeps corrections local when scores are similar.
                    score += (abs(dx) + abs(dy)) * 0.025 + abs(dh) * 0.0007
                    if score < best[0]:
                        best = (score, self.x_m + dx, self.y_m + dy, _norm_deg(self.heading_deg + dh), used)
        best_score, bx, by, bh, used = best
        improvement = current_score - best_score
        if used < 2 or best_score > 0.42:
            return
        if improvement < 0.025 and self.confidence > 0.45:
            return
        strength = _clamp(0.25 + improvement * 0.8 + (0.45 - best_score) * 0.35, 0.25, 0.70)
        old = (self.x_m, self.y_m, self.heading_deg)
        self.x_m += (bx - self.x_m) * strength
        self.y_m += (by - self.y_m) * strength
        dh = _norm_deg(bh - self.heading_deg)
        self.heading_deg = _norm_deg(self.heading_deg + dh * strength)
        self.confidence = _clamp(self.confidence + 0.06 + improvement * 0.12, 0.0, 0.98)
        self._last_pose_source = "vector_probe_wall_fusion"
        self._last_correction = {
            "kind": "wall_match", "score": round(best_score, 3), "improvement": round(improvement, 3),
            "used_rays": used, "dx_m": round(self.x_m - old[0], 3), "dy_m": round(self.y_m - old[1], 3),
            "dheading_deg": round(_norm_deg(self.heading_deg - old[2]), 2), "at": round(time.time(), 2),
        }

    # ------------------------------------------------------------------ semantics / inventory
    @staticmethod
    def _semantic_status(label: str) -> str:
        if label in _DYNAMIC_LABELS:
            return "dynamic"
        if label in _STATIC_CANDIDATE_LABELS:
            return "static_candidate"
        if label in _TEMPORARY_LABELS:
            return "temporary"
        return "temporary"

    def _record_change(self, kind: str, obj: dict[str, Any], extra: dict[str, Any] | None = None) -> None:
        event = {
            "id": f"chg-{int(time.time()*1000)}-{len(self.changes)%1000}",
            "kind": kind, "object_id": obj.get("id"), "label": obj.get("label"),
            "x_m": obj.get("x_m"), "y_m": obj.get("y_m"), "t": round(time.time(), 2),
            **(extra or {}),
        }
        # suppress repetitive change spam for the same object/kind
        if self.changes and self.changes[-1].get("kind") == kind and self.changes[-1].get("object_id") == obj.get("id") and time.time() - float(self.changes[-1].get("t", 0)) < 30:
            return
        self.changes.append(event)
        if len(self.changes) > 700:
            del self.changes[:100]
        log_event("INFO", "spatial_change", kind, event)

    def _semantic_anchor_correction(self, label: str, px: float, py: float, confidence: float) -> None:
        candidates = [a for a in self.anchors if str(a.get("label", "")).lower() == label]
        if not candidates or confidence < 0.62:
            return
        anchor = min(candidates, key=lambda a: math.hypot(float(a.get("x_m", 0)) - px, float(a.get("y_m", 0)) - py))
        dx = float(anchor.get("x_m", 0)) - px; dy = float(anchor.get("y_m", 0)) - py
        error = math.hypot(dx, dy)
        if error > 1.1:
            return
        strength = 0.08 + 0.10 * confidence
        self.x_m += dx * strength
        self.y_m += dy * strength
        self.confidence = _clamp(self.confidence + 0.018 * confidence, 0.0, 0.99)
        self._last_pose_source = "vector_probe_semantic_fusion"
        self._last_correction = {
            "kind": "semantic_anchor", "anchor_id": anchor.get("id"), "label": label,
            "residual_m": round(error, 3), "at": round(time.time(), 2),
        }

    def _update_semantics(self, vision_status: dict[str, Any], telemetry: dict[str, Any], head_angle_deg: float) -> None:
        now_mono = time.monotonic()
        if now_mono - self._last_semantic_at < 0.7:
            return
        self._last_semantic_at = now_mono
        detections = list(vision_status.get("detections", []) or [])[:24]
        if not detections:
            return
        distance_m = 0.0
        if telemetry.get("tof_ok") and float(telemetry.get("tof_mm", 0) or 0) > 0:
            distance_m = float(telemetry["tof_mm"]) / 1000.0
        elif float(telemetry.get("third_cm", 0) or 0) > 0:
            distance_m = float(telemetry["third_cm"]) / 100.0
        if not 0.05 < distance_m <= 5.0:
            return

        hfov = float(getattr(settings, "camera_hfov_deg", 72.0))
        now = time.time()
        for det in detections:
            confidence = float(det.get("confidence", 0.0) or 0.0)
            if confidence < 0.45:
                continue
            label = str(det.get("label", "object")).strip().lower()
            cx = float(det.get("x", 0.5) or 0.5) + float(det.get("width", 0.0) or 0.0) * 0.5
            offset = (cx - 0.5) * hfov
            alignment = max(0.0, 1.0 - abs(cx - 0.5) / 0.42)
            # The single ToF beam measures near the optical centre. Wide off-centre
            # detections remain visible to YOLO but are not assigned a fake distance.
            if alignment < 0.25:
                continue
            world_angle = _norm_deg(self.heading_deg + head_angle_deg + offset)
            angle = math.radians(world_angle)
            px = self.x_m + distance_m * math.cos(angle)
            py = self.y_m + distance_m * math.sin(angle)
            spatial_conf = confidence * (0.55 + 0.45 * alignment)
            status = self._semantic_status(label)
            radius = 1.0 if status == "dynamic" else 0.60
            candidates = [o for o in self.objects[-400:] if o.get("label") == label and math.hypot(float(o.get("x_m", 0)) - px, float(o.get("y_m", 0)) - py) < radius]
            existing = min(candidates, key=lambda o: math.hypot(float(o.get("x_m", 0)) - px, float(o.get("y_m", 0)) - py)) if candidates else None
            if existing:
                oldx, oldy = float(existing.get("x_m", px)), float(existing.get("y_m", py))
                alpha = 0.55 if status == "dynamic" else 0.28
                nx, ny = oldx * (1-alpha) + px * alpha, oldy * (1-alpha) + py * alpha
                move = math.hypot(nx - oldx, ny - oldy)
                existing.update({
                    "x_m": round(nx, 3), "y_m": round(ny, 3), "confidence": round(spatial_conf, 3),
                    "last_seen": round(now, 2), "seen_count": int(existing.get("seen_count", 1)) + 1,
                    "status": existing.get("status") if existing.get("status") == "confirmed_static" else status,
                    "head_angle_deg": round(head_angle_deg, 1),
                })
                if status == "dynamic":
                    dt = max(0.05, now - float(existing.get("prev_seen", now)))
                    existing["vx_mps"] = round((nx - oldx) / dt, 3); existing["vy_mps"] = round((ny - oldy) / dt, 3)
                    existing["prev_seen"] = round(now, 2)
                elif status == "temporary" and move > 0.35:
                    self._record_change("temporary_object_moved", existing, {"move_m": round(move, 2)})
                obj = existing
            else:
                obj = {
                    "id": f"obj-{int(now*1000)}-{len(self.objects)%1000}", "label": label,
                    "x_m": round(px, 3), "y_m": round(py, 3), "confidence": round(spatial_conf, 3),
                    "first_seen": round(now, 2), "last_seen": round(now, 2), "seen_count": 1,
                    "status": status, "head_angle_deg": round(head_angle_deg, 1),
                    "vx_mps": 0.0, "vy_mps": 0.0,
                }
                self.objects.append(obj)
            if status != "dynamic" and int(obj.get("seen_count", 1)) == 3:
                # A new obstacle is a change, not an automatic edit of the static map.
                nearest = min((math.hypot(float(a.get("x_m", 0))-float(obj["x_m"]), float(a.get("y_m", 0))-float(obj["y_m"])) for a in self.anchors if str(a.get("label", "")).lower() == label), default=99.0)
                if nearest > 0.65:
                    self._record_change("new_temporary_object" if status == "temporary" else "new_static_candidate", obj)
            self._semantic_anchor_correction(label, px, py, spatial_conf)
        if len(self.objects) > 1400:
            del self.objects[:200]

    def inventory_summary(self) -> dict[str, Any]:
        now = time.time(); counts: dict[str, int] = {}; active_dynamic = 0; temporary = 0
        for obj in self.objects[-1000:]:
            age = now - float(obj.get("last_seen", now))
            status = str(obj.get("status", "temporary"))
            if status == "dynamic" and age <= 20:
                active_dynamic += 1
            if status == "temporary" and age <= 6 * 3600:
                temporary += 1
            if age <= 6 * 3600 or status in {"static_candidate", "confirmed_static"}:
                label = str(obj.get("label", "object")); counts[label] = counts.get(label, 0) + 1
        return {
            "reference_anchors": len(self.anchors), "active_dynamic": active_dynamic,
            "active_temporary": temporary, "labels": counts,
        }

    # ------------------------------------------------------------------ route planning
    def _bounds(self, target: dict[str, float]) -> tuple[float, float, float, float]:
        xs = [self.x_m, float(target["x_m"])]; ys = [self.y_m, float(target["y_m"])]
        for wall in self.walls:
            for p in (wall.get("a", {}), wall.get("b", {})):
                xs.append(float(p.get("x_m", 0))); ys.append(float(p.get("y_m", 0)))
        for zone in self.zones:
            for p in zone.get("points", []):
                xs.append(float(p.get("x_m", 0))); ys.append(float(p.get("y_m", 0)))
        return min(xs)-0.6, max(xs)+0.6, min(ys)-0.6, max(ys)+0.6

    def _occupied(self, x: float, y: float, robot_radius: float = 0.18) -> bool:
        for wall in self.walls:
            if not wall.get("enabled", True) or str(wall.get("kind", "wall")) in {"door_open", "opening"}:
                continue
            a, b = wall.get("a", {}), wall.get("b", {})
            if _point_segment_distance(x, y, float(a.get("x_m",0)), float(a.get("y_m",0)), float(b.get("x_m",0)), float(b.get("y_m",0))) <= robot_radius:
                return True
        for zone in self.zones:
            if str(zone.get("kind", "")) == "no-go" and _point_in_polygon(x, y, list(zone.get("points", []))):
                return True
        now = time.time()
        for obj in self.objects[-500:]:
            status = str(obj.get("status", "temporary")); age = now - float(obj.get("last_seen", now))
            if status == "dynamic" and age > 20: continue
            if status == "temporary" and age > 6*3600: continue
            if status in {"dynamic", "temporary"}:
                radius = 0.38 if status == "dynamic" else 0.28
                if math.hypot(x-float(obj.get("x_m",0)), y-float(obj.get("y_m",0))) <= radius:
                    return True
        return False

    def _line_free(self, a: dict[str,float], b: dict[str,float], step: float = 0.07) -> bool:
        dx, dy = b["x_m"]-a["x_m"], b["y_m"]-a["y_m"]
        d = math.hypot(dx,dy)
        n = max(1, int(d/step))
        for i in range(1,n):
            t=i/n
            if self._occupied(a["x_m"]+dx*t, a["y_m"]+dy*t): return False
        return True

    def _simplify_route(self, path: list[dict[str,float]]) -> list[dict[str,float]]:
        if len(path) <= 2: return path
        out=[path[0]]; i=0
        while i < len(path)-1:
            j=len(path)-1
            while j>i+1 and not self._line_free(path[i],path[j]): j-=1
            out.append(path[j]); i=j
        return out

    def plan_path(self, target: dict[str, float]) -> list[dict[str, float]]:
        tx, ty = float(target["x_m"]), float(target["y_m"])
        minx,maxx,miny,maxy=self._bounds({"x_m":tx,"y_m":ty})
        cell=0.12
        nx=max(1,int(math.ceil((maxx-minx)/cell))+1); ny=max(1,int(math.ceil((maxy-miny)/cell))+1)
        # Keep worst-case planning bounded on a normal laptop.
        if nx*ny > 45000:
            cell*=math.sqrt(nx*ny/45000); nx=int(math.ceil((maxx-minx)/cell))+1; ny=int(math.ceil((maxy-miny)/cell))+1
        def to_grid(x,y): return int(round((x-minx)/cell)), int(round((y-miny)/cell))
        def to_world(g): return {"x_m":round(minx+g[0]*cell,3),"y_m":round(miny+g[1]*cell,3)}
        start=to_grid(self.x_m,self.y_m); goal=to_grid(tx,ty)
        if not (0<=start[0]<nx and 0<=start[1]<ny and 0<=goal[0]<nx and 0<=goal[1]<ny):
            self.route=[]; return []
        blocked: dict[tuple[int,int],bool]={}
        def is_blocked(g):
            if g in {start,goal}: return False
            if g not in blocked:
                p=to_world(g); blocked[g]=self._occupied(p["x_m"],p["y_m"])
            return blocked[g]
        dirs=[(-1,0,1),(1,0,1),(0,-1,1),(0,1,1),(-1,-1,1.414),(1,-1,1.414),(-1,1,1.414),(1,1,1.414)]
        openq=[(0.0,start)]; gscore={start:0.0}; came:dict[tuple[int,int],tuple[int,int]]={}; seen=set()
        while openq:
            _,cur=heapq.heappop(openq)
            if cur in seen: continue
            seen.add(cur)
            if cur==goal: break
            for dx,dy,cost in dirs:
                nxt=(cur[0]+dx,cur[1]+dy)
                if not (0<=nxt[0]<nx and 0<=nxt[1]<ny) or is_blocked(nxt): continue
                ng=gscore[cur]+cost
                if ng < gscore.get(nxt,1e18):
                    gscore[nxt]=ng; came[nxt]=cur
                    h=math.hypot(goal[0]-nxt[0],goal[1]-nxt[1])
                    heapq.heappush(openq,(ng+h,nxt))
        if goal not in came and goal!=start:
            self.route=[]
            log_event("WARNING","vector_probe","No route found",{"target":{"x_m":tx,"y_m":ty}})
            return []
        nodes=[goal]
        while nodes[-1]!=start: nodes.append(came[nodes[-1]])
        nodes.reverse(); path=[to_world(g) for g in nodes]
        path[0]={"x_m":round(self.x_m,3),"y_m":round(self.y_m,3)}; path[-1]={"x_m":round(tx,3),"y_m":round(ty,3)}
        self.route=self._simplify_route(path)
        self.save()
        log_event("INFO","vector_probe","Route planned",{"target":self.route[-1] if self.route else target,"points":len(self.route),"grid_cell_m":round(cell,3)})
        return self.route

    def plan_to_zone(self, name: str) -> dict[str, Any]:
        zone=self.resolve_zone(name)
        if not zone: raise ValueError("zone not found")
        route=self.plan_path(zone["target"])
        return {"zone":zone,"route":route,"ok":bool(route)}

    def steering_hint(self, target: dict[str,float]) -> dict[str,Any]:
        """Potential-field hint: target attracts; recent near rays/objects repel."""
        dx=float(target["x_m"])-self.x_m; dy=float(target["y_m"])-self.y_m
        d=max(1e-6,math.hypot(dx,dy)); vx,vy=dx/d,dy/d
        now=time.time()
        for ray in self.rays[-120:]:
            if now-float(ray.get("t",now))>2.0: continue
            dist=float(ray.get("distance_m",0) or 0)
            if not 0.04<dist<1.0: continue
            ex=float(ray.get("x_m",0)); ey=float(ray.get("y_m",0))
            ox=self.x_m-ex; oy=self.y_m-ey; od=max(0.05,math.hypot(ox,oy))
            gain=(1.0/dist-1.0/1.0)*0.22
            vx+=gain*ox/od; vy+=gain*oy/od
        mag=max(1e-6,math.hypot(vx,vy)); heading=math.degrees(math.atan2(vy/mag,vx/mag))
        return {"target":target,"suggested_heading_deg":round(_norm_deg(heading),1),"turn_error_deg":round(_norm_deg(heading-self.heading_deg),1),"distance_m":round(d,2)}

    # ------------------------------------------------------------------ main update
    def update(self, telemetry: dict[str, Any], vision_status: dict[str, Any], camera_status: dict[str, Any]) -> None:
        if not self.enabled or not telemetry.get("connected"):
            self._last_update = time.monotonic()
            return
        now = time.monotonic(); dt = min(0.5, max(0.0, now - self._last_update)); self._last_update = now

        pwm_limit = max(1.0, float(telemetry.get("pwm_limit", settings.drive_pwm_limit) or settings.drive_pwm_limit))
        max_rpm = float(settings.motor_estimated_max_rpm)
        circumference = math.pi * float(settings.wheel_diameter_mm) / 1000.0
        vl = float(telemetry.get("current_left_pwm", 0) or 0) / pwm_limit * max_rpm * circumference / 60.0
        vr = float(telemetry.get("current_right_pwm", 0) or 0) / pwm_limit * max_rpm * circumference / 60.0
        track = max(0.05, float(settings.track_width_mm) / 1000.0)
        linear = (vl + vr) * 0.5; omega = (vr - vl) / track
        mid_heading = math.radians(self.heading_deg) + omega * dt * 0.5
        self.x_m += linear * math.cos(mid_heading) * dt; self.y_m += linear * math.sin(mid_heading) * dt
        self.heading_deg = _norm_deg(self.heading_deg + math.degrees(omega * dt))
        if abs(linear) > 0.01 or abs(omega) > 0.05:
            # Confidence decay is distance/rotation based, not simply wall-clock based.
            self.confidence = max(0.12, self.confidence - abs(linear)*dt*0.025 - abs(omega)*dt*0.006)
            self._last_pose_source = "pwm_dead_reckoning"
            self._append_trail()

        head = float(camera_status.get("head_pan_deg", 0.0) or 0.0)
        front = float(telemetry.get("front_cm", 0) or 0) / 100.0
        rear = float(telemetry.get("rear_cm", 0) or 0) / 100.0
        third = float(telemetry.get("third_cm", 0) or 0) / 100.0
        tof = float(telemetry.get("tof_mm", 0) or 0) / 1000.0 if telemetry.get("tof_ok") else 0.0

        measurements: list[dict[str,float]]=[]
        for distance,rel,source,weight in ((front,0.0,"hc_front",0.65),(rear,180.0,"hc_rear",0.60),(third,head,"hc_head",0.48),(tof,head,"tof_head",1.0)):
            ray=self._add_ray(distance,rel,source,weight)
            if ray and 0.08<distance<5.5:
                measurements.append({"distance_m":distance,"relative_angle_deg":rel,"weight":weight})
        self._correct_pose_from_walls(measurements)
        self._update_semantics(vision_status, telemetry, head)
        if now - self._last_save_at >= 8.0:
            self._last_save_at = now
            try: self.save()
            except Exception as exc: log_event("ERROR", "vector_probe", "Could not persist spatial state", {"error": str(exc)})


mapping = VectorProbeEngine()
