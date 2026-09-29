import pytest
from fastapi.testclient import TestClient

import main
from conftest import FakeLLM, reply, tool
from ratelimit import LimitExceeded, RateLimiter


class Clock:
    def __init__(self, t=1_800_000_000.0):
        self.t = t

    def __call__(self):
        return self.t


def test_games_per_hour_per_visitor():
    clock = Clock()
    lim = RateLimiter(games_per_hour=2, ip_questions_per_day=0, daily_questions=0, clock=clock)
    lim.reserve_game("a", 3)
    lim.reserve_game("a", 3)
    with pytest.raises(LimitExceeded, match="last hour"):
        lim.reserve_game("a", 3)
    lim.reserve_game("b", 3)          # other visitors are not affected
    clock.t += 3600
    lim.reserve_game("a", 3)          # the hour has passed


def test_questions_per_visitor_per_day():
    clock = Clock()
    lim = RateLimiter(games_per_hour=0, ip_questions_per_day=30, daily_questions=0, clock=clock)
    lim.reserve_game("a", 20)
    with pytest.raises(LimitExceeded, match="come back tomorrow"):
        lim.reserve_game("a", 20)
    lim.reserve_game("a", 10)          # a shorter game still fits
    clock.t += 86400
    lim.reserve_game("a", 20)          # new day


def test_daily_limit_for_everyone():
    lim = RateLimiter(games_per_hour=0, ip_questions_per_day=0, daily_questions=50, clock=Clock())
    lim.reserve_game("a", 40)
    with pytest.raises(LimitExceeded, match="Only 10 questions are left"):
        lim.reserve_game("b", 20)
    lim.reserve_game("b", 10)
    with pytest.raises(LimitExceeded, match="come back tomorrow"):
        lim.reserve_game("c", 3)
    assert lim.usage() == {"questions_today": 50, "daily_question_limit": 50}


def test_a_refused_game_uses_no_quota():
    lim = RateLimiter(games_per_hour=1, ip_questions_per_day=0, daily_questions=100, clock=Clock())
    lim.reserve_game("a", 5)
    with pytest.raises(LimitExceeded):
        lim.reserve_game("a", 5)
    assert lim.usage()["questions_today"] == 5


def test_zero_turns_limits_off():
    lim = RateLimiter(0, 0, 0, clock=Clock())
    for _ in range(50):
        lim.reserve_game("a", 100)


def test_env_settings(monkeypatch):
    monkeypatch.setenv("IP_GAMES_PER_HOUR", "7")
    monkeypatch.setenv("DAILY_QUESTION_LIMIT", "not a number")
    lim = RateLimiter.from_env()
    assert (lim.games_per_hour, lim.ip_questions_per_day, lim.daily_questions) == (7, 100, 300)


def test_start_returns_429_and_does_not_call_the_llm(monkeypatch):
    llm = FakeLLM([reply("", tool("generate_question", "1", question="Q?", answer="A", intro="Hi"))])
    monkeypatch.setattr(main, "get_llm", lambda: llm)
    monkeypatch.setattr(main, "limiter", RateLimiter(1, 0, 0))
    client = TestClient(main.app)
    body = {"topics": ["Space"], "rounds": 1, "questions_per_round": 3}
    assert client.post("/game/start", json=body).status_code == 200
    res = client.post("/game/start", json=body)
    assert res.status_code == 429 and "last hour" in res.json()["detail"]
    assert len(llm.calls) == 1
