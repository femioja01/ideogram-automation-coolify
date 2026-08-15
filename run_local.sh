#!/bin/bash
# --------------------------------------------------
# Ideogram Automation — macOS Local Launcher
# --------------------------------------------------

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$DIR"

echo "=================================================="
echo "  ⚡ Starting Ideogram Control Center (Local)"
echo "=================================================="

# Find Python binary
if [ -f "venv/bin/python" ]; then
    PYTHON_BIN="venv/bin/python"
    PIP_BIN="venv/bin/pip"
elif command -v python3 &>/dev/null; then
    PYTHON_BIN="python3"
    PIP_BIN="pip3"
else
    PYTHON_BIN="python"
    PIP_BIN="pip"
fi

echo "Using Python: $PYTHON_BIN"

echo "Installing / verifying dependencies..."
$PIP_BIN install -q -r requirements.txt

echo "Opening Web Control Center at http://localhost:8000..."
sleep 2 && open http://localhost:8000 2>/dev/null &

$PYTHON_BIN app.py
