"""Auto-play Trivia Master with a simulated player and measure how the agent behaves.

Uses the real agent loop and the real LLM from backend/.env (this costs a little API credit).
The simulated player reads the stored answer and replies correctly, with a typo, or wrongly,
so we can also measure whether the host marks answers fairly.

Examples (from backend/, venv active):
  python eval_game.py                                   # 1 game, 2 rounds x 5, fresh memory
  python eval_game.py --topics "Modern Family" Space --rounds 2 --questions 5 --games 2
  python eval_game.py --memory real --topics "Modern Family"   # test a well-played topic

Reports are printed and saved as JSON in logs/ (git-ignored).
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import random
import tempfile
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any

from dotenv import load_dotenv

load_dotenv()

import agent  # noqa: E402
import memory  # noqa: E402
from game_state import GameState, expand_topics  # noqa: E402
from llm import LLM, LLMReply, Message, ToolSpec, get_llm, provider_settings  # noqa: E402

# USD per 1M tokens (input, output), cache-miss input price. Estimates only: providers change prices,
# and cache discounts are ignored, so the cost is an upper bound. Override with --price-in/--price-out.
PRICES = {"deepseek": (0.30, 1.20), "anthropic": (1.00, 5.00), "groq": (0.0, 0.0), "gemini": (0.0, 0.0),
          "openai": (0.0, 0.0)}


# ---------- measuring ----------

class CountingLLM(LLM):
    """Wraps the real LLM and records every call: tokens and time."""

    def __init__(self, inner: LLM):
        self.inner, self.provider, self.model = inner, inner.provider, inner.model
        self.calls = 0
        self.input_tokens = 0
        self.output_tokens = 0

    def chat(self, system: str, messages: list[Message], tools: list[ToolSpec], max_tokens: int = 1024) -> LLMReply:
        reply = self.inner.chat(system, messages, tools, max_tokens)
        self.calls += 1
        self.input_tokens += reply.input_tokens
        self.output_tokens += reply.output_tokens
        return reply


@dataclass
class TurnStat:
    kind: str            # start | answer | next_round
    round: int
    calls: int
    input_tokens: int
    output_tokens: int
    seconds: float
    duplicate_rejections: int
    other_tool_errors: int
    error: str | None = None


@dataclass
class AnswerStat:
    kind: str            # correct | typo | wrong
    expected: str
    given: str
    marked_correct: bool | None


@dataclass
class GameReport:
    topics: list[str]
    turns: list[TurnStat] = field(default_factory=list)
    answers: list[AnswerStat] = field(default_factory=list)
    accepted: list[dict] = field(default_factory=list)   # questions that reached the player
    finished: bool = False


# ---------- the simulated player ----------

def make_typo(answer: str, rng: random.Random) -> str | None:
    """Drop or swap one letter in the longest word ("Colombia" -> "Colmbia"). None if too short."""
    words = answer.split()
    i = max(range(len(words)), key=lambda k: len(words[k]))
    w = words[i]
    if len(w) < 5 or not w.isalpha():
        return None
    p = rng.randrange(1, len(w) - 1)
    w = w[:p] + w[p + 1:] if rng.random() < 0.5 else w[:p] + w[p + 1] + w[p] + w[p + 2:]
    return " ".join(words[:i] + [w] + words[i + 1:])


def choose_answer(expected: str, pool: list[str], accuracy: float, typo_rate: float,
                  rng: random.Random) -> tuple[str, str]:
    """Return (kind, text) for the player's answer."""
    if rng.random() < accuracy:
        typo = make_typo(expected, rng) if rng.random() < typo_rate else None
        return ("typo", typo) if typo else ("correct", expected)
    others = [a for a in pool if not memory.answers_match(a, expected)]
    if others and rng.random() < 0.5:
        return "wrong", rng.choice(others)   # a real answer, but to a different question
    return "wrong", "I don't know"


# ---------- playing ----------

class ToolErrorCounter(logging.Handler):
    """Counts rejected tool calls from the agent's log lines.

    Counting from the conversation history would miss failed turns: those are rolled back
    (agent.atomic), history included, but the log lines stay.
    """

    def __init__(self):
        super().__init__(level=logging.INFO)
        self.duplicates = 0
        self.other = 0

    def emit(self, record: logging.LogRecord) -> None:
        msg = record.getMessage()
        if record.name == "trivia.tools" and "dup-check REPEAT" in msg:
            self.duplicates += 1
        elif record.name == "trivia.agent" and "-> {'error'" in msg and "Too similar" not in msg:
            self.other += 1


