#!/bin/bash
# --------------------------------------------------
# Ideogram Automation — macOS Local Launcher
# --------------------------------------------------

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$DIR"

echo "=================================================="
echo "  ⚡ Starting Ideogram Control Center (Local)"
echo "=================================================="

if [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
fi

echo "Installing / verifying dependencies..."
pip install -q -r requirements.txt

echo "Opening Web Control Center at http://localhost:8000..."
sleep 2 && open http://localhost:8000 2>/dev/null &

python app.py
