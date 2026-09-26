"""Adapter for Anthropic's Messages API (native tool use)."""
from __future__ import annotations

from typing import Any

from .base import LLM, LLMError, LLMReply, Message, ToolCall, ToolSpec


def to_anthropic_tools(tools: list[ToolSpec]) -> list[dict[str, Any]]:
    return [{"name": t.name, "description": t.description, "input_schema": t.parameters} for t in tools]


def to_anthropic_messages(messages: list[Message]) -> list[dict[str, Any]]:
    """Anthropic differences vs OpenAI:
    - the system prompt is a separate parameter, not a message
    - tool calls are `tool_use` content blocks inside the assistant message
    - tool results are `tool_result` blocks inside a *user* message, and consecutive
      results must be grouped into that one user message
    """
    out: list[dict[str, Any]] = []
    for m in messages:
        if m.role == "user":
            out.append({"role": "user", "content": m.content})
        elif m.role == "assistant":
            blocks: list[dict[str, Any]] = []
            if m.content:
                blocks.append({"type": "text", "text": m.content})
            blocks += [{"type": "tool_use", "id": c.id, "name": c.name, "input": c.arguments}
                       for c in m.tool_calls]
            out.append({"role": "assistant", "content": blocks})
        else:
            block = {"type": "tool_result", "tool_use_id": m.tool_call_id, "content": m.content}
            prev = out[-1] if out else None
            if prev and prev["role"] == "user" and isinstance(prev["content"], list):
                prev["content"].append(block)
            else:
                out.append({"role": "user", "content": [block]})
    return out


def from_anthropic_response(resp: Any) -> LLMReply:
    text = "".join(b.text for b in resp.content if b.type == "text").strip()
    calls = [ToolCall(id=b.id, name=b.name, arguments=dict(b.input))
             for b in resp.content if b.type == "tool_use"]
    return LLMReply(text=text, tool_calls=calls,
                    input_tokens=resp.usage.input_tokens, output_tokens=resp.usage.output_tokens)


class AnthropicLLM(LLM):
    def __init__(self, api_key: str, model: str, client: Any = None):
        self.provider, self.model = "anthropic", model
        if client is None:
            import anthropic
            client = anthropic.Anthropic(api_key=api_key)
        self._client = client

    def chat(self, system: str, messages: list[Message], tools: list[ToolSpec],
             max_tokens: int = 1024) -> LLMReply:
        kwargs: dict[str, Any] = {"model": self.model, "max_tokens": max_tokens,
                                  "system": system, "messages": to_anthropic_messages(messages)}
        if tools:
            kwargs["tools"] = to_anthropic_tools(tools)
        try:
            resp = self._client.messages.create(**kwargs)
        except Exception as e:
            raise LLMError(f"anthropic request failed: {type(e).__name__}: {e}") from e
        return from_anthropic_response(resp)