_counter = ToolErrorCounter()
for _name in ("trivia.tools", "trivia.agent"):
    logging.getLogger(_name).addHandler(_counter)
    logging.getLogger(_name).setLevel(logging.INFO)


def _turn(llm: CountingLLM, state: GameState, kind: str, report: GameReport, fn, *args) -> bool:
    calls, tin, tout = llm.calls, llm.input_tokens, llm.output_tokens
    dup0, other0 = _counter.duplicates, _counter.other
    t0, error = time.perf_counter(), None
    try:
        fn(llm, state, *args)
    except Exception as e:  # record and stop this game; the turn was rolled back
        error = f"{type(e).__name__}: {e}"
    dup, other = _counter.duplicates - dup0, _counter.other - other0
    report.turns.append(TurnStat(kind, state.round_index + 1, llm.calls - calls, llm.input_tokens - tin,
                                 llm.output_tokens - tout, round(time.perf_counter() - t0, 2), dup, other, error))
    if error is None and state.awaiting_answer and state.current_question:
        if not report.accepted or report.accepted[-1]["question"] != state.current_question:
            report.accepted.append({"round": state.round_index + 1, "topic": state.topic,
                                    "question": state.current_question, "answer": state.current_answer})
    return error is None


def play_game(llm: CountingLLM, topics: list[str], questions: int, accuracy: float, typo_rate: float,
              rng: random.Random) -> GameReport:
    state = GameState(topics=topics, questions_per_round=questions)
    report = GameReport(topics=topics)
    if not _turn(llm, state, "start", report, agent.start_game):
        return report
    while True:
        expected = state.current_answer or ""
        pool = [a["answer"] for a in report.accepted]
        kind, given = choose_answer(expected, pool, accuracy, typo_rate, rng)
        if not _turn(llm, state, "answer", report, agent.answer, given):
            return report
        report.answers.append(AnswerStat(kind, expected, given, (state.last_result or {}).get("correct")))
        if state.finished:
            report.finished = True
            return report
        if state.round_over and not _turn(llm, state, "next_round", report, agent.next_round):
            return report


# ---------- reporting ----------

def possible_repeats(accepted: list[dict]) -> list[tuple[str, str]]:
    """Pairs of accepted questions with matching answers: candidates to review by hand."""
    pairs = []
    for i, a in enumerate(accepted):
        for b in accepted[i + 1:]:
            if memory.answers_match(a["answer"], b["answer"]):
                pairs.append((a["question"], b["question"]))
    return pairs


