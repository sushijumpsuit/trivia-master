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

5. Host's feedback lost, and an extra model call every turn
 - e.g. (DeepSeek log): the model wrote `No worries, the answer is Phil Dunphy, Realtor...` together with its tool calls, but the player saw a later, vaguer reply: `Next question's up, this one should feel a bit more familiar.`
 - what went wrong: after a wrong answer the player never saw the correct answer. On Groq (`gpt-oss`) the same extra step was where replies turned into garbage.
 - why: the agent loop kept calling the model after the next question was registered, only to get a final text reply. The last text won, so good feedback written earlier in the turn was thrown away. That extra call also cost tokens and added to Groq's rate limits.
 - how to fix: added a `reaction` field to `generate_question`. The model writes its feedback there, and the turn ends as soon as the next question is registered. No extra call. With DeepSeek, which calls several tools in one reply, most turns now take one model call. For Anthropic, the next player message is merged into the tool-result message so roles still alternate. Added a regression test that replays the DeepSeek turn.

6. Rambling answers, and a tool the model never used
 - e.g. (DeepSeek log): the stored answer for Q1 was a whole sentence: `Phil Dunphy is a realtor; his catchphrase is "Phil's-osophy" but the persona is simply "Phil Dunphy, Realtor."`. Also, DeepSeek always sent `check_answer`, `update_score` and `generate_question` in the same reply.
 - what went wrong: a question with no clear answer can't be marked fairly. And `check_answer` did nothing: the model decided right or wrong before it saw what `check_answer` returned.
 - why: nothing limited the answer's length. `check_answer` only returned an answer the model had written itself, which was already in the conversation.
 - how to fix: `generate_question` now rejects answers longer than 8 words (or 80 characters) and asks for a question with one clear answer. Removed `check_answer`. When a question is open, the server puts it and its correct answer in the system prompt on every call (context engineering instead of a tool), so the model always judges against the stored answer. Also added prompt rules for consistent marking ("Didi" for "DeDe") and for asking only well-known facts. Tests cover the long answer, the removed tool, and the answer in the prompt.

7. Wrong facts in the questions (fixed with thinking mode)
 - e.g. (DeepSeek Flash, thinking off, Modern Family game):
   - Q7 asked for the Dunphys' "overachieving eldest daughter" with the answer "Haley". Haley is the eldest, but Alex is the overachiever, so the question contradicts itself. The model even said so in its reaction ("Alex is the overachieving middle one") but still marked me wrong.
   - Q4 called Andy Bailey the Dunphys' "next-door neighbor friend". He is Jay and Gloria's manny.
   - Q9: "Which character is Cam and Mitchell's husband, played by Eric Stonestreet?" with the answer "Cam Tucker". The question makes no sense.
   - Q5 (Pepper as "Lily's godfather") and Q6 ("The Incredible Phil" as Phil's magician name) look made up.
 - what went wrong: some questions have wrong facts or contradict themselves, so a correct answer can be marked wrong.
 - why: this is the model's knowledge, not a code bug. `deepseek-flash` with thinking off writes questions fast without checking its facts. The code can keep the game consistent (scoring, no repeats, short answers), but it can't make the model know the show.
 - how to fix: compared options using the game logs, cheapest first:
   1. Turn on DeepSeek thinking mode (`DEEPSEEK_THINKING=enabled`) so the model reasons before it writes each question. Tried first, and it was enough.
   2. Use the stronger `deepseek-v4-pro` (about 4x the price, still cheap).
   3. Add an `explanation` field to `generate_question`, filled in before the answer, so the model has to justify the answer and catches its own contradictions.
   4. Use Claude for the live demo (stronger general knowledge).
   Result (same topic, one game each): thinking off had about 5 wrong or made-up questions out of 9; thinking on had 0 out of 11 that I could find. Model time per turn went from about 1s to 2-3s, still 1 model call per turn. The questions also became more mainstream, which is probably part of why they were accurate. Made thinking the default for DeepSeek. Options 2-4 stay as backups. Next time, log token usage so cost can be compared with numbers too.

8. Duplicate check: embedding distance alone can't separate repeats from new questions
 - e.g. (tune_threshold.py on 20 real pairs from game logs, all-MiniLM-L6-v2, cosine distance):
   - Question only: best cutoff (about 0.20) catches 7/10 repeats and wrongly rejects 1/10.
   - Question + answer: best cutoff (about 0.30) catches 8/10 repeats and wrongly rejects 1/10. Better, but still overlaps.
   - False alarm: "Gloria's son from her first marriage?" (Manny) vs "Manny's biological father, Gloria's first husband?" (Javier) at 0.107. Different facts, but almost the same words, and "Manny" is in both texts.
   - Missed repeats: "patriarch, father of Claire and Mitchell" vs "grumpy patriarch played by Ed O'Neill" (0.441), and "city where Modern Family is set" vs "city where the families live" (0.433). Different clues, same answer.
 - what went wrong: no single cutoff catches every reworded repeat without also rejecting some new questions.
 - why: embeddings measure how similar the wording and topic are, not whether two questions ask for the same fact. Questions that share a template look close even when the answers differ, and loose rewordings look far apart even when the answer is the same.
 - the pattern: in this data, every real repeat had the same answer, and every false alarm had a different answer.
 - how to fix: a hybrid rule that combines distance with an answer check, looking at the 5 nearest past questions:
   - same answer (compared loosely: lowercase, no punctuation, "Jay" counts as "Jay Pritchett") and distance under 0.5 = repeat
   - different answer = repeat only if the question is nearly identical (distance under 0.05)
   Confirmed by re-running tune_threshold.py with the real model: the hybrid rule catches 10/10 repeats with 0/10 false alarms (best plain cutoff: 8/10 and 1/10). 20 pairs is a small set, so confirm it in the 2-game acceptance test (every check's distance is logged) and add new pairs to tune_threshold.py whenever it gets one wrong.
