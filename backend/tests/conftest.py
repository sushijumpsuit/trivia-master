import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # make backend/ importable

from llm import LLM, LLMReply, ToolCall  # noqa: E402


class FakeLLM(LLM):
    """Plays back scripted replies instead of calling a real provider. Records what it was sent."""
    provider, model = "fake", "fake-1"

    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []

    def chat(self, system, messages, tools, max_tokens=1024):
        self.calls.append({"system": system, "messages": list(messages)})
        if not self.replies:
            raise AssertionError("FakeLLM ran out of scripted replies")
        r = self.replies.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


def tool(name, id_="c1", **args):
    return ToolCall(id=id_, name=name, arguments=args)


def reply(text="", *calls):
    return LLMReply(text=text, tool_calls=list(calls))


@pytest.fixture
def fake_llm():
    return FakeLLM
