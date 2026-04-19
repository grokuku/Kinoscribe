# ─── Build stage (install deps) ────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /app

# Install uv for fast deps
RUN pip install --no-cache-dir uv

COPY requirements.txt .
RUN uv pip install --system --no-cache -r requirements.txt

# ─── Runtime stage ─────────────────────────────────────────────
FROM python:3.11-slim

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy app code
COPY app/ ./app/

# Create data directories
RUN mkdir -p /app/data/uploads /app/data/output

# Environment defaults
ENV DATABASE_URL=sqlite+aiosqlite:///./data/subtitle_translator.db \
    OLLAMA_BASE_URL=http://ollama:11434 \
    OLLAMA_MODEL=llama3 \
    DEBUG=false

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]