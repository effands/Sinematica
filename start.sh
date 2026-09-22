#!/bin/bash
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

echo "==================================================="
echo "  SINEMATICA AI STUDIO - GOOGLE FLOW AUTO GENERATOR"
echo "==================================================="
echo ""

if [ ! -f ".env" ]; then
    echo "[Info] Membuat file .env..."
    cp .env.example .env
fi

PORT=8888
if [ -n "$1" ]; then
    PORT="$1"
fi

echo "[1/2] Memeriksa Environment..."
if [ -d ".venv" ]; then
    source .venv/bin/activate
elif [ -d "venv" ]; then
    source venv/bin/activate
fi

echo ""
echo "==================================================="
echo "  Menjalankan Server Sinematica AI di Port $PORT"
echo "  Membuka dashboard: http://127.0.0.1:$PORT"
echo "==================================================="
echo ""

python -m uvicorn backend.main:app --host 127.0.0.1 --port "$PORT"
