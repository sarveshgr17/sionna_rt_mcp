#!/usr/bin/env bash
set -e

# Navigate to repository root
cd "$(dirname "$0")"

echo "========================================================================"
echo "    SIONNA LAB — Full-Stack Ray Tracing & MCP Simulation Suite        "
echo "========================================================================"

# 1. Activate Python virtual environment if present
if [ -f ".venv/bin/activate" ]; then
    echo "[*] Activating virtual environment (.venv)..."
    source .venv/bin/activate
elif [ -f "venv/bin/activate" ]; then
    echo "[*] Activating virtual environment (venv)..."
    source venv/bin/activate
elif [ -f ".venv_sionna/bin/activate" ]; then
    echo "[*] Activating virtual environment (.venv_sionna)..."
    source .venv_sionna/bin/activate
fi

# 2. Resolve Python binary
PYTHON_BIN=""
if [ -x ".venv/bin/python" ]; then
    PYTHON_BIN=".venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="python3"
elif command -v python >/dev/null 2>&1; then
    PYTHON_BIN="python"
else
    echo "[ERROR] Python 3.10/3.11 was not found on PATH or in .venv."
    exit 1
fi

# 3. Ensure frontend dependencies are installed if missing
if [ -d "frontend" ] && [ ! -d "frontend/node_modules" ]; then
    echo "[*] frontend/node_modules not found. Installing frontend dependencies..."
    cd frontend
    if command -v bun >/dev/null 2>&1; then
        bun install
    elif command -v npm >/dev/null 2>&1; then
        npm install
    else
        echo "[WARNING] Neither bun nor npm was found to install frontend dependencies."
    fi
    cd ..
fi

# 4. Clean up any stale processes on ports 8000, 8080, or 5173
for port in 8000 8080 5173; do
    pids=$(lsof -ti :$port 2>/dev/null || true)
    if [ -n "$pids" ]; then
        echo "[*] Releasing busy port $port (PID: $pids)..."
        kill -15 $pids 2>/dev/null || true
        sleep 0.3
        kill -9 $pids 2>/dev/null || true
    fi
done

# 5. Launch the unified multi-process runner
exec "$PYTHON_BIN" start_sionna_lab.py "$@"
