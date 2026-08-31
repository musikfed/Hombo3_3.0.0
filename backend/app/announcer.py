"""Queued voice announcements for the robot speaker.

The queue lives on Acer, not on ESP32. ESP32 only receives a short PCM stream,
so long conversations do not consume controller flash or permanent storage.
"""
from __future__ import annotations

import asyncio
import time
from contextlib import suppress
from dataclasses import dataclass
from typing import Awaitable, Callable

from .database import log_event
from .tts import render_pcm


@dataclass(slots=True)
class Announcement:
    text: str
    category: str
    cooldown_s: float


class VoiceAnnouncer:
    def __init__(self) -> None:
        self.enabled = True
        self.announce_actions = True
        self.announce_observations = True
        self.announce_critical = True
        self.last_phrase = ""
        self._queue: asyncio.Queue[Announcement] = asyncio.Queue(maxsize=30)
        self._recent: dict[str, float] = {}
        self._worker: asyncio.Task[None] | None = None
        self._sender: Callable[[bytes, int], Awaitable[None]] | None = None

    def status(self) -> dict[str, object]:
        return {
            "enabled": self.enabled,
            "announce_actions": self.announce_actions,
            "announce_observations": self.announce_observations,
            "announce_critical": self.announce_critical,
            "queue_size": self._queue.qsize(),
            "last_phrase": self.last_phrase,
        }

    def configure(self, values: dict[str, object]) -> dict[str, object]:
        for name in ("enabled", "announce_actions", "announce_observations", "announce_critical"):
            if name in values and values[name] is not None:
                setattr(self, name, bool(values[name]))
        return self.status()

    async def start(self, sender: Callable[[bytes, int], Awaitable[None]]) -> None:
        self._sender = sender
        if self._worker is None:
            self._worker = asyncio.create_task(self._run(), name="robot-voice-announcer")

    async def stop(self) -> None:
        if self._worker:
            self._worker.cancel()
            with suppress(asyncio.CancelledError):
                await self._worker
            self._worker = None

    async def say(self, text: str, category: str = "action", cooldown_s: float = 2.0) -> bool:
        text = " ".join(text.strip().split())
        if not text or not self.enabled:
            return False
        if category == "action" and not self.announce_actions:
            return False
        if category == "observation" and not self.announce_observations:
            return False
        if category == "critical" and not self.announce_critical:
            return False

        now = time.monotonic()
        if now - self._recent.get(text, -10_000.0) < cooldown_s:
            return False
        self._recent[text] = now
        try:
            self._queue.put_nowait(Announcement(text=text, category=category, cooldown_s=cooldown_s))
        except asyncio.QueueFull:
            log_event("WARNING", "speech", "Voice queue is full; phrase skipped", {"text": text})
            return False
        log_event("INFO", "speech", "Phrase queued", {"text": text, "category": category})
        return True

    async def _run(self) -> None:
        while True:
            item = await self._queue.get()
            try:
                if self._sender is None:
                    continue
                pcm, sample_rate = await render_pcm(item.text)
                await self._sender(pcm, sample_rate)
                self.last_phrase = item.text
                log_event("INFO", "speech", "Phrase played", {"text": item.text})
            except Exception as exc:
                log_event("ERROR", "speech", "Automatic speech failed", {"text": item.text, "error": str(exc)})
            finally:
                self._queue.task_done()


announcer = VoiceAnnouncer()
