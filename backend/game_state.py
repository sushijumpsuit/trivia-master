"""Per-game state. The server, not the model, is the source of truth for score and answers."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from llm import Message



@dataclass
class GameState:
    topic: str
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    score: int = 0
    streak: int = 0
    best_streak: int = 0
    question_number: int = 0
    current_question: str | None = None
    current_answer: str | None = None   # never sent to the frontend while the question is open
    awaiting_answer: bool = False        # True between generate_question and update_score
    player_answered: bool = False        # True once the player submits an answer; unlocks update_score
    last_result: dict | None = None      # {"correct": bool, "answer": str} for the question just scored
    last_reaction: str = ""              # host's reaction, sent with the latest generate_question call
    asked_questions: list[str] = field(default_factory=list)  # normalised text of every question this game
    history: list[Message] = field(default_factory=list)

    def public_view(self) -> dict:
        """What the frontend is allowed to see (no hidden answer)."""
        return {"game_id": self.id, "topic": self.topic, "score": self.score, "streak": self.streak,
                "best_streak": self.best_streak, "question_number": self.question_number,
                "current_question": self.current_question,
                "last_result": self.last_result}


class GameStore:
    """In-memory store. Fine for Phase 1; games vanish on restart. Oldest games are evicted past the cap."""

    def __init__(self, max_games: int = 500):
        self._games: dict[str, GameState] = {}
        self._max = max_games

    def create(self, topic: str) -> GameState:
        if len(self._games) >= self._max:
            self._games.pop(next(iter(self._games)))  # dicts keep insertion order -> oldest first
        game = GameState(topic=topic)
        self._games[game.id] = game
        return game

    def get(self, game_id: str) -> GameState | None:
        return self._games.get(game_id)
