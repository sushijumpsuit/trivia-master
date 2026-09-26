"""Adapter for OpenAI's chat-completions format.

Used for OpenAI itself, and for Groq and Gemini, which accept the same format
at a different base URL.
"""
from __future__ import annotations

import json
from typing import Any

from .base import LLM, LLMError, LLMReply, Message, ToolCall, ToolSpec


def to_openai_tools(tools: list[ToolSpec]) -> list[dict[str, Any]]:
    return [{"type": "function",
             "function": {"name": t.name, "description": t.description, "parameters": t.parameters}}
            for t in tools]


def to_openai_messages(system: str, messages: list[Message]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = [{"role": "system", "content": system}]
    for m in messages:
        if m.role == "user":
            out.append({"role": "user", "content": m.content})
        elif m.role == "assistant":
            msg: dict[str, Any] = {"role": "assistant", "content": m.content or None}
            if m.tool_calls:
                # OpenAI wants arguments as a JSON *string*, not an object.
                msg["tool_calls"] = [{"id": c.id, "type": "function",
                                      "function": {"name": c.name, "arguments": json.dumps(c.arguments)}}
                                     for c in m.tool_calls]
            out.append(msg)
        else:  # tool result
            out.append({"role": "tool", "tool_call_id": m.tool_call_id, "content": m.content})
    return out


def from_openai_response(resp: Any) -> LLMReply:
    choice = resp.choices[0].message
    calls: list[ToolCall] = []
    for c in choice.tool_calls or []:
        try:
            args = json.loads(c.function.arguments or "{}")
        except json.JSONDecodeError as e:
            raise LLMError(f"Model sent invalid JSON arguments for {c.function.name}: {e}")
        calls.append(ToolCall(id=c.id, name=c.function.name, arguments=args))
    usage = getattr(resp, "usage", None)
    return LLMReply(text=(choice.content or "").strip(), tool_calls=calls,
                    input_tokens=getattr(usage, "prompt_tokens", 0) or 0,
                    output_tokens=getattr(usage, "completion_tokens", 0) or 0)


class OpenAICompatLLM(LLM):
    def __init__(self, provider: str, api_key: str, model: str, base_url: str | None = None,
                 client: Any = None):
        self.provider, self.model = provider, model
        if client is None:
            from openai import OpenAI  # imported lazily so tests don't need the SDK
            client = OpenAI(api_key=api_key, base_url=base_url)
        self._client = client

    def chat(self, system: str, messages: list[Message], tools: list[ToolSpec],
             max_tokens: int = 1024) -> LLMReply:
        kwargs: dict[str, Any] = {"model": self.model,
                                  "messages": to_openai_messages(system, messages)}
        if tools:
            kwargs["tools"] = to_openai_tools(tools)
        # Newer OpenAI models reject `max_tokens`; Groq accepts either; Gemini's compat layer wants max_tokens.
        kwargs["max_tokens" if self.provider == "gemini" else "max_completion_tokens"] = max_tokens
        try:
            resp = self._client.chat.completions.create(**kwargs)
        except Exception as e:  # SDK raises many subclasses; normalise them
            raise LLMError(f"{self.provider} request failed: {type(e).__name__}: {e}") from e
        return from_openai_response(resp)
