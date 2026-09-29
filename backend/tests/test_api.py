import pytest
from fastapi.testclient import TestClient

import main
from conftest import FakeLLM, reply, tool


def q(id_, question, answer, intro=""):
    return tool("generate_question", id_, question=question, answer=answer, intro=intro)


def score(id_, correct, reaction):
    return tool("update_score", id_, correct=correct, reaction=reaction)


@pytest.fixture
def play(monkeypatch):
    """Returns (client, llm); the test sets llm.replies to script the host."""
    llm = FakeLLM([])
    monkeypatch.setattr(main, "get_llm", lambda: llm)
    return TestClient(main.app), llm


def test_two_rounds_end_to_end(play):
    client, llm = play
    llm.replies = [reply("", q("1", "Capital of Malaysia?", "Kuala Lumpur", intro="Round 1: Malaysia!"))]
    body = client.post("/game/start", json={"topics": ["Malaysia", "Space"], "rounds": 2, "questions_per_round": 3}).json()
    gid = body["game_id"]
    assert body["message"] == "Round 1: Malaysia!" and body["topics"] == ["Malaysia", "Space"]
    assert (body["round"], body["total_rounds"], body["round_question"]) == (1, 2, 1)
    assert "Kuala Lumpur" not in str(body)

    llm.replies = [reply("", score("s1", True, "Yes!"), q("2", "Largest state?", "Sarawak"))]
    body = client.post(f"/game/{gid}/answer", json={"answer": "KL"}).json()
    assert body["message"] == "Yes!" and body["last_result"] == {"correct": True, "answer": "Kuala Lumpur", "reaction": "Yes!"}
    assert body["current_question"] == "Largest state?" and "Sarawak" not in str(body)

    llm.replies = [reply("", score("s2", False, "It's Sarawak."), q("3", "Longest river?", "Rajang"))]
    client.post(f"/game/{gid}/answer", json={"answer": "Sabah"})
    llm.replies = [reply("", score("s3", True, "Round over!"))]
    body = client.post(f"/game/{gid}/answer", json={"answer": "Rajang"}).json()
    assert body["round_over"] and not body["finished"] and body["current_question"] is None
    assert body["round_scores"] == [2, 0]

    llm.replies = [reply("", q("4", "Closest star?", "The Sun", intro="Round 2: Space!"))]
    body = client.post(f"/game/{gid}/next-round").json()
    assert body["message"] == "Round 2: Space!" and body["topic"] == "Space" and body["round"] == 2


def test_topics_repeat_to_fill_rounds(play):
    client, llm = play
    llm.replies = [reply("", q("1", "q?", "a", intro="Hi"))]
    body = client.post("/game/start", json={"topics": ["Space", ""], "rounds": 3}).json()
    assert body["topics"] == ["Space", "Space", "Space"] and body["questions_per_round"] == 5


def test_validation(play):
    client, _ = play
    post = lambda payload: client.post("/game/start", json=payload).status_code
    assert post({"topics": []}) == 422
    assert post({"topics": ["", " "]}) == 422
    assert post({"topics": ["x" * 81]}) == 422
    assert post({"topics": ["a"], "rounds": 6}) == 422
    assert post({"topics": ["a"], "questions_per_round": 2}) == 422
    assert post({"topics": ["a"], "questions_per_round": 21}) == 422
    assert client.post("/game/nope/answer", json={"answer": "a"}).status_code == 404


def test_next_round_refused_mid_round(play):
    client, llm = play
    llm.replies = [reply("", q("1", "q?", "a", intro="Hi"))]
    gid = client.post("/game/start", json={"topics": ["a", "b"], "rounds": 2}).json()["game_id"]
    assert client.post(f"/game/{gid}/next-round").status_code == 409


def test_health_reports_stored_questions(play):
    client, llm = play
    llm.replies = [reply("", q("1", "q?", "a", intro="Hi"))]
    client.post("/game/start", json={"topics": ["Malaysia"]})
    assert client.get("/health").json()["questions_stored"] == 1
