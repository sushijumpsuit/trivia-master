"""Long-term question memory (ChromaDB), so the game never repeats a question, even reworded.

How it works:
- Every accepted question is embedded (turned into a vector that captures its meaning) and saved
  to a persistent ChromaDB collection on disk, so it survives restarts and new games.
- Before a new question is accepted, we find the most similar past question. If its cosine
  distance is below DUPLICATE_DISTANCE, the new question counts as a repeat and is rejected.

All ChromaDB code lives in this file (see CLAUDE.md).
"""
from __future__ import annotations

import logging
import os
import uuid
from dataclasses import dataclass
from typing import Any

log = logging.getLogger("trivia.memory")

COLLECTION = "questions"

# Store question + answer together. Reworded repeats share the answer; different facts that use the
# same wording ("Gloria's son?" = Manny vs "Gloria's first husband?" = Javier) don't, which pushes
# them further apart. tune_threshold.py measures both modes on real question pairs.
INCLUDE_ANSWER = True

# Cosine distance (0 = same meaning, bigger = less similar) below which a question is a repeat.
# Provisional until confirmed with tune_threshold.py on real pairs; override with DUPLICATE_DISTANCE.
DEFAULT_DUPLICATE_DISTANCE = 0.25


def duplicate_threshold() -> float:
    return float(os.getenv("DUPLICATE_DISTANCE", DEFAULT_DUPLICATE_DISTANCE))


def to_document(question: str, answer: str) -> str:
    """The text we embed for a question."""
    return f"{question.strip()} Answer: {answer.strip()}" if INCLUDE_ANSWER else question.strip()


@dataclass
class Match:
    question: str
    answer: str
    topic: str
    distance: float


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

    def nearest(self, question: str, answer: str) -> Match | None:
        """The most similar stored question, or None if the memory is empty."""
        if self._col.count() == 0:
            return None
        res = self._col.query(query_texts=[to_document(question, answer)], n_results=1,
                              include=["metadatas", "distances"])
        meta = res["metadatas"][0][0]
        return Match(question=meta["question"], answer=meta["answer"], topic=meta["topic"],
                     distance=float(res["distances"][0][0]))

    def add(self, question: str, answer: str, topic: str, difficulty: str, game_id: str) -> None:
        self._col.add(ids=[uuid.uuid4().hex], documents=[to_document(question, answer)],
                      metadatas=[{"question": question.strip(), "answer": answer.strip(),
                                  "topic": topic.strip().lower(), "difficulty": difficulty,
                                  "game_id": game_id}])

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
