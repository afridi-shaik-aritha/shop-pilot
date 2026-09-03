"""LLM client interface. FakeLLM replays scripted turns in tests/demo.
Real provider adapter lands in Plan 3; nothing here makes network calls."""
import json as _json
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
                    },
                },
            }
        )
    return converted


class OpenAICompatibleClient:
    """OpenAI-compatible chat client for NVIDIA NIM and OpenRouter.

    Provider selection is env-driven (LLM_PROVIDER=nim|openrouter with
    LLM_BASE_URL / LLM_API_KEY / LLM_MODEL). Stdlib HTTP only. The API key
    is sent as a Bearer token and never logged.
    """

    def __init__(self, base_url: str, api_key: str, model: str, timeout_s: int = 60) -> None:
        if not base_url or not api_key or not model:
            raise ValueError("base_url, api_key, and model are all required")
        self._url = base_url.rstrip("/") + "/chat/completions"
        self._api_key = api_key
        self._model = model
        self._timeout_s = timeout_s

    @classmethod
    def from_settings(cls, settings: Settings) -> "OpenAICompatibleClient":
        if settings.llm_provider not in ("nim", "openrouter"):
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
        try:
            with _urlreq.urlopen(request, timeout=self._timeout_s) as response:
                payload = _json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            raise LLMError(f"llm request failed: {type(exc).__name__}: {exc}") from None
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
            calls.append(ToolCall(name=function.get("name", ""), arguments=arguments))
        return LLMMessage(content=content, tool_calls=calls)
