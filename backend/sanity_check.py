"""Phase 0 sanity check: confirms the configured LLM provider responds and ChromaDB works.

Pick the provider with LLM_PROVIDER in backend/.env (anthropic, openai, groq, gemini).
Run from backend/ with the venv active:  python sanity_check.py

Temporary: ask_llm() here is a stopgap until Phase 1 builds the proper llm/ package.
"""
import os
import sys

from dotenv import load_dotenv

load_dotenv()

# provider -> (API key env var, model env var, default model, OpenAI-compatible base URL or None)
PROVIDERS: dict[str, tuple[str, str, str, str | None]] = {
    "anthropic": ("ANTHROPIC_API_KEY", "ANTHROPIC_MODEL", "claude-haiku-4-5-20251001", None),
    "openai": ("OPENAI_API_KEY", "OPENAI_MODEL", "", None),  # model must be set in .env
    "groq": ("GROQ_API_KEY", "GROQ_MODEL", "openai/gpt-oss-120b", "https://api.groq.com/openai/v1"),
    "gemini": ("GEMINI_API_KEY", "GEMINI_MODEL", "gemini-3.8-flash",
               "https://generativelanguage.googleapis.com/v1beta/openai/"),
}

GREETING_PROMPT = "You are a trivia host. Greet the player in one short sentence."


class LLMConfigError(Exception):
    """Raised when the provider, key, or model is missing or invalid."""


def provider_config() -> tuple[str, str, str, str | None]:
    """Return (provider, key, model, base_url) from the environment, or raise LLMConfigError."""
    provider = os.getenv("LLM_PROVIDER", "anthropic").strip().lower()
    if provider not in PROVIDERS:
        raise LLMConfigError(f"LLM_PROVIDER='{provider}' is not one of {', '.join(PROVIDERS)}")
    key_var, model_var, default_model, base_url = PROVIDERS[provider]
    key = os.getenv(key_var, "").strip()
    if len(key) < 20:
        raise LLMConfigError(f"{key_var} is missing or looks like a placeholder ({len(key)} chars)")
    model = os.getenv(model_var, default_model).strip()
    if not model:
        raise LLMConfigError(f"Set {model_var} in backend/.env")
    return provider, key, model, base_url


def ask_llm(prompt: str, max_tokens: int = 500) -> tuple[str, str]:
    """Send one prompt to the configured provider. Returns (model, reply_text)."""
    provider, key, model, base_url = provider_config()
    if provider == "anthropic":
        import anthropic

        msg = anthropic.Anthropic(api_key=key).messages.create(
            model=model, max_tokens=max_tokens, messages=[{"role": "user", "content": prompt}]
        )
        return msg.model, "".join(b.text for b in msg.content if b.type == "text").strip()

    # OpenAI, Groq, and Gemini all speak OpenAI's chat-completions format.
    try:
        from openai import OpenAI
    except ImportError:
        raise LLMConfigError("The openai package isn't installed. Run: pip install openai")
    resp = OpenAI(api_key=key, base_url=base_url).chat.completions.create(
        model=model, max_tokens=max_tokens, messages=[{"role": "user", "content": prompt}]
    )
    return resp.model, (resp.choices[0].message.content or "").strip()


def check_llm() -> None:
    try:
        provider, _, model, _ = provider_config()
        print(f"[ .. ] Provider: {provider}, model: {model}")
        used_model, text = ask_llm(GREETING_PROMPT)
    except LLMConfigError as e:
        sys.exit(f"[FAIL] {e}")
    except Exception as e:  # SDK errors differ per vendor; show the type and message
        sys.exit(f"[FAIL] {type(e).__name__}: {e}")
    print(f"[ OK ] {used_model} replied: {text}")


def check_chroma() -> None:
    import chromadb

    client = chromadb.EphemeralClient()  # in-memory, nothing written to disk
    col = client.create_collection("sanity")
    col.add(ids=["q1"], documents=["What is the capital of Malaysia?"])
    hit = col.query(query_texts=["Which city is Malaysia's capital?"], n_results=1)
    dist = hit["distances"][0][0]
    print(f"[ OK ] ChromaDB works (paraphrase distance {dist:.3f}; lower = more similar)")


if __name__ == "__main__":
    check_llm()
    check_chroma()
    print("\nPhase 0 backend check passed.")
