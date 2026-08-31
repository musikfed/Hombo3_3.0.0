"""Hermes 4 REST client optimized for robot dialogue and agent decisions.

Two paths are intentionally separated:
1) ordinary dialogue (allow_action=False): simple chat, no JSON grammar/schema;
2) action request/autonomy: compact context + JSON mode, parsed/validated by Acer.

This avoids forcing every normal conversation through structured output and prevents
recursive RAG logs from inflating the prompt until a long local-model timeout.
"""
from __future__ import annotations

import json
import re
from typing import Any

import httpx

from .config import settings
from .database import append_dataset_record, log_event
from .models import LlmDecision

DIALOGUE_SYSTEM_PROMPT = """
Ты Hermes 4, генеративный мозг домашнего мобильного робота-машинки.
У робота дифференциальная схема: левый борт и правый борт, по два мотора на борт; руля нет.
Отвечай естественно и по делу. Не выдумывай показания датчиков и состояние железа.
Контроллер ESP32, камера и моторы могут быть отключены: обычному диалогу это не мешает.
Если в контексте есть имя робота, можешь использовать его как своё имя.
""".strip()

AGENT_SYSTEM_PROMPT = """
Ты Hermes 4, генеративный мозг домашнего мобильного робота с дифференциальной бортовой схемой: левый и правый борт, по два мотора на борт; руля нет.
Используй только переданную телеметрию, локальное зрение Acer, активный профиль ходовой, компактную память и навыки.
Никогда не обходи watchdog, локальную защиту ESP32 и аварийный STOP. Если данных недостаточно или ситуация опасна — action должен быть none или stop.
Верни ТОЛЬКО JSON-объект без Markdown со следующими полями:
{"say":"короткая фраза","action":"none|stop|forward|backward|left|right","speed":0,"duration_ms":0,"reason":"краткая причина"}
Ограничения: speed 0..100, duration_ms 0..3000.
""".strip()


def _normalize_base_url(value: str) -> str:
    value = value.strip()
    match = re.fullmatch(r"\[([^\]]+)\]\(([^)]+)\)", value)
    if match:
        value = match.group(2)
    return value.rstrip("/")


def _normalize_model(value: str) -> str:
    return value.strip().replace("\\:", ":")


def _error_text(exc: BaseException) -> str:
    text = str(exc).strip()
    return text if text else f"{type(exc).__name__}: {exc!r}"


def _http_error_text(exc: httpx.HTTPStatusError) -> str:
    response = exc.response
    try:
        body = response.text.strip()
    except Exception:
        body = ""
    if len(body) > 1200:
        body = body[:1200] + "..."
    suffix = f" body={body}" if body else ""
    return f"HTTP {response.status_code} {response.request.method} {response.request.url}{suffix}"


def _json_len(value: Any) -> int:
    try:
        return len(json.dumps(value, ensure_ascii=False, separators=(",", ":")))
    except Exception:
        return -1


def _compact_context(context: dict[str, Any] | None, max_chars: int = 14000) -> dict[str, Any]:
    """Final defensive bound even if another memory provider becomes verbose later."""
    if not context:
        return {}
    out = dict(context)

    # The explicit graph is stable; for the model a compact semantic summary is enough.
    graph = out.get("hardware_graph") or {}
    if isinstance(graph, dict):
        nodes = graph.get("nodes") or []
        out["hardware_graph"] = {
            "summary": [str(n.get("label", n.get("id", ""))) for n in nodes[:20] if isinstance(n, dict)]
        }

    memory = out.get("retrieved_memory")
    if isinstance(memory, list):
        out["retrieved_memory"] = memory[:6]

    skills = out.get("retrieved_skills")
    if isinstance(skills, list):
        out["retrieved_skills"] = skills[:6]

    encoded = json.dumps(out, ensure_ascii=False, separators=(",", ":"))
    if len(encoded) <= max_chars:
        return out

    # First trim memory, then skills. Keep current telemetry/tuning/vision.
    out["retrieved_memory"] = (out.get("retrieved_memory") or [])[:2]
    out["retrieved_skills"] = (out.get("retrieved_skills") or [])[:3]
    encoded = json.dumps(out, ensure_ascii=False, separators=(",", ":"))
    if len(encoded) <= max_chars:
        return out

    # Last resort: omit historical material completely rather than timing out control.
    out["retrieved_memory"] = []
    out["retrieved_skills"] = []
    return out


def _decision_from_content(content: str) -> LlmDecision:
    content = content.strip()
    if not content:
        raise ValueError("Hermes returned empty message.content")
    try:
        return LlmDecision.model_validate_json(content)
    except Exception as first_exc:
        start = content.find("{")
        end = content.rfind("}")
        if start >= 0 and end > start:
            candidate = content[start : end + 1]
            try:
                return LlmDecision.model_validate_json(candidate)
            except Exception:
                pass
        raise ValueError(f"Invalid Hermes JSON: {type(first_exc).__name__}: {first_exc}") from first_exc


