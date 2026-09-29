"""Trivia Master backend (FastAPI). Routes only: game logic lives in agent.py / tools.py.

Run from backend/ with the venv active:  uvicorn main:app --reload
Then open http://127.0.0.1:8000/docs
"""
import logging
import os

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

load_dotenv()  # before importing modules that read env vars

import agent  # noqa: E402
from game_state import GameStore  # noqa: E402
from llm import LLMConfigError, LLMError, get_llm, provider_settings  # noqa: E402

# Log to the terminal and to backend/logs/trivia.log (git-ignored) so game runs can be reviewed later.
os.makedirs("logs", exist_ok=True)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s",
                    datefmt="%Y-%m-%d %H:%M:%S",
                    handlers=[logging.StreamHandler(),
                              logging.FileHandler("logs/trivia.log", encoding="utf-8")])
log = logging.getLogger("trivia")
app = FastAPI(title="Trivia Master API")
store = GameStore()

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in os.getenv("FRONTEND_ORIGINS", "http://localhost:3000").split(",")],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


class StartRequest(BaseModel):
    topic: str = Field(min_length=1, max_length=80)


class AnswerRequest(BaseModel):
    answer: str = Field(min_length=1, max_length=200)


def _run(fn, *args) -> str:
    """Call the agent and turn failures into clean HTTP errors (never leak keys or stack traces)."""
    try:
        return fn(get_llm(), *args)
    except LLMConfigError as e:
        raise HTTPException(status_code=500, detail=f"LLM not configured: {e}")
    except LLMError as e:
        log.warning("LLM error: %s", e)
        raise HTTPException(status_code=502, detail="The AI host is unavailable right now. Try again.")
    except agent.AgentError as e:
        log.warning("Agent error: %s", e)
        raise HTTPException(status_code=502, detail="The AI host got confused. Try again.")


@app.get("/health")
def health() -> dict:
    try:
        provider, _, model, _ = provider_settings()
    except LLMConfigError:
        provider, model = "not configured", ""
    return {"status": "ok", "provider": provider, "model": model}


@app.post("/game/start")
def start_game(req: StartRequest) -> dict:
    game = store.create(req.topic.strip())
    message = _run(agent.start_game, game)
    return {"message": message, **game.public_view()}


@app.post("/game/{game_id}/answer")
def submit_answer(game_id: str, req: AnswerRequest) -> dict:
    game = store.get(game_id)
    if game is None:
        raise HTTPException(status_code=404, detail="Game not found (the server may have restarted).")
    if not game.awaiting_answer:
        raise HTTPException(status_code=409, detail="No open question for this game.")
    message = _run(agent.answer, game, req.answer)
    return {"message": message, **game.public_view()}
