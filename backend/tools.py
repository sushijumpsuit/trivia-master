"""The tools the agent can call, defined once in provider-neutral form.

Each tool function validates the call against the game state. Invalid calls return
{"error": ...} instead of raising, so the model sees the problem and can correct itself.
"""
from __future__ import annotations

import re
from typing import Any, Callable

from game_state import DIFFICULTIES, GameState
from llm import ToolSpec

TOOL_SPECS: list[ToolSpec] = [
    ToolSpec(
        name="generate_question",
        description=("Register the next trivia question you have written. The answer is stored on the "
                     "server and hidden from the player. Call this exactly once per question, only after "
                     "the previous question has been scored."),
        parameters={"type": "object", "properties": {
            "question": {"type": "string", "description": "The question text shown to the player."},
            "answer": {"type": "string", "description": "The correct answer, short (a few words)."},
            "difficulty": {"type": "string", "enum": list(DIFFICULTIES)},
        }, "required": ["question", "answer", "difficulty"]},
    ),
    ToolSpec(
        name="check_answer",
        description=("Get the stored correct answer for the current question, to compare with the player's "
                     "answer. Judge meaning, not exact wording (e.g. 'KL' matches 'Kuala Lumpur')."),
        parameters={"type": "object", "properties": {
            "player_answer": {"type": "string", "description": "The player's answer, verbatim."},
        }, "required": ["player_answer"]},
    ),
    ToolSpec(
        name="update_score",
        description="Record whether the player's answer to the current question was correct. Call once per question.",
        parameters={"type": "object", "properties": {
            "correct": {"type": "boolean"},
        }, "required": ["correct"]},
    ),
]


def normalise_question(text: str) -> str:
    """Lowercase and drop punctuation/extra spaces, so trivial differences don't hide a repeat.

    Exact repeats only. Reworded repeats are Phase 2's job (ChromaDB similarity search).
    """
    return " ".join(re.sub(r"[^\w\s]", " ", text.lower()).split())


def generate_question(state: GameState, question: str, answer: str, difficulty: str) -> dict[str, Any]:
    if state.awaiting_answer:
        return {"error": "The current question hasn't been scored yet. Call check_answer and update_score first."}
    if difficulty not in DIFFICULTIES:
        return {"error": f"difficulty must be one of {DIFFICULTIES}"}
    if not question.strip() or not answer.strip():
        return {"error": "question and answer must not be empty"}
    key = normalise_question(question)
    if key in state.asked_questions:
        return {"error": "You already asked this question in this game. Write a different question."}
    state.asked_questions.append(key)
    state.question_number += 1
    state.current_question, state.current_answer = question.strip(), answer.strip()
    state.difficulty, state.awaiting_answer = difficulty, True
    state.player_answered = False
    return {"status": "ok", "question_number": state.question_number}


def check_answer(state: GameState, player_answer: str) -> dict[str, Any]:
    if not state.awaiting_answer:
        return {"error": "There is no open question to check."}
    if not state.player_answered:
        return {"error": "The player hasn't answered the current question yet. Wait for their answer."}
    return {"expected_answer": state.current_answer, "player_answer": player_answer}


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
    "check_answer": check_answer,
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
