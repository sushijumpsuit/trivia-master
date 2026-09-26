"""Trivia Master backend (FastAPI). Phase 0 skeleton.

Run from backend/ with the venv active:  uvicorn main:app --reload
Then open http://127.0.0.1:8000/docs
"""
import os

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from sanity_check import GREETING_PROMPT, LLMConfigError, ask_llm  # replaced by llm/ in Phase 1

load_dotenv()

app = FastAPI(title="Trivia Master API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("FRONTEND_ORIGINS", "http://localhost:3000").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/hello")
def hello() -> dict:
    """Round-trip to the configured LLM so the frontend can confirm the whole chain works."""
    try:
        model, greeting = ask_llm(GREETING_PROMPT)
    except LLMConfigError as e:
        raise HTTPException(status_code=500, detail=f"LLM not configured: {e}")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"LLM error: {type(e).__name__}")
    return {"provider": os.getenv("LLM_PROVIDER", "anthropic"), "model": model, "greeting": greeting}
