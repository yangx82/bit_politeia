#!/bin/bash

# Start with Supervisor script for Bit Politeia Agent
# This script launches both the backend and the code supervisor for self-healing.

# 1. Kill any existing background processes in this project
echo "[*] Cleaning up old processes..."
pkill -f "python.*code_supervisor.py" || true
pkill -f "uvicorn.*main:app" || true
pkill -f "python.*backend/main.py" || true

# 2. Ensure log directory exists
mkdir -p backend/data/logs
mkdir -p backend/data/code_updates

# 3. Start Code Supervisor in the background
echo "[*] Starting Code Supervisor..."
python backend/scripts/code_supervisor.py > backend/data/logs/supervisor_stdout.log 2>&1 &
SUPERVISOR_PID=$!

# 4. Start Backend with auto-restart loop
echo "[*] Starting Backend (uvicorn) with auto-restart loop..."
STOP_FILE="backend/data/STOP"
rm -f "$STOP_FILE"

while true; do
    if [ -f "$STOP_FILE" ]; then
        echo "[!] STOP file detected. Exiting backend loop."
        break
    fi
    
    # Launch equivalent to manual execution so that sys.path and cwd behave EXACTLY as they did before
    cd backend && uv run --no-sync uvicorn main:app --host 0.0.0.0 --port 8001
    
    EXIT_CODE=$?
    echo "[!] Backend exited with code $EXIT_CODE. Restarting in 2 seconds..."
    sleep 2
done &
BACKEND_PID=$!

echo "[+] System started!"
echo "[+] Supervisor PID: $SUPERVISOR_PID"
echo "[+] Backend PID: $BACKEND_PID"
echo "[+] Logs available in backend/data/logs/"
echo "[*] Showing backend logs below (Press Ctrl+C to exit log view, services will keep running)..."

# Keep script running by tailing the logs, so the user sees the output
tail -f backend/data/logs/backend_stdout.log
