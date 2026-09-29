# Trivia Master backend: FastAPI + ChromaDB
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# Run as a normal user, not root
RUN useradd --create-home app
WORKDIR /app

# Install dependencies first so code changes don't reinstall them (pytest is dev only)
COPY requirements.txt .
RUN grep -v '^pytest' requirements.txt > requirements.prod.txt \
    && pip install -r requirements.prod.txt

USER app

# Download the embedding model at build time, so the first game doesn't wait for it
RUN python -c "from chromadb.utils.embedding_functions import DefaultEmbeddingFunction as E; E()(['warm up'])"

COPY --chown=app:app . .
RUN mkdir -p chroma_data logs

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4)"

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
