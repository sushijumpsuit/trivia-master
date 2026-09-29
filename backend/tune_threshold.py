"""Pick the duplicate cutoffs from data, not a guess.

Embeds pairs of questions that are the SAME fact reworded, and pairs that are DIFFERENT facts
(often with similar wording), then prints their cosine distances. It compares embedding the
question alone vs question + answer, and scores the hybrid rule the game uses (memory.is_duplicate:
distance plus an answer check).

Run from backend/ with the venv active:  python tune_threshold.py
Many pairs come from real game logs. Add your own pairs whenever the game gets one wrong.
"""
import math

from chromadb.utils.embedding_functions import DefaultEmbeddingFunction

import memory

# (question A, answer A, question B, answer B)
SAME = [  # same fact, reworded: should be caught as a repeat
    ("What is the name of Cam and Mitchell's adopted daughter?", "Lily",
     "Cam and Mitchell's adopted daughter, who joins the family as a baby from Vietnam, is named what?", "Lily"),
    ("In which country was Gloria Delgado-Pritchett born?", "Colombia",
     "Gloria Delgado-Pritchett hails from which South American country?", "Colombia"),
    ("In which California city is Modern Family set?", "Los Angeles",
     "In what city do the Pritchett, Dunphy, and Tucker-Pritchett families live?", "Los Angeles"),
    ("Who is the patriarch of the Pritchett family, the father of Claire and Mitchell?", "Jay Pritchett",
     "What is the name of the family's grumpy but lovable patriarch, played by Ed O'Neill?", "Jay Pritchett"),
    ("What is the name of the governing body composed of multiple Ricks that oversees the multiverse?", "Council of Ricks",
     "Which council of Ricks rules over the multiverse?", "Council of Ricks"),
    ("What is the name of Cameron Tucker's clown persona?", "Fizbo",
     "What is Cam's clown alter ego called?", "Fizbo"),
    ("Which actor plays Phil Dunphy?", "Ty Burrell",
     "Who portrays Phil Dunphy in Modern Family?", "Ty Burrell"),
    ("What is the name of Gloria's son from her first marriage?", "Manny",
     "Who is Gloria's son with her ex-husband Javier?", "Manny"),
    ("What is the capital of Malaysia?", "Kuala Lumpur",
     "Which city is Malaysia's capital?", "Kuala Lumpur"),
    ("What kind of products does Jay Pritchett's company sell?", "Closets and blinds",
     "What does Jay's business, Pritchett's, make and sell?", "Closets and blinds"),
]
DIFFERENT = [  # different facts: should NOT be rejected
    ("What is the name of Gloria's son from her first marriage?", "Manny",
     "What is the name of Manny's biological father, Gloria's first husband?", "Javier"),
    ("What is the name of Cam and Mitchell's adopted daughter?", "Lily",
     "What is the name of the French bulldog that Jay and Gloria own?", "Stella"),
    ("Which actor plays Phil Dunphy?", "Ty Burrell",
     "Which actress plays Haley Dunphy?", "Sarah Hyland"),
    ("What is the capital of Malaysia?", "Kuala Lumpur",
     "What is the capital of Thailand?", "Bangkok"),
    ("What is the first name of Phil Dunphy's father?", "Frank",
     "What is the first name of Mitchell and Claire's mother?", "DeDe"),
    ("Who does Haley Dunphy eventually marry?", "Dylan",
     "What is the name of Mitchell and Cam's flamboyant friend Pepper's last name?", "Saltzman"),
    ("What is the name of Cameron Tucker's clown persona?", "Fizbo",
     "What is the name of the Dunphy family's youngest child?", "Luke"),
    ("What kind of products does Jay Pritchett's company sell?", "Closets and blinds",
     "What is Phil Dunphy's job?", "Real estate agent"),
    ("What is the name of the governing body composed of multiple Ricks that oversees the multiverse?", "Council of Ricks",
     "What is the name of the device that lets you summon a Meeseeks?", "Meeseeks Box"),
    ("What is the name of the interdimensional cable network Morty and Summer watch?", "Interdimensional Cable",
     "What is the name of the alien species that serves as soldiers of the Galactic Federation?", "Gromflomites"),
]


