#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "==============================================================================="
echo "  SINEMATICA AI STUDIO - FULL AUTOMATED E2E PIPELINE RUNNER"
echo "  Alur: Katalog Genre/Preset -> AI Storyboard -> Fleet Execution -> Video"
echo "==============================================================================="
echo ""

if [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
fi

python3 run_e2e_pipeline.py --scenes 2 --duration 10 --country Indonesia --lang Indonesia --aspect-ratio portrait "$@"