def summarize(reports: list[GameReport], price_in: float, price_out: float) -> dict[str, Any]:
    turns = [t for r in reports for t in r.turns]
    answers = [a for r in reports for a in r.answers]
    accepted = [q for r in reports for q in r.accepted]
    n_q = max(len(accepted), 1)
    ok_turns = [t for t in turns if t.error is None]
    tin, tout = sum(t.input_tokens for t in turns), sum(t.output_tokens for t in turns)
    cost = tin / 1e6 * price_in + tout / 1e6 * price_out

    def judged(kind: str, want: bool) -> str:
        items = [a for a in answers if a.kind == kind]
        return f"{sum(a.marked_correct is want for a in items)}/{len(items)}"

    return {
        "games": len(reports), "games_finished": sum(r.finished for r in reports),
        "questions_asked": len(accepted),
        "model_calls": sum(t.calls for t in turns),
        "model_calls_per_question": round(sum(t.calls for t in turns) / n_q, 2),
        "duplicate_rejections": sum(t.duplicate_rejections for t in turns),
        "other_tool_errors": sum(t.other_tool_errors for t in turns),
        "possible_repeats_to_review": possible_repeats(accepted),
        "judging": {"correct_accepted": judged("correct", True), "typos_accepted": judged("typo", True),
                    "wrong_rejected": judged("wrong", False)},
        "seconds_per_turn_avg": round(sum(t.seconds for t in ok_turns) / max(len(ok_turns), 1), 2),
        "seconds_per_turn_max": max((t.seconds for t in ok_turns), default=0),
        "tokens_per_question": {"input": tin // n_q, "output": tout // n_q},
        "estimated_cost_usd": {"per_question": round(cost / n_q, 5), "per_game": round(cost / max(len(reports), 1), 4),
                               "total": round(cost, 4), "note": "upper bound: ignores cache discounts"},
        "failed_turns": [t.error for t in turns if t.error],
    }


def print_summary(s: dict[str, Any], provider: str, model: str) -> None:
    j = s["judging"]
    print(f"\n=== Trivia Master eval: {provider} / {model} ===")
    print(f"Games: {s['games']} ({s['games_finished']} finished) | Questions asked: {s['questions_asked']}")
    print(f"Model calls per question: {s['model_calls_per_question']}  (total {s['model_calls']})")
    print(f"Duplicate rejections: {s['duplicate_rejections']} | Other tool errors: {s['other_tool_errors']}")
    print(f"Possible repeats to review: {len(s['possible_repeats_to_review'])}")
    for a, b in s["possible_repeats_to_review"]:
        print(f"  - {a!r}  vs  {b!r}")
    print(f"Marking: correct accepted {j['correct_accepted']}, typos accepted {j['typos_accepted']}, "
          f"wrong rejected {j['wrong_rejected']}")
    print(f"Time per turn: {s['seconds_per_turn_avg']} s avg, {s['seconds_per_turn_max']} s max")
    t = s["tokens_per_question"]
    c = s["estimated_cost_usd"]
    print(f"Tokens per question: {t['input']:,} in / {t['output']:,} out")
    print(f"Estimated cost: ${c['per_question']} per question, ${c['per_game']} per game ({c['note']})")
    print(f"Failed turns: {len(s['failed_turns'])}")
    for e in s["failed_turns"]:
        print(f"  - {e}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--topics", nargs="+", default=["Space exploration", "World geography"])
    ap.add_argument("--rounds", type=int, default=2)
    ap.add_argument("--questions", type=int, default=5, help="questions per round")
    ap.add_argument("--games", type=int, default=1)
    ap.add_argument("--accuracy", type=float, default=0.6, help="share of answers the player gets right")
    ap.add_argument("--typo-rate", type=float, default=0.3, help="share of right answers sent with a typo")
    ap.add_argument("--memory", choices=["fresh", "real"], default="fresh",
                    help="fresh = temporary ChromaDB per run (comparable runs); real = the game's memory")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--price-in", type=float, help="USD per 1M input tokens (overrides the table)")
    ap.add_argument("--price-out", type=float, help="USD per 1M output tokens (overrides the table)")
    args = ap.parse_args()

    provider, _, model, _ = provider_settings()
    price_in, price_out = PRICES.get(provider, (0.0, 0.0))
    price_in = args.price_in if args.price_in is not None else price_in
    price_out = args.price_out if args.price_out is not None else price_out
    total = args.games * args.rounds * args.questions
    print(f"Playing {args.games} game(s) x {args.rounds} round(s) x {args.questions} questions = {total} questions "
          f"on {provider}/{model} with {args.memory} memory...")

    tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True) if args.memory == "fresh" else None  # Windows may lock files
    if tmp:
        memory.set_memory(memory.QuestionMemory(path=tmp.name))
    rng = random.Random(args.seed)
    llm = CountingLLM(get_llm())
    reports = []
    for g in range(args.games):
        reports.append(play_game(llm, expand_topics(args.topics, args.rounds), args.questions,
                                 args.accuracy, args.typo_rate, rng))
        print(f"  game {g + 1}: {len(reports[-1].accepted)} questions, {'finished' if reports[-1].finished else 'stopped early'}")

    summary = summarize(reports, price_in, price_out)
    print_summary(summary, provider, model)
    os.makedirs("logs", exist_ok=True)
    path = f"logs/eval-{datetime.now():%Y%m%d-%H%M%S}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"settings": vars(args) | {"provider": provider, "model": model},
                   "summary": summary, "games": [asdict(r) for r in reports]}, f, indent=2, ensure_ascii=False)
    print(f"\nFull report: {path}")
    if tmp:
        memory.set_memory(None)
        tmp.cleanup()


if __name__ == "__main__":
    main()
