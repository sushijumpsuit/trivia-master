"""Per-game state. The server, not the model, is the source of truth for score, answers and rounds."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from llm import Message


@dataclass
class GameState:
    topics: list[str]                    # one topic per round (already expanded, e.g. [A, B, A])
    questions_per_round: int = 5
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    round_index: int = 0                 # 0-based
    round_question: int = 0              # questions registered in the current round
    round_scores: list[int] = field(default_factory=list)
    score: int = 0
    streak: int = 0
    best_streak: int = 0
    question_number: int = 0             # questions registered in the whole game
    scored_count: int = 0                # answers scored in the whole game
    current_question: str | None = None
    current_answer: str | None = None    # never sent to the frontend while the question is open
    awaiting_answer: bool = False        # True between generate_question and update_score
    player_answered: bool = False        # True once the player submits an answer; unlocks update_score
    last_result: dict | None = None      # {"correct", "answer", "reaction"} for the question just scored
    last_intro: str = ""                 # host's intro for the first question of a round
    used_answers: list[str] = field(default_factory=list)  # answers to avoid this round (memory + this game)
    asked_questions: list[str] = field(default_factory=list)  # normalised text of every question this game
    past_questions: list[str] = field(default_factory=list)  # "question (answer)" on this topic, shown to the model
    history: list[Message] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.topics:
            raise ValueError("a game needs at least one topic")
        if not self.round_scores:
            self.round_scores = [0] * len(self.topics)

    @property
    def topic(self) -> str:
        return self.topics[self.round_index]

    @property
    def total_rounds(self) -> int:
        return len(self.topics)

    @property
    def is_last_question_of_round(self) -> bool:
        return self.round_question >= self.questions_per_round

    @property
    def round_over(self) -> bool:
        """All of this round's questions have been asked and scored."""
        return self.is_last_question_of_round and not self.awaiting_answer

    @property
    def finished(self) -> bool:
        return self.round_over and self.round_index == self.total_rounds - 1

    def public_view(self) -> dict:
        """What the frontend is allowed to see (no hidden answer)."""
        return {"game_id": self.id, "topic": self.topic, "topics": self.topics,
                "round": self.round_index + 1, "total_rounds": self.total_rounds,
                "questions_per_round": self.questions_per_round, "round_question": self.round_question,
                "round_scores": self.round_scores, "score": self.score, "streak": self.streak,
                "best_streak": self.best_streak, "question_number": self.question_number,
                "current_question": self.current_question if self.awaiting_answer else None,
                "last_result": self.last_result, "round_over": self.round_over, "finished": self.finished}


def expand_topics(topics: list[str], rounds: int) -> list[str]:
    """Repeat the chosen topics in order to fill every round: [A, B] over 3 rounds -> [A, B, A]."""
    clean = [t.strip() for t in topics if t.strip()]
    if not clean:
        raise ValueError("at least one topic is required")
    return [clean[i % len(clean)] for i in range(rounds)]


class GameStore:
    """In-memory store; games vanish on restart. Oldest games are evicted past the cap."""

    def __init__(self, max_games: int = 500):
        self._games: dict[str, GameState] = {}
        self._max = max_games

    def create(self, topics: list[str], questions_per_round: int = 5) -> GameState:
        if len(self._games) >= self._max:
            self._games.pop(next(iter(self._games)))  # dicts keep insertion order -> oldest first
        game = GameState(topics=topics, questions_per_round=questions_per_round)
        self._games[game.id] = game
        return game

    def get(self, game_id: str) -> GameState | None:
        return self._games.get(game_id)
