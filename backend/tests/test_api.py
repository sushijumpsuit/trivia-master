import pytest
from fastapi.testclient import TestClient

import main
from conftest import FakeLLM, reply, tool


@pytest.fixture
def client(monkeypatch):
    llm = FakeLLM([
        reply("", tool("generate_question", question="Capital of Malaysia?", answer="Kuala Lumpur", difficulty="easy")),
        reply("Hi! Capital of Malaysia?"),
        reply("", tool("check_answer", "a", player_answer="KL")),
        reply("", tool("update_score", "b", correct=True)),
        reply("", tool("generate_question", "c", question="Largest state?", answer="Sarawak", difficulty="medium")),
        reply("Yes! Largest state?"),
    ])
    monkeypatch.setattr(main, "get_llm", lambda: llm)
    return TestClient(main.app)


def test_start_then_answer(client):
    r = client.post("/game/start", json={"topic": "Malaysia"})
    assert r.status_code == 200
    body = r.json()
    assert body["current_question"] == "Capital of Malaysia?" and "Kuala Lumpur" not in str(body)

    r = client.post(f"/game/{body['game_id']}/answer", json={"answer": "KL"})
    body = r.json()
    assert body["score"] == 1 and body["last_result"] == {"correct": True, "answer": "Kuala Lumpur"}
    assert body["current_question"] == "Largest state?" and "Sarawak" not in str(body)


def test_validation_and_unknown_game(client):
    assert client.post("/game/start", json={"topic": ""}).status_code == 422
    assert client.post("/game/start", json={"topic": "x" * 81}).status_code == 422
    assert client.post("/game/nope/answer", json={"answer": "a"}).status_code == 404
