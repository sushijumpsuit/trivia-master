from conftest import FakeMemory
from game_state import GameState
from tools import run_tool


def new_game():
    return GameState(topics=["Malaysia"])


def test_full_question_cycle_updates_score_and_streak():
    g = new_game()
    assert run_tool(g, "generate_question", {"question": "Capital?", "answer": "Kuala Lumpur"})["status"] == "ok"
    assert g.awaiting_answer and g.question_number == 1
    g.player_answered = True
    assert run_tool(g, "update_score", {"correct": True, "reaction": "Yes!"}) == {"score": 1, "streak": 1}
    assert not g.awaiting_answer
    assert g.last_result == {"correct": True, "answer": "Kuala Lumpur", "reaction": "Yes!"}


def test_wrong_answer_resets_streak_but_keeps_best():
    g = new_game()
    for i, correct in enumerate((True, True, False)):
        run_tool(g, "generate_question", {"question": f"q{i}", "answer": "a"})
        g.player_answered = True
        run_tool(g, "update_score", {"correct": correct})
    assert (g.score, g.streak, g.best_streak) == (2, 0, 2)


def test_cannot_register_new_question_before_scoring():
    g = new_game()
    run_tool(g, "generate_question", {"question": "q1", "answer": "a"})
    result = run_tool(g, "generate_question", {"question": "q2", "answer": "b"})
    assert "error" in result and g.current_question == "q1" and g.question_number == 1


def test_cannot_score_twice():
    g = new_game()
    run_tool(g, "generate_question", {"question": "q", "answer": "a"})
    g.player_answered = True
    run_tool(g, "update_score", {"correct": True})
    assert "error" in run_tool(g, "update_score", {"correct": True})
    assert g.score == 1


def test_model_mistakes_return_errors_instead_of_crashing():
    g = new_game()
    assert "error" in run_tool(g, "no_such_tool", {})
    assert "error" in run_tool(g, "generate_question", {"question": "q"})  # missing args
    assert "error" in run_tool(g, "update_score", {"correct": True})  # no open question


def test_public_view_hides_open_answer():
    g = new_game()
    run_tool(g, "generate_question", {"question": "q", "answer": "secret"})
    assert "secret" not in str(g.public_view())


def test_cannot_score_a_question_the_player_has_not_answered():
    """Bug 1 regression: the model scored Q2 itself and jumped straight to Q3."""
    g = new_game()
    run_tool(g, "generate_question", {"question": "q1", "answer": "a"})
    g.player_answered = True
    run_tool(g, "update_score", {"correct": True})
    run_tool(g, "generate_question", {"question": "q2", "answer": "b"})
    assert "error" in run_tool(g, "update_score", {"correct": True})      # player never saw q2
    assert "error" in run_tool(g, "generate_question", {"question": "q3", "answer": "c"})
    assert (g.score, g.question_number, g.current_question) == (1, 2, "q2")


def test_same_question_cannot_be_asked_twice_in_a_game():
    """Bug 4 regression: the model registered Q4 with exactly the same text as Q3."""
    g = new_game()
    q = "What is the name of the governing body composed of multiple Ricks that oversees the multiverse?"
    run_tool(g, "generate_question", {"question": q, "answer": "Council of Ricks"})
    g.player_answered = True
    run_tool(g, "update_score", {"correct": False})
    again = run_tool(g, "generate_question", {"question": "  what is the NAME of the governing body composed of "
                                              "multiple Ricks that oversees the multiverse", "answer": "x"})
    assert "error" in again and g.question_number == 1 and not g.awaiting_answer
    assert run_tool(g, "generate_question", {"question": "Who is Morty's sister?", "answer": "Summer"})["status"] == "ok"



def test_long_rambling_answers_are_rejected():
    """Bug 6 regression (DeepSeek log): the stored 'answer' was a whole sentence."""
    g = new_game()
    rambling = 'Phil Dunphy is a realtor; his catchphrase is "Phil\'s-osophy" but the persona is simply "Phil Dunphy, Realtor."'
    assert "error" in run_tool(g, "generate_question", {"question": "q", "answer": rambling})
    assert g.question_number == 0 and not g.asked_questions  # rejected question isn't remembered either
    assert run_tool(g, "generate_question", {"question": "q", "answer": "Lily Tucker-Pritchett"})["status"] == "ok"


def test_check_answer_tool_is_gone():
    from tools import TOOL_SPECS
    assert [t.name for t in TOOL_SPECS] == ["generate_question", "update_score"]


# ---------- Phase 2: long-term memory ----------

