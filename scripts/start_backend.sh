#!/bin/bash
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$DIR"

echo "[*] Killing old backend processes..."
pkill -9 -f "uvicorn" 2>/dev/null || true
pkill -9 -f "backend/main.py" 2>/dev/null || true
pkill -9 -f "code_supervisor.py" 2>/dev/null || true
sleep 1

mkdir -p backend/data/logs
export PYTHONPATH="$DIR/backend:$PYTHONPATH"

echo "[*] Starting backend main.py in background..."
nohup /home/xing/miniconda3/envs/bit_politeia/bin/python backend/main.py > backend/data/logs/backend_stdout.log 2>&1 &
PID=$!
echo "[+] Backend launched with PID: $PID"

for i in {1..35}; do
    if ss -tlpn | grep -q ":8100"; then
        echo "[+] Backend successfully listening on port 8100!"
        curl -s http://127.0.0.1:8100/
        echo ""
        exit 0
    fi
    sleep 1
done

echo "[-] Backend did not bind port 8100 within 35s. Checking logs:"
tail -n 30 backend/data/logs/backend_stdout.log
tail -n 30 backend/data/logs/p2p_network.log
exit 1
