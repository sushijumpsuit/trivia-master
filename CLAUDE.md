# Trivia Master: rules for AI coding assistants

Read this before making any change. Frontend-specific rules also live in `frontend/CLAUDE.md` (Next.js 16 has breaking changes; check `frontend/node_modules/next/dist/docs/` before writing frontend code).

## What this project is

An AI-hosted trivia game. The player picks any topic; an LLM agent runs the round by calling real tools: `generate_question` (registers the question and the host's reaction, and from Phase 2 runs the ChromaDB duplicate check itself) and `update_score`. There is no difficulty setting (removed as unused; the host can still ease off in its reaction). There is no `check_answer` tool: the server puts the open question's correct answer in the system prompt. ChromaDB stores every question ever asked so the agent never repeats itself, even with reworded questions.

Rules that must always hold live in code (tool checks), not only in the prompt: logs showed models don't follow prompt rules reliably.

This is a **portfolio project for job applications**. The owner must be able to explain every line of the core logic in an interview. Clarity beats cleverness.

## Stack (do not swap without asking)

- **Frontend:** Next.js 16 (App Router), React 19, TypeScript, Tailwind CSS 4. Lives in `frontend/`. Hosted on AWS Amplify.
- **Backend:** Python 3.11, FastAPI, Uvicorn. Lives in `backend/`, venv at `backend/venv/`. Hosted on AWS EC2 via Docker Compose.
- **LLM:** multi-provider, chosen by the `LLM_PROVIDER` env var (`anthropic`, `openai`, `groq`, `gemini`, `deepseek`). Two hand-written adapters behind one interface:
  - `anthropic_llm.py` uses the `anthropic` SDK (Messages API, native tool use).
  - `openai_compat.py` uses the `openai` SDK for OpenAI, Groq, Gemini, and DeepSeek, which all accept OpenAI's chat-completions format at different base URLs.
  - DeepSeek thinking mode is on by default (`DEEPSEEK_THINKING`): a side-by-side test showed far fewer wrong questions. The adapter must send `reasoning_content` back on later tool-calling requests, or DeepSeek returns 400.
  - Model per provider comes from env vars (`ANTHROPIC_MODEL`, `OPENAI_MODEL`, `GROQ_MODEL`, `GEMINI_MODEL`, `DEEPSEEK_MODEL`); see `backend/.env.example`.
  - Do **not** use LiteLLM or similar wrapper libraries. Writing the adapters by hand is the point: it shows how each vendor's tool calling works.
- **Vector store:** ChromaDB with a persistent client writing to `backend/chroma_data/` (git-ignored; a Docker volume in production).
- Do not add new dependencies without saying why. When one is added, pin it in `backend/requirements.txt` or `frontend/package.json`.

## Project layout

```
backend/
  main.py            FastAPI app and routes only (thin)
  agent.py           the agent loop (messages -> tool calls -> results -> repeat)
  llm/
    base.py          shared interface + neutral types (Message, ToolCall, LLMReply)
    anthropic_llm.py adapter: neutral types <-> Anthropic format
    openai_compat.py adapter: neutral types <-> OpenAI format (OpenAI/Groq/Gemini)
    __init__.py      get_llm() factory that reads LLM_PROVIDER
  tools.py           tool JSON schemas + the Python functions that run them
  memory.py          all ChromaDB code (store, similarity search)
  game_state.py      score / streak per game
  sanity_check.py    Phase 0 check that the configured LLM and Chroma work
  tests/             pytest tests
frontend/app/        Next.js pages and components
```

Keep these responsibilities separate. Routes should not contain agent logic; the agent should not contain Chroma code.

**Provider-neutral rule:** `agent.py`, `tools.py`, `memory.py`, and `game_state.py` must never import `anthropic` or `openai` or use vendor-specific message shapes. Only files in `llm/` know about vendors. Tool schemas are defined once in a neutral form (name, description, JSON Schema params) and each adapter converts them.

## Security (non-negotiable)

- **Never hardcode, print, log, or return any API key** (Anthropic, OpenAI, Groq, Gemini) or any secret. Secrets come only from environment variables (`backend/.env` locally, server env vars in production).
- `.env` must stay git-ignored. `backend/.env.example` holds placeholders only.
- The frontend must **never** call Anthropic directly or see the key. All LLM calls go through the backend.
- Only variables prefixed `NEXT_PUBLIC_` reach the browser. Never put a secret in one.
- CORS: allow only origins listed in `FRONTEND_ORIGINS`. No `"*"` in production.
- Validate all request bodies with Pydantic models. Cap answer/topic length.
- Set a `max_tokens` on every Claude call and cap the agent loop (e.g. 10 iterations) so a bug cannot run up the bill.

## Code style

- Python: type hints on all functions, short docstrings on public ones, f-strings, no bare `except`. Each adapter catches its SDK's errors and raises one shared `LLMError`, which routes turn into a clean HTTP error.
- TypeScript: strict types, no `any`. Keep the API base URL in `NEXT_PUBLIC_API_URL`.
- Small functions with clear names. Comment the *why*, not the *what*.
- No dead code, no commented-out blocks, no placeholder TODOs left behind silently.

## How to work with the owner

- **Explain changes to core logic.** For anything touching `agent.py`, `tools.py`, or `memory.py`: before or after the code, explain in plain words what it does and why, so it can be defended in an interview.
- **Small steps.** One feature or fix per change. Stop at a working, testable point and say how to test it.
- **Say which mode you're in:** feature work (build the next small piece) or debugging (find the root cause first, change as little as possible, explain the cause).
- When debugging, ask for the exact error text, what was expected, and the steps to reproduce, if not given.
- Build the MVP first. Do not add features beyond the current phase unless asked.
- Suggest a short commit message after each working step, e.g. `Add check_duplicate tool with similarity threshold`.

## Build phases (current phase in bold)

0. Setup: venv, packages, sanity check, first commit (done 26 Sep 2026, on Groq)
1. Core game loop without memory: `llm/base.py` interface + first adapter (Groq or Gemini, free), neutral tool schemas, agent loop, `/game/start` and `/game/{id}/answer`, minimal UI; then add the Anthropic adapter (done 29 Sep 2026)
2. ChromaDB memory: duplicate check inside `generate_question` (memory.py) using a hybrid rule (embedding distance + answer match, cutoffs picked with tune_threshold.py, see DEVLOG bug 8); verify 20+ rounds across 2 games with no repeats (done 29 Sep 2026: 29 questions over 2 games, 7 repeats caught, 0 false rejections)
3. **Polish: host personality, summary, frontend feedback; eval script that auto-plays N rounds and reports duplicate rate + loop steps per question, per provider**
4. Docker + docker-compose (Chroma on a named volume)
5. Deploy: backend on EC2 with HTTPS, frontend on Amplify; per-visitor rate limit + daily question cap so the public demo can't drain API credit
6. README, architecture diagram, demo GIF
7. (Stretch) Kubernetes manifests in `k8s/`, run on minikube

Update the bold marker when a phase is finished.

## Testing

- Every tool function in `tools.py` and `memory.py` gets a pytest test.
- Each adapter gets tests for converting tools, messages, and tool-call replies in both directions.
- Tests must never call a real LLM API. Mock the clients.
- Only claim a provider works (README, CV) after it has been run for real at least once.
- Run backend tests with `pytest` from `backend/` (venv active).

## Commands (Windows PowerShell)

```
# backend
cd backend; .\venv\Scripts\Activate.ps1
python sanity_check.py
python tune_threshold.py         # measure duplicate distances, pick DUPLICATE_DISTANCE
uvicorn main:app --reload        # http://127.0.0.1:8000/docs
pytest

# frontend
cd frontend; npm run dev         # http://localhost:3000
```
