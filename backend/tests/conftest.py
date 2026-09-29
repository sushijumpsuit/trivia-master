import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # make backend/ importable

import memory  # noqa: E402
from llm import LLM, LLMReply, ToolCall  # noqa: E402
from tools import normalise_question  # noqa: E402


class FakeMemory:
    """In-memory stand-in for QuestionMemory (no ChromaDB, no embedding model).

    Exact same question = distance 0.0. `similar` lists question pairs to treat as rewordings
    (distance 0.05). Everything else is distance 1.0.
    """

    def __init__(self, similar=(), fail=False):
        self.items = []
        self.similar = {frozenset((normalise_question(a), normalise_question(b))) for a, b in similar}
        self.fail = fail

    def _distance(self, a, b):
        a, b = normalise_question(a), normalise_question(b)
        return 0.0 if a == b else 0.05 if frozenset((a, b)) in self.similar else 1.0

    def nearest(self, question, answer):
        if self.fail:
            raise RuntimeError("chroma is down")
        if not self.items:
            return None
        best = min(self.items, key=lambda it: self._distance(question, it["question"]))
        return memory.Match(question=best["question"], answer=best["answer"], topic=best["topic"],
                            distance=self._distance(question, best["question"]))

    def add(self, question, answer, topic, difficulty, game_id):
        if self.fail:
            raise RuntimeError("chroma is down")
        self.items.append({"question": question, "answer": answer, "topic": topic, "game_id": game_id})

    def count(self):
        return len(self.items)

    def warm_up(self):
        pass


@pytest.fixture(autouse=True)
def fake_memory(monkeypatch):
    """Every test gets a fresh, empty fake memory and the default cutoff."""
    monkeypatch.delenv("DUPLICATE_DISTANCE", raising=False)
    m = FakeMemory()
    memory.set_memory(m)
    yield m
    memory.set_memory(None)


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
