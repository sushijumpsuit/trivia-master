## BUGS
1. Question number skip
 - what went wrong: after answering question 1, chatbot skipped to q3 straightaway.
 - why: `update_score` only checked "is there an open question that hasn't been scored?", not "has the player actually answered it?". So in one turn the model could score my answer to Q1, register Q2, then call `update_score` again on Q2 (which I never saw) and move on to Q3. It was also a scoring hole: a point could be given for an unseen question. The Phase 1 tests missed it because the fake LLM always behaved perfectly. (Likely cause from reading the code; the log of that exact turn wasn't captured.)
 - how to fix: enforce "one score per player answer" in the server, not the prompt. Added a `player_answered` flag to the game state: submitting an answer sets it, `check_answer` / `update_score` refuse to run unless it's set, and scoring or registering a new question clears it. Added a regression test that replays the skip sequence and checks Q2 can't be scored or skipped.

2. Chatbot reply gibberish
 - what went wrong: after user answers to a question, chatbot generates gibberish before coming out with a new question
 - e.g.: `Close, but the phrase is **Wubba lubba dub dub**. Next: **What is the **…​​​ … … Oops! … Sorry… …` (full of invisible zero-width spaces)
 - why: the design asked the model to do the same job twice: register the question with `generate_question` AND retype it in its reply. The log showed the question had already been registered; the reasoning model (`gpt-oss-120b` on Groq) then degenerated while retyping it. Nothing guaranteed the retyped question matched the registered one either.
 - how to fix: stopped asking the model to write the question. The system prompt now says the reply is only a short reaction, and the frontend shows the question straight from the server's game state (`current_question`) in its own bubble. Added a safety net, `clean_reply()`: strips invisible characters, and if the text still looks broken (too long, mostly symbols, repeated "…") it swaps in a reaction built from the real result, e.g. "Not quite. The answer was X." Added regression tests using the actual garbage text.

3. duplicated question in one chat bubble:
 - e.g.: `**Question 2:** Who is known as the “Father of Independence” for ...? (just one name)**Question 2:** Who is known as the “Father of Independence” for leading Malaysia to independence? (just one name)`
 - what went wrong: chatbot generates repeating sentences/question in one chat bubble.
 - why: same root cause as bug 2: the model was retyping the question in its reply, and sometimes wrote it twice (with odd invisible spacing characters mixed in).
 - how to fix: fixed by the same change as bug 2: the model no longer writes the question at all; the UI displays the registered question from game state, so it can only appear once. If the model ignores the prompt and writes the question anyway, it would show up next to the question bubble; watch for that, and if it happens, add a check in `clean_reply()` that removes question text from the reply.
 - update (it came back): the model ignored the prompt and still wrote the next question in its reply, twice, so the player saw it three times (twice in the reply, once in the question bubble).
   - e.g.: `Oops! The correct answer was **Citadel of Ricks**. Let's keep going—what's the name of the device that lets you summon a Meeseeks?Your turn! What's the name of the device that lets you summon a Meeseeks?`
   - why: a prompt rule is only a request. `gpt-oss-120b` doesn't follow "never write the question" reliably, so the rule has to live in code.
   - how to fix: `clean_reply()` now drops every sentence that contains a question mark, since the reply should only be a reaction and the real question always comes from game state. It also splits "Meeseeks?Your" where the model left no space, and strips `**` markdown because the page shows plain text. If nothing is left, it uses the result message instead. Trade-off: the host can't ask rhetorical questions like "Ready?". Added tests that replay this exact text.

4. Same question asked twice in a row
 - e.g.: Q3 and Q4 were both `What is the name of the governing body composed of multiple Ricks that oversees the multiverse?`
 - what went wrong: after I answered Q3 wrongly (close answer), the model registered the exact same question again as Q4.
 - why: nothing in Phase 1 stopped repeats. `generate_question` accepted any text, and the model probably re-asked to give me another try.
 - how to fix: the game now keeps a list of every question asked (lowercased, punctuation removed). `generate_question` rejects a repeat with an error telling the model to write a different question, and the model self-corrects on its next step. This only catches exact repeats in one game; reworded repeats across games are Phase 2's job (ChromaDB `check_duplicate`). Added a regression test with the real question.