def cosine_distance(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na, nb = math.sqrt(sum(x * x for x in a)), math.sqrt(sum(y * y for y in b))
    return 1 - dot / (na * nb)


def distances(embed, pairs, with_answer: bool) -> list[float]:
    texts = []
    for qa, aa, qb, ab in pairs:
        texts += [f"{qa} Answer: {aa}" if with_answer else qa, f"{qb} Answer: {ab}" if with_answer else qb]
    vecs = embed(texts)
    return [cosine_distance(vecs[i], vecs[i + 1]) for i in range(0, len(vecs), 2)]


def report(embed, with_answer: bool) -> None:
    label = "question + answer" if with_answer else "question only"
    same, diff = distances(embed, SAME, with_answer), distances(embed, DIFFERENT, with_answer)
    print(f"\n=== Mode: {label} ===")
    print("SAME fact (want small):")
    for d, (qa, _, qb, _) in sorted(zip(same, SAME)):
        print(f"  {d:.3f}  {qa[:45]!r} vs {qb[:45]!r}")
    print("DIFFERENT fact (want large):")
    for d, (qa, _, qb, _) in sorted(zip(diff, DIFFERENT)):
        print(f"  {d:.3f}  {qa[:45]!r} vs {qb[:45]!r}")
    hi_same, lo_diff = max(same), min(diff)
    if hi_same < lo_diff:
        print(f"Separable: largest SAME {hi_same:.3f} < smallest DIFFERENT {lo_diff:.3f}")
        print(f"Suggested DUPLICATE_DISTANCE = {(hi_same + lo_diff) / 2:.2f} (midpoint)")
    else:
        print(f"Overlap: largest SAME {hi_same:.3f} >= smallest DIFFERENT {lo_diff:.3f}")
        for t in (0.15, 0.2, 0.25, 0.3, 0.35):
            caught = sum(d < t for d in same)
            wrongly = sum(d < t for d in diff)
            print(f"  cutoff {t:.2f}: catches {caught}/{len(same)} repeats, wrongly rejects {wrongly}/{len(diff)}")


def hybrid_report(embed) -> None:
    """Score the game's actual rule (memory.is_duplicate) with its current cutoffs."""
    same, diff = distances(embed, SAME, True), distances(embed, DIFFERENT, True)

    def verdict(d: float, stored_answer: str, new_answer: str) -> bool:
        return memory.is_duplicate(memory.Match("", stored_answer, "", d), new_answer)

    caught = [verdict(d, aa, ab) for d, (_, aa, _, ab) in zip(same, SAME)]
    wrong = [verdict(d, aa, ab) for d, (_, aa, _, ab) in zip(diff, DIFFERENT)]
    print(f"\n=== Hybrid rule (question + answer; same answer < {memory.same_answer_cutoff()}, "
          f"different answer < {memory.any_answer_cutoff()}) ===")
    print(f"Catches {sum(caught)}/{len(SAME)} repeats, wrongly rejects {sum(wrong)}/{len(DIFFERENT)}")
    for ok, d, (qa, _, qb, _) in zip(caught, same, SAME):
        if not ok:
            print(f"  missed  {d:.3f}  {qa[:45]!r} vs {qb[:45]!r}")
    for bad, d, (qa, _, qb, _) in zip(wrong, diff, DIFFERENT):
        if bad:
            print(f"  wrongly {d:.3f}  {qa[:45]!r} vs {qb[:45]!r}")


if __name__ == "__main__":
    embed = DefaultEmbeddingFunction()
    report(embed, with_answer=False)
    report(embed, with_answer=True)
    hybrid_report(embed)
    print("\nGoal: catch every repeat while wrongly rejecting ~none.")
    print("A missed repeat breaks the game's promise; a wrong rejection only costs the model one retry.")
