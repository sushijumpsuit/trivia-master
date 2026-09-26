"""Sanity check: confirms the configured LLM provider responds and ChromaDB works.

Pick the provider with LLM_PROVIDER in backend/.env (anthropic, openai, groq, gemini).
Run from backend/ with the venv active:  python sanity_check.py
"""
import sys

from dotenv import load_dotenv

load_dotenv()

from llm import LLMConfigError, LLMError, Message, get_llm  # noqa: E402


def check_llm() -> None:
    try:
        llm = get_llm()
        print(f"[ .. ] Provider: {llm.provider}, model: {llm.model}")
        reply = llm.chat("You are a trivia host.",
                         [Message(role="user", content="Greet the player in one short sentence.")],
                         tools=[], max_tokens=500)
    except (LLMConfigError, LLMError) as e:
        sys.exit(f"[FAIL] {e}")
    print(f"[ OK ] Replied: {reply.text}")
    print(f"       tokens in/out: {reply.input_tokens}/{reply.output_tokens}")


def check_chroma() -> None:
    import chromadb

    client = chromadb.EphemeralClient()  # in-memory, nothing written to disk
    col = client.create_collection("sanity")
    col.add(ids=["q1"], documents=["What is the capital of Malaysia?"])
    hit = col.query(query_texts=["Which city is Malaysia's capital?"], n_results=1)
    print(f"[ OK ] ChromaDB works (paraphrase distance {hit['distances'][0][0]:.3f}; lower = more similar)")


if __name__ == "__main__":
    check_llm()
    check_chroma()
    print("\nSanity check passed.")
