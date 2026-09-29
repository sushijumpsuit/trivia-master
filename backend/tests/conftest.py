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
    (distance 0.05). `distances` sets exact distances for chosen pairs, to replay real numbers.
    Everything else is distance 1.0.
    """

    def __init__(self, similar=(), fail=False, distances=None):
        self.items = []
        self.similar = {frozenset((normalise_question(a), normalise_question(b))) for a, b in similar}
        self.distances = {frozenset((normalise_question(a), normalise_question(b))): d
                          for (a, b), d in (distances or {}).items()}
        self.fail = fail

    def _distance(self, a, b):
        a, b = normalise_question(a), normalise_question(b)
        pair = frozenset((a, b))
        if a == b:
            return 0.0
        return self.distances.get(pair, 0.05 if pair in self.similar else 1.0)

    def nearest(self, question, answer, k=memory.NEIGHBOURS):
        if self.fail:
            raise RuntimeError("chroma is down")
        ranked = sorted(self.items, key=lambda it: self._distance(question, it["question"]))[:k]
        return [memory.Match(question=it["question"], answer=it["answer"], topic=it["topic"],
                             distance=self._distance(question, it["question"])) for it in ranked]

    def add(self, question, answer, topic, game_id):
        if self.fail:
            raise RuntimeError("chroma is down")
        self.items.append({"question": question, "answer": answer, "topic": topic, "game_id": game_id})

    def related_answers(self, topic, limit=60):
        if self.fail:
            raise RuntimeError("chroma is down")
        return list(dict.fromkeys(it["answer"] for it in self.items))[:limit]

    def related_questions(self, topic, limit=30):
        if self.fail:
            raise RuntimeError("chroma is down")
        return list(dict.fromkeys(f'{it["question"]} ({it["answer"]})' for it in self.items))[:limit]

    def count(self):
        return len(self.items)

    def warm_up(self):
        pass


@pytest.fixture(autouse=True)
def no_rate_limits(monkeypatch):
    """Tests start many games from one client; rate limits get their own tests."""
    import main
    from ratelimit import RateLimiter
    monkeypatch.setattr(main, "limiter", RateLimiter(0, 0, 0))


@pytest.fixture(autouse=True)
def fake_memory(monkeypatch):
    """Every test gets a fresh, empty fake memory and the default cutoffs."""
    monkeypatch.delenv("DUP_SAME_ANSWER_DISTANCE", raising=False)
    monkeypatch.delenv("DUP_ANY_ANSWER_DISTANCE", raising=False)
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
