"""Long-term question memory (ChromaDB), so the game never repeats a question, even reworded.

How it works:
- Every accepted question is embedded (turned into a vector that captures its meaning) together
  with its answer, and saved to a persistent ChromaDB collection on disk, so it survives restarts.
- Before a new question is accepted, we look at the 5 most similar past questions and apply a
  hybrid rule (see is_duplicate): distance alone overlapped on real data, but every real repeat
  shared its answer and every false alarm didn't. DEVLOG bug 8 has the numbers.

All ChromaDB code lives in this file (see CLAUDE.md).
"""
from __future__ import annotations

import logging
import os
import re
import uuid
from dataclasses import dataclass
from typing import Any

log = logging.getLogger("trivia.memory")

COLLECTION = "questions"

# Store question + answer together. Reworded repeats share the answer; different facts that use the
# same wording ("Gloria's son?" = Manny vs "Gloria's first husband?" = Javier) don't, which pushes
# them further apart. tune_threshold.py measures both modes on real question pairs.
INCLUDE_ANSWER = True

# Cosine distance: 0 = same meaning, bigger = less similar. Picked with tune_threshold.py on real pairs.
DEFAULT_SAME_ANSWER_DISTANCE = 0.5   # same answer and this close = repeat (catches loose rewordings)
DEFAULT_ANY_ANSWER_DISTANCE = 0.05   # different answer = repeat only if the question is nearly identical
NEIGHBOURS = 5                       # how many nearest past questions to check


def same_answer_cutoff() -> float:
    return float(os.getenv("DUP_SAME_ANSWER_DISTANCE", DEFAULT_SAME_ANSWER_DISTANCE))


def any_answer_cutoff() -> float:
    return float(os.getenv("DUP_ANY_ANSWER_DISTANCE", DEFAULT_ANY_ANSWER_DISTANCE))


_ARTICLES = {"the", "a", "an"}


def normalise_answer(text: str) -> list[str]:
    """Answer as lowercase words, no punctuation, no leading article: "The Tap!" -> ["tap"]."""
    words = re.sub(r"[^\w\s]", " ", text.lower()).split()
    while words and words[0] in _ARTICLES:
        words = words[1:]
    return words


def answers_match(a: str, b: str) -> bool:
    """Loose match: equal, or one answer's words all appear in the other ("Jay" vs "Jay Pritchett")."""
    wa, wb = set(normalise_answer(a)), set(normalise_answer(b))
    return bool(wa and wb) and (wa <= wb or wb <= wa)


def to_document(question: str, answer: str) -> str:
    """The text we embed for a question."""
    return f"{question.strip()} Answer: {answer.strip()}" if INCLUDE_ANSWER else question.strip()


@dataclass
class Match:
    question: str
    answer: str
    topic: str
    distance: float


def is_duplicate(match: Match, answer: str) -> bool:
    """The hybrid rule: a close question with the same answer, or a near-identical question."""
    if answers_match(match.answer, answer):
        return match.distance < same_answer_cutoff()
    return match.distance < any_answer_cutoff()


def find_duplicate(matches: list[Match], answer: str) -> Match | None:
    """The first of the nearest past questions that counts as a repeat, if any."""
    return next((m for m in matches if is_duplicate(m, answer)), None)


class QuestionMemory:
    """Thin wrapper around one ChromaDB collection.

    path=None gives an in-memory store (tests). embedding_function=None uses ChromaDB's default
    model (all-MiniLM-L6-v2, downloaded once to ~/.cache/chroma).
    """

    def __init__(self, path: str | None = None, embedding_function: Any = None,
                 collection: str = COLLECTION):
        import chromadb
        from chromadb.config import Settings

        settings = Settings(anonymized_telemetry=False)
        client = (chromadb.PersistentClient(path=path, settings=settings) if path
                  else chromadb.EphemeralClient(settings=settings))
        kwargs: dict[str, Any] = {"name": collection, "metadata": {"hnsw:space": "cosine"}}
        if embedding_function is not None:
            kwargs["embedding_function"] = embedding_function
        self._col = client.get_or_create_collection(**kwargs)

    def count(self) -> int:
        return self._col.count()

    def nearest(self, question: str, answer: str, k: int = NEIGHBOURS) -> list[Match]:
        """The k most similar stored questions, closest first (empty list if the memory is empty)."""
        count = self._col.count()
        if count == 0:
            return []
        res = self._col.query(query_texts=[to_document(question, answer)], n_results=min(k, count),
                              include=["metadatas", "distances"])
        return [Match(question=meta["question"], answer=meta["answer"], topic=meta["topic"], distance=float(d))
                for meta, d in zip(res["metadatas"][0], res["distances"][0])]

    def add(self, question: str, answer: str, topic: str, game_id: str) -> None:
        self._col.add(ids=[uuid.uuid4().hex], documents=[to_document(question, answer)],
                      metadatas=[{"question": question.strip(), "answer": answer.strip(),
                                  "topic": topic.strip().lower(), "game_id": game_id}])

    def warm_up(self) -> None:
        """Load the embedding model now, so the first question of the day isn't slow."""
        self._col.query(query_texts=["warm up"], n_results=1)  # embeds the text even if the store is empty


_memory: QuestionMemory | None = None


def get_memory() -> QuestionMemory:
    """The app-wide memory, stored on disk at CHROMA_PATH (default backend/chroma_data)."""
    global _memory
    if _memory is None:
        _memory = QuestionMemory(path=os.getenv("CHROMA_PATH", "chroma_data"))
    return _memory


def set_memory(memory: Any) -> None:
    """Swap the memory (tests use an in-memory or fake one)."""
    global _memory
    _memory = memory
