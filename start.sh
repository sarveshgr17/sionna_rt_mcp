#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"

# Activate Python 3.11 virtual environment with Sionna RT & MCP SDK
if [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
fi

# Run the unified stack launcher
python3 start_sionna_lab.py

