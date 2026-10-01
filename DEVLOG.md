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
   - Follow-up (Phase 2 acceptance test, 29 questions, thinking on): 1 wrong question. It said Mitchell "works as a realtor" (Phil is the realtor; Mitchell is a lawyer), and the reaction covered for it ("lawyer and reluctant realtor"). Thinking mode cut errors a lot but did not remove them. Stronger model (options 2 or 4) is the next step if accuracy matters more.

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
 - acceptance test (2 games, same topic, 12 + 17 questions): the second game had 7 repeats rejected, all real repeats, 0 new questions wrongly rejected, and 0 reworded repeats slipped through. The model wrote a new question after every rejection (one extra call, about 2-4 s). One rejection showed why the check looks at the 5 nearest questions: for "Gloria's son from her previous marriage?" (Manny), the closest match was the Javier question (0.132, different answer, not a repeat), and the real repeat was further down the list.
 - known limitation (accepted): "inverse" questions are not caught. Game 1 asked "What breed is Jay's dog, Stella?"; game 2 asked for the dog's name (answer Stella, distance 0.226). Same with "Phil and Claire's three children" vs "How many children do they have?" (answer 3). The rule sees different answers, so it treats them as different facts. Accepted because a new game clears the chat, so the player never sees the earlier question. It could still happen inside one game, where earlier questions stay on screen; if that shows up, add an "answer leak" check (new answer appears in a past question's text, and the distance is fairly close).

9. Frontend API client was never committed
 - e.g.: while committing a frontend change, git said `The following paths are ignored: frontend/lib`. `git ls-files frontend/lib` was empty.
 - what went wrong: `frontend/lib/api.ts` (the typed client the page uses to call the backend) was never in git. The app worked on my machine, but a fresh clone from GitHub would fail to build.
 - why: the root `.gitignore` came from a Python virtualenv template with broad rules like `[Ll]ib`, `[Bb]in` and `[Ss]cripts`. They are meant for a repo that *is* a virtualenv, and they matched any folder called `lib`, including the Next.js one.
 - how to fix: removed those six rules (`venv/` already ignores the virtualenv) and committed `frontend/lib/api.ts`. Checked that only that file became visible.
 - lesson: check what a template `.gitignore` actually ignores (`git check-ignore -v <path>`), and test a fresh clone before calling a phase done. Phase 6 (README) should include a clean-clone build test.

10. Thrown flashcard showed both faces at once
 - e.g.: in a screenshot taken mid-throw, the red result card looked doubled and see-through, with the question side showing through.
 - what went wrong: the throw animation faded the card out (opacity to 0) while it flew off screen.
 - why: in CSS, `opacity` below 1 on an element forces its children to be flattened into 2D. The flip relies on 3D (`transform-style: preserve-3d` and `backface-visibility: hidden`), so once flattened, the hidden front face showed through the back.
 - how to fix: the top card never changes opacity; it flies off screen fully solid (it leaves the screen anyway). Only the cards behind it are faded. Found by taking automated screenshots of each stage (Playwright, against a fake backend), not by reading the code.

