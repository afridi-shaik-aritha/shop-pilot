"""LLM client interface. FakeLLM replays scripted turns in tests/demo.
The OpenAI-compatible client talks to NVIDIA NIM / OpenRouter; nothing in
this module ever logs the API key."""
import json as _json
import random as _random
import time as _time
import urllib.request as _urlreq
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol

from app.config import Settings

if TYPE_CHECKING:
    from app.tools import Tool


@dataclass(frozen=True)
class ToolCall:
    name: str
    arguments: dict = field(default_factory=dict)
    id: str = ""


@dataclass(frozen=True)
class LLMMessage:
    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)


class LLMClient(Protocol):
    def complete(self, messages: list[dict], tools: dict) -> LLMMessage:
        ...


class FakeLLM:
    def __init__(self, script: list[LLMMessage]) -> None:
        self._script = list(script)

    def complete(self, messages: list[dict], tools: dict) -> LLMMessage:
        if not self._script:
            raise RuntimeError("FakeLLM script exhausted")
        return self._script.pop(0)


class LLMError(RuntimeError):
    pass


def to_openai_tools(tools: dict[str, "Tool"]) -> list[dict]:
    converted = []
    for tool in tools.values():
        schema = tool.schema
        converted.append(
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": {
                        "type": "object",
                        "properties": schema.get("properties", {}),
                        "required": schema.get("required", []),
                        "additionalProperties": False,
                    },
                },
            }
        )
    return converted


class OpenAICompatibleClient:
    """OpenAI-compatible chat client for NVIDIA NIM, OpenRouter, LM Studio,
    and Deep Infra.

    Provider selection is env-driven (LLM_PROVIDER=nim|openrouter|lmstudio|deepinfra with
    LLM_BASE_URL / LLM_API_KEY / LLM_MODEL). Stdlib HTTP only. The API key
    is sent as a Bearer token and never logged.
    """

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        timeout_s: int = 60,
        max_attempts: int = 3,
    ) -> None:
        if not base_url or not api_key or not model:
            raise ValueError("base_url, api_key, and model are all required")
        self._url = base_url.rstrip("/") + "/chat/completions"
        self._api_key = api_key
        self._model = model
        self._timeout_s = timeout_s
        self._max_attempts = max_attempts  # transient 429s / backend blips / empty 200s

    @classmethod
    def from_settings(cls, settings: Settings) -> "OpenAICompatibleClient":
        if settings.llm_provider not in ("nim", "openrouter", "lmstudio", "deepinfra"):
            raise ValueError(f"unsupported LLM_PROVIDER: {settings.llm_provider!r}")
        return cls(
            base_url=settings.llm_base_url,
            api_key=settings.llm_api_key,
            model=settings.llm_model,
            timeout_s=settings.llm_timeout_s,
        )

    def complete(self, messages: list[dict], tools: dict) -> LLMMessage:
        body = {
            "model": self._model,
            "messages": messages,
            "tools": to_openai_tools(tools) if tools else [],
            "tool_choice": "auto" if tools else "none",
        }
        request = _urlreq.Request(
            self._url,
            data=_json.dumps(body).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self._api_key}",
            },
            method="POST",
        )
        payload = None
        for attempt in range(self._max_attempts):
            try:
                with _urlreq.urlopen(request, timeout=self._timeout_s) as response:
                    payload = _json.loads(response.read().decode("utf-8"))
            except _urlreq.HTTPError as exc:
                detail = ""
                try:
                    raw = exc.read(1024).decode("utf-8", errors="replace")
                    detail = f": {raw[:500]}" if raw.strip() else ""
                except Exception:
                    pass
                # transient: rate limits, gateway/proxy blips (429, 5xx) plus
                # 400s carrying provider-backend metadata (free-tier proxies)
                transient = exc.code == 429 or exc.code in (500, 502, 503, 504) or (
                    exc.code == 400
                    and any(
                        marker in detail.lower()
                        for marker in ("backend", "upstream", "provider returned error")
                    )
                )
                if transient and attempt < self._max_attempts - 1:
                    _time.sleep(2.0 * (attempt + 1) + _random.uniform(0, 0.5))
                    continue
                raise LLMError(
                    f"llm request failed: HTTP {exc.code}"
                ) from None
            except LLMError:
                raise
            except Exception as exc:
                # Network/timeout errors are transient; programming errors
                # surface via their own type only when clearly not transient.
                if attempt < self._max_attempts - 1 and isinstance(
                    exc, (TimeoutError, ConnectionError, OSError)
                ):
                    _time.sleep(2.0 * (attempt + 1) + _random.uniform(0, 0.5))
                    continue
                raise LLMError(
                    f"llm request failed: {type(exc).__name__}"
                ) from None
            if (
                isinstance(payload, dict)
                and isinstance(payload.get("choices"), list)
                and payload["choices"]
                and isinstance(payload["choices"][0], dict)
                and "message" in payload["choices"][0]
            ):
                break  # usable completion
            # a 200 without a usable completion is usually a provider blip
            if attempt < self._max_attempts - 1:
                payload = None
                _time.sleep(2.0 * (attempt + 1) + _random.uniform(0, 0.5))
                continue
            raise LLMError("llm response has no choices[0].message")
        if payload is None:
            raise LLMError("llm request failed: no response after retries")
        try:
            message = payload["choices"][0]["message"]
        except (KeyError, IndexError, TypeError):
            raise LLMError("llm response has no choices[0].message") from None
        content = message.get("content") or ""
        raw_calls = message.get("tool_calls") or []
        if not isinstance(raw_calls, list):
            raise LLMError("llm tool_calls is not a list")
        calls: list[ToolCall] = []
        for raw in raw_calls:
            function = (raw.get("function") or {}) if isinstance(raw, dict) else {}
            raw_args = function.get("arguments") or "{}"
            try:
                arguments = _json.loads(raw_args)
            except _json.JSONDecodeError:
                raise LLMError("llm tool arguments are not valid JSON") from None
            if not isinstance(arguments, dict):
                raise LLMError("llm tool arguments must be an object")
            calls.append(
                ToolCall(
                    name=function.get("name", ""),
                    arguments=arguments,
                    id=str(raw.get("id", "") or ""),
                )
            )
        return LLMMessage(content=content, tool_calls=calls)
