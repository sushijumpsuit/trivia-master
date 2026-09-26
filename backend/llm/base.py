"""Provider-neutral types and the interface every LLM adapter implements.

The rest of the app (agent, tools, game state) only ever sees these types.
Each adapter translates them to and from its vendor's wire format.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass
class ToolSpec:
    """A tool the model may call. `parameters` is a JSON Schema object."""
    name: str
    description: str
    parameters: dict[str, Any]


@dataclass
class ToolCall:
    """The model asking us to run a tool."""
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class Message:
    """One entry in the conversation history.

    role="user":      text from the player (or a nudge from our code)
    role="assistant": the model's text and/or tool calls
    role="tool":      the result of one tool call, matched by tool_call_id
    """
    role: Literal["user", "assistant", "tool"]
    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_call_id: str | None = None


@dataclass
class LLMReply:
    text: str
    tool_calls: list[ToolCall]
    input_tokens: int = 0
    output_tokens: int = 0


class LLMError(Exception):
    """Any provider failure (network, auth, rate limit, malformed reply)."""


class LLM(ABC):
    provider: str
    model: str

    @abstractmethod
    def chat(self, system: str, messages: list[Message], tools: list[ToolSpec],
             max_tokens: int = 1024) -> LLMReply:
        """Send the conversation and return the model's next reply."""
