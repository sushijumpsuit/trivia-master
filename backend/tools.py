"""The tools the agent can call, defined once in provider-neutral form.

Each tool function validates the call against the game state. Invalid calls return
{"error": ...} instead of raising, so the model sees the problem and can correct itself.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Callable

import memory
from game_state import DIFFICULTIES, GameState
from llm import ToolSpec

log = logging.getLogger("trivia.tools")

TOOL_SPECS: list[ToolSpec] = [
    ToolSpec(
        name="generate_question",
        description=("Register the next trivia question you have written, together with your reaction to "
                     "the player's last answer. The answer is stored on the server and hidden from the player. "
                     "Call this exactly once per question, only after the previous question has been scored. "
                     "This ends your turn: the game shows your reaction and then the question."),
        parameters={"type": "object", "properties": {
            "reaction": {"type": "string", "description": (
                "What you say to the player before the question, 1-2 short sentences, plain text. On the "
                "first question: a greeting. After an answer: say if they were right, and give the correct "
                "answer if they missed it. Never include the new question or its answer.")},
            "question": {"type": "string", "description": "The question text shown to the player."},
            "answer": {"type": "string", "description": "The correct answer: a name, number or at most 8 words."},
            "difficulty": {"type": "string", "enum": list(DIFFICULTIES)},
        }, "required": ["reaction", "question", "answer", "difficulty"]},
    ),
    ToolSpec(
        name="update_score",
        description="Record whether the player's answer to the current question was correct. Call once per question.",
        parameters={"type": "object", "properties": {
            "correct": {"type": "boolean"},
        }, "required": ["correct"]},
    ),
]


MAX_ANSWER_WORDS = 8
MAX_ANSWER_CHARS = 80


def normalise_question(text: str) -> str:
    """Lowercase and drop punctuation/extra spaces, so trivial differences don't hide a repeat.

    A cheap exact check within one game. Reworded repeats, across all games, are caught by the
    ChromaDB similarity check in check_memory().
    """
    return " ".join(re.sub(r"[^\w\s]", " ", text.lower()).split())


def check_memory(state: GameState, question: str, answer: str) -> dict[str, Any] | None:
    """Return an error if a past question (any game) means the same thing, else None.

    If the memory itself fails, log it and let the question through: a broken memory
    shouldn't stop the game.
    """
    try:
        match = memory.get_memory().nearest(question, answer)
    except Exception as e:  # ChromaDB/embedding failure
        log.warning("[game %s] memory check failed, skipping: %s", state.id[:6], e)
        return None
    if match is None:
        return None
    threshold = memory.duplicate_threshold()
    log.info("[game %s] dup-check distance=%.3f (cutoff %.2f) nearest=%r", state.id[:6], match.distance,
             threshold, match.question)
    if match.distance < threshold:
        return {"error": (f"Too similar to a question already asked: \"{match.question}\" "
                          f"(answer: {match.answer}). Write a question about a different fact.")}
    return None


def remember(state: GameState, question: str, answer: str, difficulty: str) -> None:
    try:
        memory.get_memory().add(question, answer, state.topic, difficulty, state.id)
    except Exception as e:
        log.warning("[game %s] could not save question to memory: %s", state.id[:6], e)


def generate_question(state: GameState, question: str, answer: str, difficulty: str,
                      reaction: str = "") -> dict[str, Any]:
    if state.awaiting_answer:
        return {"error": "The current question hasn't been scored yet. Call update_score first."}
    if difficulty not in DIFFICULTIES:
        return {"error": f"difficulty must be one of {DIFFICULTIES}"}
    if not question.strip() or not answer.strip():
        return {"error": "question and answer must not be empty"}
    if len(answer.split()) > MAX_ANSWER_WORDS or len(answer) > MAX_ANSWER_CHARS:
        return {"error": (f"The answer is too long. Use a short answer (a name, number or at most "
                          f"{MAX_ANSWER_WORDS} words) and pick a question with one clear answer.")}
    key = normalise_question(question)
    if key in state.asked_questions:
        return {"error": "You already asked this question in this game. Write a different question."}
    if (error := check_memory(state, question, answer)) is not None:
        return error
    state.asked_questions.append(key)
    remember(state, question, answer, difficulty)
    state.question_number += 1
    state.current_question, state.current_answer = question.strip(), answer.strip()
    state.difficulty, state.awaiting_answer = difficulty, True
    state.last_reaction = reaction.strip()
    state.player_answered = False
    return {"status": "ok", "question_number": state.question_number}


def update_score(state: GameState, correct: bool) -> dict[str, Any]:
    if not state.awaiting_answer:
        return {"error": "There is no open question to score (already scored?)."}
    if not state.player_answered:
        return {"error": "The player hasn't answered the current question yet. Only score answers the player gave."}
    correct = bool(correct)
    if correct:
        state.score += 1
        state.streak += 1
        state.best_streak = max(state.best_streak, state.streak)
    else:
        state.streak = 0
    state.last_result = {"correct": correct, "answer": state.current_answer}
    state.awaiting_answer = False
    state.player_answered = False
    return {"score": state.score, "streak": state.streak}


_TOOL_FUNCS: dict[str, Callable[..., dict[str, Any]]] = {
    "generate_question": generate_question,
    "update_score": update_score,
}


def run_tool(state: GameState, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Dispatch a tool call from the model. Never raises for model mistakes."""
    func = _TOOL_FUNCS.get(name)
    if func is None:
        return {"error": f"Unknown tool '{name}'."}
    try:
        return func(state, **arguments)
    except TypeError as e:  # wrong or missing arguments
        return {"error": f"Bad arguments for {name}: {e}"}
