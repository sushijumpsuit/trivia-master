from game_state import GameState
from tools import run_tool


def new_game():
    return GameState(topic="Malaysia")


def test_full_question_cycle_updates_score_and_streak():
    g = new_game()
    assert run_tool(g, "generate_question", {"question": "Capital?", "answer": "Kuala Lumpur", "difficulty": "easy"})["status"] == "ok"
    assert g.awaiting_answer and g.question_number == 1
    g.player_answered = True
    assert run_tool(g, "check_answer", {"player_answer": "KL"})["expected_answer"] == "Kuala Lumpur"
    assert run_tool(g, "update_score", {"correct": True}) == {"score": 1, "streak": 1}
    assert not g.awaiting_answer
    assert g.last_result == {"correct": True, "answer": "Kuala Lumpur"}


def test_wrong_answer_resets_streak_but_keeps_best():
    g = new_game()
    for i, correct in enumerate((True, True, False)):
        run_tool(g, "generate_question", {"question": f"q{i}", "answer": "a", "difficulty": "easy"})
        g.player_answered = True
        run_tool(g, "update_score", {"correct": correct})
    assert (g.score, g.streak, g.best_streak) == (2, 0, 2)


def test_cannot_register_new_question_before_scoring():
    g = new_game()
    run_tool(g, "generate_question", {"question": "q1", "answer": "a", "difficulty": "easy"})
    result = run_tool(g, "generate_question", {"question": "q2", "answer": "b", "difficulty": "easy"})
    assert "error" in result and g.current_question == "q1" and g.question_number == 1


def test_cannot_score_twice():
    g = new_game()
    run_tool(g, "generate_question", {"question": "q", "answer": "a", "difficulty": "easy"})
    g.player_answered = True
    run_tool(g, "update_score", {"correct": True})
    assert "error" in run_tool(g, "update_score", {"correct": True})
    assert g.score == 1


def test_model_mistakes_return_errors_instead_of_crashing():
    g = new_game()
    assert "error" in run_tool(g, "no_such_tool", {})
    assert "error" in run_tool(g, "generate_question", {"question": "q"})  # missing args
    assert "error" in run_tool(g, "generate_question", {"question": "q", "answer": "a", "difficulty": "insane"})
    assert "error" in run_tool(g, "check_answer", {"player_answer": "x"})  # no open question


def test_public_view_hides_open_answer():
    g = new_game()
    run_tool(g, "generate_question", {"question": "q", "answer": "secret", "difficulty": "easy"})
    assert "secret" not in str(g.public_view())


def test_cannot_score_or_check_a_question_the_player_has_not_answered():
    """Bug 1 regression: the model scored Q2 itself and jumped straight to Q3."""
    g = new_game()
    run_tool(g, "generate_question", {"question": "q1", "answer": "a", "difficulty": "easy"})
    g.player_answered = True
    run_tool(g, "update_score", {"correct": True})
    run_tool(g, "generate_question", {"question": "q2", "answer": "b", "difficulty": "easy"})
    assert "error" in run_tool(g, "update_score", {"correct": True})      # player never saw q2
    assert "error" in run_tool(g, "check_answer", {"player_answer": "b"})
    assert "error" in run_tool(g, "generate_question", {"question": "q3", "answer": "c", "difficulty": "easy"})
    assert (g.score, g.question_number, g.current_question) == (1, 2, "q2")


def test_same_question_cannot_be_asked_twice_in_a_game():
    """Bug 4 regression: the model registered Q4 with exactly the same text as Q3."""
    g = new_game()
    q = "What is the name of the governing body composed of multiple Ricks that oversees the multiverse?"
    run_tool(g, "generate_question", {"question": q, "answer": "Council of Ricks", "difficulty": "easy"})
    g.player_answered = True
    run_tool(g, "update_score", {"correct": False})
    again = run_tool(g, "generate_question", {"question": "  what is the NAME of the governing body composed of "
                                              "multiple Ricks that oversees the multiverse", "answer": "x", "difficulty": "easy"})
    assert "error" in again and g.question_number == 1 and not g.awaiting_answer
    assert run_tool(g, "generate_question", {"question": "Who is Morty's sister?", "answer": "Summer",
                                             "difficulty": "easy"})["status"] == "ok"


def test_generate_question_stores_the_reaction():
    g = new_game()
    run_tool(g, "generate_question", {"reaction": "Welcome!", "question": "q", "answer": "a", "difficulty": "easy"})
    assert g.last_reaction == "Welcome!"
