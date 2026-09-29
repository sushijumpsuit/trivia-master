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
    assert new_memory().nearest("Capital of Malaysia?", "Kuala Lumpur") == []


def test_reworded_question_is_closer_than_unrelated_one():
    m = new_memory()
    m.add("What is the capital of Malaysia?", "Kuala Lumpur", "Geography", "easy", "g1")
    close = m.nearest("Which city is the capital of Malaysia?", "Kuala Lumpur")[0]
    far = m.nearest("Who painted the Mona Lisa?", "Leonardo da Vinci")[0]
    assert close.question == "What is the capital of Malaysia?" and close.topic == "geography"
    assert close.distance < far.distance


def test_exact_repeat_has_distance_near_zero():
    m = new_memory()
    m.add("Who plays Phil Dunphy?", "Ty Burrell", "Modern Family", "easy", "g1")
    assert m.nearest("Who plays Phil Dunphy?", "Ty Burrell")[0].distance < 0.01


def test_memory_survives_a_restart(tmp_path):
    name = f"test-{uuid.uuid4().hex}"
    new_memory(str(tmp_path), name).add("q one", "a", "t", "easy", "g")
    assert new_memory(str(tmp_path), name).count() == 1


def test_document_includes_answer_when_enabled(monkeypatch):
    monkeypatch.setattr(memory, "INCLUDE_ANSWER", True)
    assert memory.to_document(" Who? ", " Lily ") == "Who? Answer: Lily"
    monkeypatch.setattr(memory, "INCLUDE_ANSWER", False)
    assert memory.to_document("Who?", "Lily") == "Who?"


def test_cutoffs_can_be_overridden(monkeypatch):
    assert memory.same_answer_cutoff() == memory.DEFAULT_SAME_ANSWER_DISTANCE
    assert memory.any_answer_cutoff() == memory.DEFAULT_ANY_ANSWER_DISTANCE
    monkeypatch.setenv("DUP_SAME_ANSWER_DISTANCE", "0.4")
    monkeypatch.setenv("DUP_ANY_ANSWER_DISTANCE", "0.02")
    assert (memory.same_answer_cutoff(), memory.any_answer_cutoff()) == (0.4, 0.02)


def test_nearest_returns_up_to_k_closest_first():
    m = new_memory()
    for i, q in enumerate(["capital of malaysia", "capital of thailand", "largest ocean", "tallest mountain",
                           "fastest animal", "smallest planet"]):
        m.add(q, f"a{i}", "t", "easy", "g")
    got = m.nearest("capital of malaysia", "a0")
    assert len(got) == memory.NEIGHBOURS and got[0].question == "capital of malaysia"
    assert [x.distance for x in got] == sorted(x.distance for x in got)


# ---------- the hybrid rule (pure functions, real numbers from tune_threshold.py) ----------

@pytest.mark.parametrize("a, b, expected", [
    ("Jay Pritchett", "Jay", True), ("The Tap", "tap!", True), ("Lily", "Lily Tucker-Pritchett", True),
    ("Kuala Lumpur", "KUALA LUMPUR", True), ("Manny", "Javier", False), ("Bangkok", "Kuala Lumpur", False),
    ("", "Manny", False),
])
def test_answers_match_loosely(a, b, expected):
    assert memory.answers_match(a, b) is expected


@pytest.mark.parametrize("distance, stored, new, expected", [
    (0.441, "Jay Pritchett", "Jay Pritchett", True),   # loose rewording, same answer: missed by distance alone
    (0.433, "Los Angeles", "Los Angeles", True),       # same
    (0.028, "Kuala Lumpur", "Kuala Lumpur", True),     # clear rewording
    (0.107, "Manny", "Javier", False),                 # same wording, different fact: the old false alarm
    (0.304, "Kuala Lumpur", "Bangkok", False),         # capital of Malaysia vs Thailand
    (0.030, "Ty Burrell", "Ty Burel", True),           # near-identical question, answer typo
    (0.620, "Frank", "Frank", False),                  # same answer but a clearly different question
])
def test_hybrid_rule_on_real_distances(distance, stored, new, expected):
    assert memory.is_duplicate(memory.Match("q", stored, "t", distance), new) is expected


def test_find_duplicate_looks_past_a_closer_non_repeat():
    matches = [memory.Match("Gloria's first husband?", "Javier", "t", 0.10),
               memory.Match("Gloria's son from first marriage?", "Manny", "t", 0.30)]
    assert memory.find_duplicate(matches, "Manny").answer == "Manny"
    assert memory.find_duplicate(matches, "Luke") is None
