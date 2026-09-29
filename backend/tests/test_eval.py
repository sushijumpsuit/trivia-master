"""Tests for eval_game.py, using a fake model that follows the game rules (no API calls)."""
import difflib
import random
import re

import eval_game
from llm import LLM, LLMReply, ToolCall

eval_game.VERBOSE = False

WORDS = ["Colombia Station", "Neptune Harbour", "Jupiter Valley", "Everest Bridge", "Sahara Garden",
         "Amazon Tower", "Portugal Square", "Argentina Road", "Mercury Castle", "Kilimanjaro Park"]


class RulesLLM(LLM):
    """Plays host by the rules: asks unique questions, marks fairly (typos accepted), stops at round end."""
    provider, model = "fake", "rules-1"

    def __init__(self):
        self.n = 0

    def _question(self, intro=""):
        self.n += 1
        return ToolCall(f"q{self.n}", "generate_question",
                        {"question": f"Question number {self.n}?", "answer": WORDS[(self.n - 1) % len(WORDS)], "intro": intro})

    def chat(self, system, messages, tools, max_tokens=1024):
        if "Open question: none yet." in system:
            return LLMReply("", [self._question("Welcome!")], input_tokens=100, output_tokens=10)
        expected = re.search(r"Correct answer \(hidden from the player\): (.+)", system).group(1).strip()
        given = re.search(r"<player_answer>(.*)</player_answer>", messages[-1].content).group(1)
        ok = difflib.SequenceMatcher(None, given.lower(), expected.lower()).ratio() > 0.85
        calls = [ToolCall(f"s{self.n}", "update_score", {"correct": ok, "reaction": "Yes!" if ok else f"It's {expected}."})]
        if "LAST question of the round" not in system:
            calls.append(self._question())
        return LLMReply("", calls, input_tokens=100, output_tokens=10)


def test_full_eval_game_with_rule_following_model():
    llm = eval_game.CountingLLM(RulesLLM())
    report = eval_game.play_game(llm, ["Space", "Geography"], questions=3, accuracy=0.6, typo_rate=0.5,
                                 rng=random.Random(3))
    assert report.finished and len(report.accepted) == 6 and len(report.answers) == 6
    s = eval_game.summarize([report], price_in=0.30, price_out=1.20)
    assert s["questions_asked"] == 6 and s["games_finished"] == 1
    assert s["model_calls"] == 1 + 6 + 1          # start + one per answer + next round
    assert s["model_calls_per_question"] == round(8 / 6, 2)
    assert s["duplicate_rejections"] == 0 and s["possible_repeats_to_review"] == [] and s["failed_turns"] == []
    for key, got in s["judging"].items():        # the fake host marks fairly, so every ratio is n/n
        num, den = got.split("/")
        assert num == den, key
    assert s["tokens_per_question"] == {"input": 8 * 100 // 6, "output": 8 * 10 // 6}
    assert s["estimated_cost_usd"]["total"] == round(800 / 1e6 * 0.30 + 80 / 1e6 * 1.20, 4)


def test_failed_turn_is_recorded_and_the_game_stops():
    class Broken(LLM):
        provider, model = "fake", "broken"

        def chat(self, *a, **k):
            raise RuntimeError("provider down")

    report = eval_game.play_game(eval_game.CountingLLM(Broken()), ["Space"], 3, 0.6, 0.3, random.Random(1))
    assert not report.finished and report.turns[0].error.startswith("RuntimeError")


def test_typos_and_wrong_answers():
    rng = random.Random(0)
    typo = eval_game.make_typo("Colombia", rng)
    assert typo != "Colombia" and len(typo) in (7, 8) and typo[0] == "C"
    assert eval_game.make_typo("Lily", rng) is None      # too short to mangle fairly
    kinds = {eval_game.choose_answer("Neptune", ["Mars", "Neptune"], 0.5, 0.5, random.Random(s))[0] for s in range(40)}
    assert kinds == {"correct", "typo", "wrong"}
    kind, text = eval_game.choose_answer("Neptune", ["Mars"], 0.0, 0.0, random.Random(5))
    assert kind == "wrong" and text in ("Mars", "I don't know")


def test_possible_repeats_flag_matching_answers():
    accepted = [{"question": "Jay's dog?", "answer": "Stella"}, {"question": "Name the bulldog?", "answer": "stella"},
                {"question": "Phil's actor?", "answer": "Ty Burrell"}]
    assert eval_game.possible_repeats(accepted) == [("Jay's dog?", "Name the bulldog?")]



def test_rejections_in_a_failed_turn_are_still_counted():
    """A failed turn is rolled back (history too), so counting must not rely on history."""
    class Repeater(RulesLLM):
        def _question(self, intro=""):
            call = super()._question(intro)
            call.arguments["question"] = "The same question?"  # every question is an exact repeat
            return call

    report = eval_game.play_game(eval_game.CountingLLM(Repeater()), ["Space"], 3, 1.0, 0.0, random.Random(1))
    failed = [t for t in report.turns if t.error]
    assert failed and failed[0].other_tool_errors >= 5  # the in-game exact-repeat check kept rejecting



def test_game_limits_match_the_real_game(monkeypatch, capsys):
    import pytest
    for bad in (["--questions", "200"], ["--rounds", "6"], ["--questions", "2"]):
        monkeypatch.setattr("sys.argv", ["eval_game.py", *bad])
        with pytest.raises(SystemExit):
            eval_game.main()
    assert "questions 3-20" in capsys.readouterr().err