11. 502 Bad Gateway when a topic runs out of famous questions
 - e.g. (log, round 2 on Modern Family): the model proposed Gloria, Lily, Phil's job, Stella, Ty Burrell, Manny, ABC and Fizbo. All 8 had been asked in earlier games, so the duplicate check rejected every one. After 8 model calls the loop stopped with `Turn did not finish within 8 model calls`, and the API returned 502.
 - what went wrong: on a topic that had been played a lot, starting a round failed. Round 1 had nearly failed too (5 rejections before one got through).
 - why: the memory knew every past question, but the model only learned about them one rejection at a time. It never saw the full list, so it kept offering the most famous facts first. The step cap (a safety limit against runaway loops) then ended the turn.
 - how to fix: context engineering. At the start of each round, fetch the answers already used for this topic from ChromaDB (up to 60, searched by the topic's meaning, not its exact label) and put them in the system prompt: `Already-used answers on this topic (don't reuse): Stella, Lily, ...`. Answers accepted during the round are added to the list. The prompt tells the model to pick less obvious facts when the famous ones are used up. The rejection message says the same. If the memory is down, the game still starts. Answers are short, so 60 of them cost only a few hundred tokens.
 - lesson: a check that rejects bad output isn't enough on its own; also give the model the information it needs to get it right the first time. Keep the step cap: it turned a runaway loop into a clean error.

12. 409 Conflict after a failed answer
 - e.g. (log): in one reply the model scored my answer and proposed a repeat ("Cam and Mitchell's daughter", Lily), which the memory rejected. Its next reply was completely empty (no text, no tool call). DeepSeek then refused the whole conversation: `Invalid assistant message: content or tool_calls must be set` (400). The retry failed the same way, so the API returned 502. When I submitted again, I got 409 `No open question`.
 - what went wrong: three problems stacked up. (1) The empty reply was saved into the conversation, which made every later request invalid. (2) The token budget (1024) was too small for thinking mode, which is likely why the reply was empty: the reasoning used it all. (3) The failed turn had already scored my answer, so the game was left half-changed: no open question and no next question. The retry then hit 409.
 - how to fix: (1) An empty reply is never stored. It counts as a failed attempt, and the model gets a nudge. The adapters also skip empty assistant messages, so an invalid message can never be sent. (2) Raised the token budget to 4096; you only pay for tokens actually used. (3) Turns are now all-or-nothing: the game state is copied at the start of each turn (start, answer, next round) and restored if the turn fails, so a retry is a clean fresh attempt. Nothing needs undoing in the memory, because a question is only saved when it's registered, and that ends the turn. Tests replay the exact sequence from the log.
 - lesson: when a request can fail halfway, make it atomic (all-or-nothing) so the user can safely retry.


## Bug 13: duplicate check rejected two new facts (false alarms)
 - scenario: in the 100-question eval run, the memory rejected two questions that were not repeats. "Which two countries are separated by the Bering Strait?" (Russia and the United States) was blocked by "Which is the largest country by land area?" (Russia), distance 0.489. "Which country's space agency is ISRO?" (India) was blocked by the Chandrayaan-3 question (India), distance 0.484.
 - what went wrong: the same-answer cutoff was 0.5. Both pairs share an answer and sit just under it, but ask about different facts.
 - how to fix: lowered the cutoff to 0.46. The loosest real repeat seen so far is 0.441, so 0.46 still catches every known repeat and lets both false alarms through. Added both pairs to tune_threshold.py and to the tests.
 - lesson: a threshold is only as good as the data behind it. Keep every false alarm and every miss as a test case.


## Bug 14: trimming the history made the model repeat itself (memory has a cost either way)
 - scenario: to stop input tokens growing in long rounds, I sent the model only the last 2 turns instead of the whole round. I re-ran the eval (5 rounds x 20 questions, same seed). Input tokens per question halved (7,042 to 3,617) and cost per question fell 28% ($0.0026 to $0.00186). But duplicate rejections went from 10 to 44, model calls per question from 1.2 to 1.6, output tokens from 409 to 641, and time per turn from 2.9 s to 3.8 s.
 - what went wrong: the model forgot the questions it had asked earlier in the round, so it kept offering the same famous facts again (Greenland, Valentina Tereshkova, James Webb). The ChromaDB check caught every one, so no repeat reached the player, but each rejection cost a whole extra call. The "already-used answers" list was still in the prompt; the model mostly ignored it. It avoided repeats well when it could see its own earlier questions.
 - how to fix: keep the trimming, but put the questions already asked on the topic into the system prompt (about 20 tokens each, last 30 or so, about 600 tokens). That gives back the memory that mattered without replaying reactions, tool results and reasoning. Next eval run checks it.
 - lesson: the model needs memory, and you pay for it either way: up front in context, or later in retries and latency. The job is to find the smallest form of memory that still works.
 - result: with the past-questions list, rejections fell to 25 and calls to 1.38 per question (3.45 s per turn). Cost stayed at $0.00183 per question, because the list's extra input tokens cancelled most of the saving from fewer retries. Overall still 30% cheaper than full history. The model still proposes a few favourite facts even when they are listed (Greenland 4 times), but the server blocks them.


## Bug 15: Amplify build passed but the deploy failed
 - scenario: first Amplify deploy. The Next.js build finished and generated all static pages, then the deploy step failed with `Can't find required-server-files.json in build output directory`.
 - what went wrong: Amplify saw Next.js and set the app up as a server-rendered app (platform WEB_COMPUTE), which expects server files after the build. This app is built as plain static files (`NEXT_OUTPUT=export`), because Amplify doesn't support Next.js 16 servers yet and the page needs no server.
 - how to fix: switched the app to static hosting with the AWS CLI (`update-app --platform WEB`, `update-branch --framework "Web"`) and redeployed. Added the fix to docs/DEPLOY.md.
 - lesson: hosting platforms guess the app type from the framework. When the build output doesn't match their guess, set the type explicitly.

## Bug 16: Docker build failed on folder permissions, then the live site was blocked by CORS
 - scenario: (1) the backend image failed at `mkdir chroma_data logs: Permission denied`. (2) After deploying, starting a game failed with a CORS error in the browser.
 - what went wrong: (1) `/app` was created by root, and `COPY --chown` only changes the copied files, not the folder, so the non-root user couldn't create folders in it. (2) The backend only accepts browser requests from origins in `FRONTEND_ORIGINS`, which still had the localhost value.
 - how to fix: (1) create the folders as root and hand `/app` to the app user before switching to it. (2) set `FRONTEND_ORIGINS` to the Amplify address and recreate the backend container. Both are in the deploy guide.
 - lesson: running as a non-root user and strict CORS are both worth keeping; they just need to be set up on purpose.
