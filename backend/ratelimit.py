"""Usage limits for the public demo, so strangers can't run up the LLM bill.

Checked once, when a game starts: the whole game's questions (rounds x questions per round) are
reserved up front. Kept in memory, so limits reset if the server restarts; that's fine for one small
server. Days are counted in UTC.

Settings (0 turns a limit off):
  IP_GAMES_PER_HOUR      games one visitor can start per hour           (default 5)
  IP_QUESTIONS_PER_DAY   questions one visitor can play per day         (default 100)
  DAILY_QUESTION_LIMIT   questions everyone together can play per day   (default 300, about $0.55)
"""
import os
import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timezone


class LimitExceeded(Exception):
    """The request would go over a limit. The message is safe to show to the player."""


def _env_int(name: str, default: int) -> int:
    try:
        return max(0, int(os.getenv(name, default)))
    except ValueError:
        return default


class RateLimiter:
    def __init__(self, games_per_hour: int, ip_questions_per_day: int, daily_questions: int, clock=time.time):
        self.games_per_hour = games_per_hour
        self.ip_questions_per_day = ip_questions_per_day
        self.daily_questions = daily_questions
        self._clock = clock
        self._lock = threading.Lock()  # FastAPI runs sync routes in a thread pool
        self._starts: dict[str, deque[float]] = defaultdict(deque)
        self._day = ""
        self._ip_questions: dict[str, int] = defaultdict(int)
        self._total_questions = 0

    @classmethod
    def from_env(cls) -> "RateLimiter":
        return cls(_env_int("IP_GAMES_PER_HOUR", 5), _env_int("IP_QUESTIONS_PER_DAY", 100),
                   _env_int("DAILY_QUESTION_LIMIT", 300))

    def _roll_day(self, now: float) -> None:
        day = datetime.fromtimestamp(now, timezone.utc).strftime("%Y-%m-%d")
        if day != self._day:
            self._day, self._ip_questions, self._total_questions = day, defaultdict(int), 0

    def reserve_game(self, ip: str, questions: int) -> None:
        """Record a new game, or raise LimitExceeded without recording anything."""
        with self._lock:
            now = self._clock()
            self._roll_day(now)
            starts = self._starts[ip]
            while starts and now - starts[0] >= 3600:
                starts.popleft()
            if self.daily_questions and self._total_questions + questions > self.daily_questions:
                left = self.daily_questions - self._total_questions
                raise LimitExceeded("The demo has reached today's question limit. Please come back tomorrow."
                                    if left < 3 else
                                    f"Only {left} questions are left in today's demo limit. Try a shorter game.")
            if self.ip_questions_per_day and self._ip_questions[ip] + questions > self.ip_questions_per_day:
                raise LimitExceeded("You've reached today's question limit for this demo. Please come back tomorrow, "
                                    "or try a shorter game.")
            if self.games_per_hour and len(starts) >= self.games_per_hour:
                raise LimitExceeded("Too many new games in the last hour. Please wait a bit and try again.")
            starts.append(now)
            self._ip_questions[ip] += questions
            self._total_questions += questions

    def usage(self) -> dict:
        with self._lock:
            self._roll_day(self._clock())
            return {"questions_today": self._total_questions, "daily_question_limit": self.daily_questions}
