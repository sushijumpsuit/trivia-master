"""Tests for memory.py against real ChromaDB, with a fake embedding model (no download)."""
import uuid

import pytest

pytest.importorskip("chromadb")

import memory  # noqa: E402
from fake_embeddings import HashEF  # noqa: E402


def new_memory(path=None, name=None):
    # EphemeralClients share state inside one process, so give every test its own collection.
    return memory.QuestionMemory(path=path, embedding_function=HashEF(), collection=name or f"test-{uuid.uuid4().hex}")


def test_empty_memory_has_no_match():
    assert new_memory().nearest("Capital of Malaysia?", "Kuala Lumpur") is None


def test_reworded_question_is_closer_than_unrelated_one():
    m = new_memory()
    m.add("What is the capital of Malaysia?", "Kuala Lumpur", "Geography", "easy", "g1")
    close = m.nearest("Which city is the capital of Malaysia?", "Kuala Lumpur")
    far = m.nearest("Who painted the Mona Lisa?", "Leonardo da Vinci")
    assert close.question == "What is the capital of Malaysia?" and close.topic == "geography"
    assert close.distance < far.distance


def test_exact_repeat_has_distance_near_zero():
    m = new_memory()
    m.add("Who plays Phil Dunphy?", "Ty Burrell", "Modern Family", "easy", "g1")
    assert m.nearest("Who plays Phil Dunphy?", "Ty Burrell").distance < 0.01


def test_memory_survives_a_restart(tmp_path):
    name = f"test-{uuid.uuid4().hex}"
    new_memory(str(tmp_path), name).add("q one", "a", "t", "easy", "g")
    assert new_memory(str(tmp_path), name).count() == 1


def test_document_includes_answer_when_enabled(monkeypatch):
    monkeypatch.setattr(memory, "INCLUDE_ANSWER", True)
    assert memory.to_document(" Who? ", " Lily ") == "Who? Answer: Lily"
    monkeypatch.setattr(memory, "INCLUDE_ANSWER", False)
    assert memory.to_document("Who?", "Lily") == "Who?"


def test_threshold_can_be_overridden(monkeypatch):
    assert memory.duplicate_threshold() == memory.DEFAULT_DUPLICATE_DISTANCE
    monkeypatch.setenv("DUPLICATE_DISTANCE", "0.3")
    assert memory.duplicate_threshold() == 0.3
