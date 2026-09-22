#!/bin/bash

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

echo "====================================================================="
echo "  SINEMATICA AI STUDIO - AUTOMATED E2E SCENE GENERATION TEST RUNNER"
echo "====================================================================="
echo ""

if [ -d ".venv" ]; then
    source .venv/bin/activate
elif [ -d "venv" ]; then
    source venv/bin/activate
fi

python scripts/test_e2e_generation.py "$@"
EXIT_CODE=$?

echo ""
echo "====================================================================="
if [ $EXIT_CODE -eq 0 ]; then
    echo "[SELESAI] Pengujian E2E Scene Generation Berhasil! (Exit Code: 0)"
else
    echo "[GAGAL] Pengujian E2E Scene Generation Mengalami Kendala (Exit Code: $EXIT_CODE)"
fi
echo "====================================================================="
exit $EXIT_CODE
