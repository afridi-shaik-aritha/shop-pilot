"""Single shopping agent. Bounded ReAct loop over injected tools.

The agent reasons and picks tools; services enforce every business rule.
It can never mutate confirmation state except through the checkout tools.
"""
import json
from dataclasses import dataclass, field

from app.guardrails import validate_tool_args
from app.llm import LLMClient, LLMMessage
from app.prompts import SYSTEM_PROMPT
from app.tools import Tool


def _model_visible(result):
    """Tool results as the LLM sees them. Confirmation codes belong to the
    shopper's slip only, so they are redacted before anything reaches the model.
    """
    if isinstance(result, dict):
        return {
            k: ("[redacted — shown to the shopper only]" if k == "confirmation_token"
                else _model_visible(v))
            for k, v in result.items()
        }
    if isinstance(result, list):
        return [_model_visible(v) for v in result]
    return result


@dataclass
class AgentResult:
    text: str
    status: str = "ok"
    steps: int = 0
    tool_calls_made: int = 0
    trace: list[dict] = field(default_factory=list)


class ShoppingAgent:
    def __init__(
        self,
        llm: LLMClient,
        tools: dict[str, Tool],
        system_prompt: str = SYSTEM_PROMPT,
        max_steps: int = 12,
        max_tool_calls: int = 20,
    ) -> None:
        self.llm = llm
        self.tools = tools
        self.system_prompt = system_prompt
        self.max_steps = max_steps
        self.max_tool_calls = max_tool_calls

    @staticmethod
    def _history_entries(history: list[dict] | None, limit: int = 32) -> list[dict]:
        """Plain user/assistant turns only — tool scaffolding never replays."""
        clean: list[dict] = []
        for entry in history or []:
            if not isinstance(entry, dict):
                continue
            role, content = entry.get("role"), entry.get("content")
            if role not in ("user", "assistant") or not isinstance(content, str):
                continue
            clean.append({"role": role, "content": content[:4000]})
        return clean[-limit:]

    def run(
        self,
        user_message: str,
        ctx: dict,
        history: list[dict] | None = None,
    ) -> AgentResult:
        messages: list[dict] = [
            {"role": "system", "content": self.system_prompt},
            *self._history_entries(history),
            {"role": "user", "content": user_message},
        ]
        trace: list[dict] = []
        tool_calls_made = 0
        steps = 0
        while steps < self.max_steps:
            steps += 1
            try:
                reply: LLMMessage = self.llm.complete(messages, self.tools)
            except Exception as exc:
                return AgentResult(
                    text=f"LLM error: {type(exc).__name__}: {exc}",
                    status="failed",
                    steps=steps,
                    tool_calls_made=tool_calls_made,
                    trace=trace,
                )
            if not reply.tool_calls:
                messages.append({"role": "assistant", "content": reply.content})
                return AgentResult(
                    text=reply.content,
                    status="ok",
                    steps=steps,
                    tool_calls_made=tool_calls_made,
                    trace=trace,
                )
            # one id per call, shared by the assistant tool_calls entry and the
            # matching tool result so strict providers (e.g. NIM) can pair them
            call_ids = [c.id or f"call_{tool_calls_made + i}" for i, c in enumerate(reply.tool_calls)]
            messages.append(
                {
                    "role": "assistant",
                    "content": reply.content,
                    "tool_calls": [
                        {
                            "id": call_ids[i],
                            "type": "function",
                            "function": {
                                "name": c.name,
                                "arguments": json.dumps(c.arguments),
                            },
                        }
                        for i, c in enumerate(reply.tool_calls)
                    ],
                }
            )
            for i, call in enumerate(reply.tool_calls):
                if tool_calls_made >= self.max_tool_calls:
                    return AgentResult(
                        text="Stopped: tool-call budget exceeded.",
                        status="failed",
                        steps=steps,
                        tool_calls_made=tool_calls_made,
                        trace=trace,
                    )
                tool = self.tools.get(call.name)
                if tool is None:
                    result = {"error": f"unknown tool: {call.name}"}
                else:
                    try:
                        validate_tool_args(tool.schema, call.arguments)
                        result = _model_visible(tool.run(call.arguments, ctx))
                    except Exception as exc:  # noqa: BLE001 — surfaced to the model
                        result = {"error": f"{type(exc).__name__}: {exc}"}
                tool_calls_made += 1
                trace.append({"tool": call.name, "result": result})
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call_ids[i],
                        "content": str(result),
                    }
                )
        # Step budget exhausted mid-reasoning: the model kept calling tools and
        # never produced a final answer. Instead of dead-ending with
        # "Stopped: step budget exceeded", give it ONE final completion so it
        # can answer from the tool results it already collected (churny small
        # models otherwise burn all steps searching and leave the shopper with
        # nothing). If it still insists on tool calls, stop honestly.
        try:
            final = self.llm.complete(
                messages
                + [
                    {
                        "role": "system",
                        "content": "Summarize your answer now from the tool "
                        "results above. Do not call any more tools.",
                    }
                ],
                self.tools,
            )
        except Exception as exc:
            return AgentResult(
                text=f"LLM error: {type(exc).__name__}: {exc}",
                status="failed",
                steps=steps + 1,
                tool_calls_made=tool_calls_made,
                trace=trace,
            )
        if final.tool_calls:
            return AgentResult(
                text="Stopped: step budget exceeded.",
                status="failed",
                steps=steps + 1,
                tool_calls_made=tool_calls_made,
                trace=trace,
            )
        return AgentResult(
            text=final.content,
            status="ok",
            steps=steps + 1,
            tool_calls_made=tool_calls_made,
            trace=trace,
        )

    def run_stream(
        self,
        user_message: str,
        ctx: dict,
        history: list[dict] | None = None,
    ):
        """Streamed ReAct loop. Yields lifecycle events:
        - {"type": "status", "text": "..."}
        - {"type": "delta", "text": chunk}
        - {"type": "reasoning", "text": chunk}
        - {"type": "tool_start", "name": tool_name, "arguments": {...}}
        - {"type": "tool_end", "name": tool_name, "result": {...}}
        - {"type": "complete", "result": AgentResult(...)}
        """
        messages: list[dict] = [
            {"role": "system", "content": self.system_prompt},
            *self._history_entries(history),
            {"role": "user", "content": user_message},
        ]
        trace: list[dict] = []
        tool_calls_made = 0
        steps = 0
        while steps < self.max_steps:
            steps += 1
            reply: LLMMessage | None = None
            step_deltas: list[str] = []
            try:
                if hasattr(self.llm, "complete_stream"):
                    for event_kind, payload in self.llm.complete_stream(messages, self.tools):
                        if event_kind == "delta":
                            step_deltas.append(payload)
                            yield {"type": "delta", "text": payload}
                        elif event_kind == "reasoning":
                            yield {"type": "reasoning", "text": payload}
                        elif event_kind == "done":
                            reply = payload
                else:
                    reply = self.llm.complete(messages, self.tools)
                    if reply.content:
                        step_deltas.append(reply.content)
                        yield {"type": "delta", "text": reply.content}
            except Exception as exc:
                res = AgentResult(
                    text=f"LLM error: {type(exc).__name__}: {exc}",
                    status="failed",
                    steps=steps,
                    tool_calls_made=tool_calls_made,
                    trace=trace,
                )
                yield {"type": "complete", "result": res}
                return

            if reply is None:
                res = AgentResult(
                    text="LLM error: no reply received",
                    status="failed",
                    steps=steps,
                    tool_calls_made=tool_calls_made,
                    trace=trace,
                )
                yield {"type": "complete", "result": res}
                return

            if not reply.tool_calls:
                messages.append({"role": "assistant", "content": reply.content})
                res = AgentResult(
                    text=reply.content,
                    status="ok",
                    steps=steps,
                    tool_calls_made=tool_calls_made,
                    trace=trace,
                )
                yield {"type": "complete", "result": res}
                return

            # If intermediate text was streamed before tool calls, notify client to reset text buffer
            if step_deltas:
                yield {"type": "reset_delta"}

            call_ids = [c.id or f"call_{tool_calls_made + i}" for i, c in enumerate(reply.tool_calls)]
            messages.append(
                {
                    "role": "assistant",
                    "content": reply.content,
                    "tool_calls": [
                        {
                            "id": call_ids[i],
                            "type": "function",
                            "function": {
                                "name": c.name,
                                "arguments": json.dumps(c.arguments),
                            },
                        }
                        for i, c in enumerate(reply.tool_calls)
                    ],
                }
            )
            for i, call in enumerate(reply.tool_calls):
                if tool_calls_made >= self.max_tool_calls:
                    res = AgentResult(
                        text="Stopped: tool-call budget exceeded.",
                        status="failed",
                        steps=steps,
                        tool_calls_made=tool_calls_made,
                        trace=trace,
                    )
                    yield {"type": "complete", "result": res}
                    return
                yield {"type": "tool_start", "name": call.name, "arguments": call.arguments}
                tool = self.tools.get(call.name)
                if tool is None:
                    result = {"error": f"unknown tool: {call.name}"}
                else:
                    try:
                        validate_tool_args(tool.schema, call.arguments)
                        result = _model_visible(tool.run(call.arguments, ctx))
                    except Exception as exc:
                        result = {"error": f"{type(exc).__name__}: {exc}"}
                tool_calls_made += 1
                trace.append({"tool": call.name, "result": result})
                yield {"type": "tool_end", "name": call.name, "result": result}
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call_ids[i],
                        "content": str(result),
                    }
                )

        yield {"type": "status", "text": "Summarizing answer..."}
        try:
            final: LLMMessage | None = None
            final_messages = messages + [
                {
                    "role": "system",
                    "content": "Summarize your answer now from the tool results above. Do not call any more tools.",
                }
            ]
            if hasattr(self.llm, "complete_stream"):
                for event_kind, payload in self.llm.complete_stream(final_messages, self.tools):
                    if event_kind == "delta":
                        yield {"type": "delta", "text": payload}
                    elif event_kind == "reasoning":
                        yield {"type": "reasoning", "text": payload}
                    elif event_kind == "done":
                        final = payload
            else:
                final = self.llm.complete(final_messages, self.tools)
                if final.content:
                    yield {"type": "delta", "text": final.content}
        except Exception as exc:
            res = AgentResult(
                text=f"LLM error: {type(exc).__name__}: {exc}",
                status="failed",
                steps=steps + 1,
                tool_calls_made=tool_calls_made,
                trace=trace,
            )
            yield {"type": "complete", "result": res}
            return

        if final is None or final.tool_calls:
            res = AgentResult(
                text="Stopped: step budget exceeded.",
                status="failed",
                steps=steps + 1,
                tool_calls_made=tool_calls_made,
                trace=trace,
            )
            yield {"type": "complete", "result": res}
            return

        res = AgentResult(
            text=final.content,
            status="ok",
            steps=steps + 1,
            tool_calls_made=tool_calls_made,
            trace=trace,
        )
        yield {"type": "complete", "result": res}

