#!/bin/bash

# Start with Supervisor script for Bit Politeia Agent
# This script launches both the backend and the code supervisor for self-healing.

# 1. Kill any existing background processes in this project
echo "[*] Cleaning up old processes..."
pkill -f "python3 scripts/code_supervisor.py" || true
pkill -f "uvicorn main:app" || true

# 2. Ensure log directory exists
mkdir -p backend/data/logs
mkdir -p backend/data/code_updates

# 3. Start Code Supervisor in the background
echo "[*] Starting Code Supervisor..."
python3 backend/scripts/code_supervisor.py > backend/data/logs/supervisor_stdout.log 2>&1 &
SUPERVISOR_PID=$!

# 4. Start Backend with hot-reload
echo "[*] Starting Backend (uvicorn)..."
cd backend
python3 -m uvicorn main:app --host 0.0.0.0 --port 8001 --reload > data/logs/backend_stdout.log 2>&1 &
BACKEND_PID=$!

echo "[+] System started!"
echo "[+] Supervisor PID: $SUPERVISOR_PID"
echo "[+] Backend PID: $BACKEND_PID"
echo "[+] Logs available in backend/data/logs/"

# Keep script running to monitor or wait
wait
