# ─── Build stage (install deps) ───────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /app

# Install uv for fast deps
RUN pip install --no-cache-dir uv

COPY requirements.txt .

# Install base deps (fast)
RUN uv pip install --system --no-cache \
    fastapi uvicorn[standard] pydantic>=2 pydantic-settings python-multipart \
    aiohttp xmltodict sqlalchemy[asyncio] aiosqlite structlog pysubs2 \
    asyncssh python-dotenv "cryptography>=42.0" cinemagoer

# Install ML deps (heavy: ~2GB for torch + faster-whisper) — skip if unavailable
RUN uv pip install --system --no-cache faster-whisper || \
    echo "⚠️  faster-whisper install skipped — Whisper features disabled"

# ─── Runtime stage ─────────────────────────────────────────────
FROM python:3.11-slim

WORKDIR /app

# Install ffmpeg (for media track extraction, Whisper audio extraction)
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg && \
    rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy app code
COPY app/ ./app/

# Create data directories
RUN mkdir -p /app/data/uploads /app/data/output /app/data/work /app/data/cache

# Environment defaults
ENV DATABASE_URL=sqlite+aiosqlite:///./data/subtitle_translator.db \
    OLLAMA_BASE_URL=http://ollama:11434 \
    OLLAMA_MODEL=llama3 \
    DEBUG=false

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]