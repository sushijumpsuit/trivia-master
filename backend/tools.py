"""The tools the agent can call, defined once in provider-neutral form.

Each tool function validates the call against the game state. Invalid calls return
{"error": ...} instead of raising, so the model sees the problem and can correct itself.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Callable

import memory
from game_state import GameState
from llm import ToolSpec

log = logging.getLogger("trivia.tools")

TOOL_SPECS: list[ToolSpec] = [
    ToolSpec(
        name="generate_question",
        description=("Register the next trivia question you have written. The answer is stored on the "
                     "server and hidden from the player. Call this once per question, only after the previous "
                     "question has been scored, and never after the last question of a round. "
                     "This ends your turn."),
        parameters={"type": "object", "properties": {
            "question": {"type": "string", "description": "Only the question itself: no greeting, no 'Next up'."},
            "answer": {"type": "string", "description": "The correct answer: a name, number or at most 8 words."},
            "intro": {"type": "string", "description": (
                "Only for the first question of a round: one short sentence welcoming the player to the "
                "round and its topic. Leave empty otherwise.")},
        }, "required": ["question", "answer"]},
    ),
    ToolSpec(
        name="update_score",
        description=("Record whether the player's answer to the current question was correct, with your "
                     "reaction. Call once per answer. The result tells you if the round is over."),
        parameters={"type": "object", "properties": {
            "correct": {"type": "boolean"},
            "reaction": {"type": "string", "description": (
                "1-2 short sentences, plain text: say if they were right, and give the correct answer if they "
                "missed it. Never include the next question.")},
        }, "required": ["correct", "reaction"]},
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
        matches = memory.get_memory().nearest(question, answer)
    except Exception as e:  # ChromaDB/embedding failure
        log.warning("[game %s] memory check failed, skipping: %s", state.id[:6], e)
        return None
    if not matches:
        return None
    duplicate = memory.find_duplicate(matches, answer)
    top = matches[0]
    # Logged for every check, so real games keep giving data to confirm the cutoffs.
    log.info("[game %s] dup-check %s | nearest distance=%.3f same_answer=%s q=%r a=%r", state.id[:6],
             "REPEAT" if duplicate else "ok", top.distance, memory.answers_match(top.answer, answer),
             top.question, top.answer)
    if duplicate:
        return {"error": (f"Too similar to a question already asked: \"{duplicate.question}\" "
                          f"(answer: {duplicate.answer}). Write a question about a different, less obvious fact "
                          f"whose answer is not in the already-used list.")}
    return None


def remember(state: GameState, question: str, answer: str) -> None:
    try:
        memory.get_memory().add(question, answer, state.topic, state.id)
    except Exception as e:
        log.warning("[game %s] could not save question to memory: %s", state.id[:6], e)


def generate_question(state: GameState, question: str, answer: str, intro: str = "",
                      **_ignored: Any) -> dict[str, Any]:
    # **_ignored: some models add fields we don't use (e.g. an old "difficulty"); ignore them
    # instead of failing the call.
    if state.is_last_question_of_round:
        return {"error": "This round's questions are all used. Don't register another question."}
    if state.awaiting_answer:
        return {"error": "The current question hasn't been scored yet. Call update_score first."}
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
    state.used_answers.append(answer.strip())
    remember(state, question, answer)
    state.question_number += 1
    state.round_question += 1
    state.current_question, state.current_answer = question.strip(), answer.strip()
    state.awaiting_answer = True
    state.last_intro = (intro or str(_ignored.get("reaction", ""))).strip()
    state.player_answered = False
    return {"status": "ok", "question_number": state.question_number}


def update_score(state: GameState, correct: bool, reaction: str = "", **_ignored: Any) -> dict[str, Any]:
    if not state.awaiting_answer:
        return {"error": "There is no open question to score (already scored?)."}
    if not state.player_answered:
        return {"error": "The player hasn't answered the current question yet. Only score answers the player gave."}
    correct = bool(correct)
    if correct:
        state.score += 1
        state.round_scores[state.round_index] += 1
        state.streak += 1
        state.best_streak = max(state.best_streak, state.streak)
    else:
        state.streak = 0
    state.last_result = {"correct": correct, "answer": state.current_answer, "reaction": reaction.strip()}
    state.awaiting_answer = False
    state.player_answered = False
    state.scored_count += 1
    result: dict[str, Any] = {"score": state.score, "streak": state.streak}
    if state.finished:
        result["game_over"] = "That was the last question of the game. Stop here."
    elif state.round_over:
        result["round_over"] = "That was the last question of this round. Stop here; don't register a question."
    return result


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
