"""Single shopping agent. Bounded ReAct loop over injected tools.

The agent reasons and picks tools; services enforce every business rule.
It can never mutate confirmation state except through the checkout tools.
"""
from dataclasses import dataclass, field

from app.llm import LLMClient, LLMMessage
from app.prompts import SYSTEM_PROMPT
from app.tools import Tool


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
        max_steps: int = 12,
        max_tool_calls: int = 20,
    ) -> None:
        self.llm = llm
        self.tools = tools
        self.max_steps = max_steps
        self.max_tool_calls = max_tool_calls

    def run(self, user_message: str, ctx: dict) -> AgentResult:
        messages: list[dict] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ]
        trace: list[dict] = []
        tool_calls_made = 0
        steps = 0
        while steps < self.max_steps:
            steps += 1
            reply: LLMMessage = self.llm.complete(messages, self.tools)
            if not reply.tool_calls:
                messages.append({"role": "assistant", "content": reply.content})
                return AgentResult(
                    text=reply.content,
                    status="ok",
                    steps=steps,
                    tool_calls_made=tool_calls_made,
                    trace=trace,
                )
            messages.append(
                {
                    "role": "assistant",
                    "content": reply.content,
                    "tool_calls": [
                        {"name": c.name, "arguments": c.arguments}
                        for c in reply.tool_calls
                    ],
                }
            )
            for call in reply.tool_calls:
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
                        if not isinstance(call.arguments, dict):
                            raise ValueError("tool arguments must be an object")
                        result = tool.run(call.arguments, ctx)
                    except Exception as exc:  # noqa: BLE001 — surfaced to the model
                        result = {"error": f"{type(exc).__name__}: {exc}"}
                tool_calls_made += 1
                trace.append({"tool": call.name, "result": result})
                messages.append(
                    {"role": "tool", "name": call.name, "content": str(result)}
                )
        return AgentResult(
            text="Stopped: step budget exceeded.",
            status="failed",
            steps=steps,
            tool_calls_made=tool_calls_made,
            trace=trace,
        )