class OllamaClient:
    def __init__(self) -> None:
        self.base_url = _normalize_base_url(settings.ollama_base_url)
        self.model = _normalize_model(settings.ollama_model)
        timeout = httpx.Timeout(settings.ollama_timeout_s, connect=min(10.0, settings.ollama_timeout_s))
        self._http = httpx.AsyncClient(timeout=timeout)

    async def close(self) -> None:
        await self._http.aclose()

    async def status(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "configured": bool(self.base_url and self.model),
            "reachable": False,
            "base_url": self.base_url,
            "model": self.model,
            "model_found": False,
            "note": "reachable/model_found checks Ollama catalog; generation is tested by the agent request",
            "error": "",
        }
        if not result["configured"]:
            result["error"] = "OLLAMA_BASE_URL / OLLAMA_MODEL are not configured"
            return result
        try:
            response = await self._http.get(
                f"{self.base_url}/api/tags",
                timeout=min(settings.ollama_timeout_s, 8.0),
            )
            response.raise_for_status()
            result["reachable"] = True
            names = [str(item.get("name", "")) for item in response.json().get("models", [])]
            result["model_found"] = self.model in names
            result["models"] = names
        except httpx.HTTPStatusError as exc:
            result["error"] = _http_error_text(exc)
        except Exception as exc:
            result["error"] = _error_text(exc)
        return result

    async def _post_chat(self, payload: dict[str, Any], mode: str) -> dict[str, Any]:
        try:
            response = await self._http.post(f"{self.base_url}/api/chat", json=payload)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as exc:
            detail = _http_error_text(exc)
            log_event("ERROR", "ollama", f"Hermes {mode} HTTP failed", {"error": detail})
            raise RuntimeError(detail) from exc
        except httpx.TimeoutException as exc:
            detail = f"{type(exc).__name__}: timeout after {settings.ollama_timeout_s}s while calling {self.base_url}/api/chat"
            log_event("ERROR", "ollama", f"Hermes {mode} timeout", {"error": detail})
            raise RuntimeError(detail) from exc
        except httpx.RequestError as exc:
            detail = f"{type(exc).__name__}: {_error_text(exc)}"
            log_event("ERROR", "ollama", f"Hermes {mode} network failed", {"error": detail})
            raise RuntimeError(detail) from exc

    async def _dialogue(self, prompt: str, context: dict[str, Any] | None) -> LlmDecision:
        compact = _compact_context(context, max_chars=9000)
        # Keep dialogue context intentionally small: live state + a little memory is useful,
        # but an ordinary conversation must never depend on a huge agent/RAG packet.
        dialogue_context = {
            "active_tuning": compact.get("active_tuning", {}),
            "telemetry": compact.get("telemetry", {}),
            "vision": compact.get("vision", {}),
            "retrieved_memory": (compact.get("retrieved_memory") or [])[:3],
        }
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": DIALOGUE_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        "Текущий компактный контекст робота:\n"
                        + json.dumps(dialogue_context, ensure_ascii=False, separators=(",", ":"))
                        + "\n\nСообщение пользователя:\n"
                        + prompt
                    ),
                },
            ],
            "stream": False,
            "think": False,
            "keep_alive": "30m",
            "options": {
                "temperature": 0.3,
                "num_ctx": 4096,
                "num_predict": 320,
            },
        }
        log_event(
            "INFO",
            "ollama",
            "Hermes dialogue request",
            {"prompt_chars": len(prompt), "context_chars": _json_len(dialogue_context)},
        )
        raw = await self._post_chat(payload, "dialogue")
        content = str((raw.get("message") or {}).get("content") or "").strip()
        if not content:
            raise RuntimeError("Hermes dialogue returned empty message.content")
        decision = LlmDecision(say=content, action="none", speed=0, duration_ms=0, reason="dialogue")
        log_event(
            "INFO",
            "ollama",
            "Hermes dialogue response",
            {
                "chars": len(content),
                "load_duration": raw.get("load_duration", 0),
                "prompt_eval_count": raw.get("prompt_eval_count", 0),
                "eval_count": raw.get("eval_count", 0),
            },
        )
        append_dataset_record({"type": "llm_dialogue", "input": {"prompt": prompt}, "output": {"say": content}})
        return decision

    async def _agent_decision(
        self,
        prompt: str,
        telemetry: dict[str, Any],
        context: dict[str, Any] | None,
    ) -> LlmDecision:
        compact = _compact_context(context, max_chars=14000)
        task = {
            "operator_prompt": prompt,
            "telemetry": telemetry,
            "context": compact,
        }
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": AGENT_SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(task, ensure_ascii=False, separators=(",", ":"))},
            ],
            "stream": False,
            # JSON mode is lighter and more compatible with community GGUF templates
            # than forcing a full JSON grammar/schema for every local decision.
            "format": "json",
            "think": False,
            "keep_alive": "30m",
            "options": {
                "temperature": 0,
                "num_ctx": 4096,
                "num_predict": 220,
            },
        }
        log_event(
            "INFO",
            "ollama",
            "Hermes agent request",
            {"prompt_chars": len(prompt), "context_chars": _json_len(compact)},
        )
        raw = await self._post_chat(payload, "agent-json")
        content = str((raw.get("message") or {}).get("content") or "")
        decision = _decision_from_content(content)
        metrics = {
            "model": raw.get("model", self.model),
            "done_reason": raw.get("done_reason", ""),
            "load_duration": raw.get("load_duration", 0),
            "prompt_eval_count": raw.get("prompt_eval_count", 0),
            "eval_count": raw.get("eval_count", 0),
        }
        log_event(
            "INFO",
            "ollama",
            "Hermes decision",
            {
                "prompt": prompt[:800],
                "decision": decision.model_dump(),
                "metrics": metrics,
            },
        )
        # Do not persist the full RAG context in the dataset. That was the source
        # of recursive prompt growth when old decisions were retrieved again.
        append_dataset_record({
            "type": "llm_decision",
            "input": {"prompt": prompt, "telemetry": telemetry},
            "output": decision.model_dump(),
        })
        return decision

    async def decide(
        self,
        prompt: str,
        telemetry: dict[str, Any],
        allow_action: bool,
        context: dict[str, Any] | None = None,
    ) -> LlmDecision:
        # Ordinary assistant dialogue must remain independent of ESP32 and must not
        # pay the latency cost of constrained structured output.
        if not allow_action:
            return await self._dialogue(prompt, context)

        decision = await self._agent_decision(prompt, telemetry, context)
        return decision
