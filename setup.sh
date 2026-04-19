#!/bin/bash
# ─── Kinoscribe — Prerequisites Check ────────────────────────
# Verifies that the Ollama server is reachable and the model is available.
# ──────────────────────────────────────────────────────────────

set -e

OLLAMA_URL="${OLLAMA_URL:-${OLLAMA_BASE_URL:-http://localhost:11434}}"
MODEL="${OLLAMA_MODEL:-llama3}"

echo "🎬 Kinoscribe — Prerequisites Check"
echo ""

# Check Ollama connectivity
echo "⏳ Checking Ollama at $OLLAMA_URL ..."
if curl -sf --max-time 5 "$OLLAMA_URL/api/tags" > /dev/null 2>&1; then
    echo "✅ Ollama is reachable"
else
    echo "❌ Cannot reach Ollama at $OLLAMA_URL"
    echo ""
    echo "   Make sure your Ollama server is running and set OLLAMA_URL:"
    echo "   OLLAMA_URL=http://<your-server-ip>:11434 docker compose up -d"
    exit 1
fi

# Check model availability
echo "⏳ Checking model '$MODEL' ..."
MODELS=$(curl -sf "$OLLAMA_URL/api/tags" | python3 -c "
import sys, json
data = json.load(sys.stdin)
for m in data.get('models', []):
    print(m.get('name', ''))
" 2>/dev/null || echo "")

if echo "$MODELS" | grep -q "$MODEL"; then
    echo "✅ Model '$MODEL' is available"
else
    echo "⚠️  Model '$MODEL' not found on the Ollama server."
    echo "   Pull it first on the server:  ollama pull $MODEL"
    echo "   Or set OLLAMA_MODEL to an existing model."
fi

echo ""
echo "🚀 Ready! Start with:  docker compose up -d"
echo "   Then open: http://localhost:3000"