def test_reworded_repeat_from_an_earlier_game_is_rejected(fake_memory):
    old = "In which country was Gloria Delgado-Pritchett born?"
    new = "Gloria Delgado-Pritchett hails from which South American country?"
    fake_memory.similar = FakeMemory(similar=[(old, new)]).similar
    run_tool(GameState(topics=["Modern Family"]), "generate_question",
             {"question": old, "answer": "Colombia"})
    g = GameState(topics=["modern family"])  # a new game
    result = run_tool(g, "generate_question", {"question": new, "answer": "Colombia"})
    assert "error" in result and old in result["error"]
    assert g.question_number == 0 and fake_memory.count() == 1  # rejected question isn't stored


def test_accepted_questions_are_stored_with_topic_and_game(fake_memory):
    g = GameState(topics=["Malaysia"])
    run_tool(g, "generate_question", {"question": "Capital?", "answer": "Kuala Lumpur"})
    assert fake_memory.items == [{"question": "Capital?", "answer": "Kuala Lumpur", "topic": "Malaysia",
                                  "game_id": g.id}]


def test_unrelated_question_is_accepted(fake_memory):
    run_tool(new_game(), "generate_question", {"question": "Capital of Malaysia?", "answer": "KL"})
    result = run_tool(new_game(), "generate_question", {"question": "Largest state?", "answer": "Sarawak"})
    assert result["status"] == "ok"


def test_broken_memory_does_not_stop_the_game():
    import memory
    memory.set_memory(FakeMemory(fail=True))
    assert run_tool(new_game(), "generate_question", {"question": "q", "answer": "a"})["status"] == "ok"



def test_same_wording_different_fact_is_accepted(fake_memory):
    """Bug 8 regression: the old single cutoff wrongly rejected this pair (distance 0.107)."""
    son = "What is the name of Gloria's son from her first marriage?"
    father = "What is the name of Manny's biological father, Gloria's first husband?"
    fake_memory.distances = FakeMemory(distances={(son, father): 0.107}).distances
    run_tool(new_game(), "generate_question", {"question": son, "answer": "Manny"})
    result = run_tool(new_game(), "generate_question", {"question": father, "answer": "Javier"})
    assert result["status"] == "ok"


def test_loose_rewording_with_same_answer_is_rejected(fake_memory):
    """Bug 8 regression: distance alone missed this repeat (0.441), the answer check catches it."""
    a = "Who is the patriarch of the Pritchett family, the father of Claire and Mitchell?"
    b = "What is the name of the family's grumpy but lovable patriarch, played by Ed O'Neill?"
    fake_memory.distances = FakeMemory(distances={(a, b): 0.441}).distances
    run_tool(new_game(), "generate_question", {"question": a, "answer": "Jay Pritchett"})
    result = run_tool(new_game(), "generate_question", {"question": b, "answer": "Jay Pritchett"})
    assert "error" in result and a in result["error"]


def test_extra_fields_from_the_model_are_ignored():
    """Difficulty was removed; a model that still sends it (or any unused field) shouldn't fail."""
    g = new_game()
    result = run_tool(g, "generate_question", {"question": "q", "answer": "a", "difficulty": "hard", "foo": 1})
    assert result["status"] == "ok" and "difficulty" not in g.public_view()



# ---------- rounds ----------

def test_no_extra_question_after_the_last_one_in_a_round():
    g = GameState(topics=["A", "B"], questions_per_round=3)
    for i in range(3):
        assert run_tool(g, "generate_question", {"question": f"q{i}", "answer": "x"})["status"] == "ok"
        g.player_answered = True
        result = run_tool(g, "update_score", {"correct": True, "reaction": "Yes!"})
    assert "round_over" in result and g.round_over and not g.finished
    assert "error" in run_tool(g, "generate_question", {"question": "q9", "answer": "x"})
    assert g.round_scores == [3, 0] and g.last_result["reaction"] == "Yes!"


def test_last_round_reports_game_over():
    g = GameState(topics=["A"], questions_per_round=3)
    for i in range(3):
        run_tool(g, "generate_question", {"question": f"q{i}", "answer": "x"})
        g.player_answered = True
        result = run_tool(g, "update_score", {"correct": i != 1, "reaction": "ok"})
    assert "game_over" in result and g.finished and g.round_scores == [2]


def test_intro_is_stored_and_old_reaction_field_still_works_as_intro():
    g = GameState(topics=["A"])
    run_tool(g, "generate_question", {"question": "q", "answer": "a", "intro": "Welcome to round 1!"})
    assert g.last_intro == "Welcome to round 1!"
    g2 = GameState(topics=["A"])
    run_tool(g2, "generate_question", {"question": "q2", "answer": "a", "reaction": "Hi!"})
    assert g2.last_intro == "Hi!"


def test_topics_repeat_in_order():
    from game_state import expand_topics
    assert expand_topics(["A", "B"], 3) == ["A", "B", "A"]
    assert expand_topics([" A ", ""], 2) == ["A", "A"]
