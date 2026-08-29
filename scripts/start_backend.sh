#!/bin/bash
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$DIR"

echo "[*] Killing old backend processes..."
pkill -9 -f "uvicorn" 2>/dev/null || true
pkill -9 -f "backend/main.py" 2>/dev/null || true
pkill -9 -f "code_supervisor.py" 2>/dev/null || true
pkill -9 -f "multiprocessing" 2>/dev/null || true
fuser -k 8100/tcp 2>/dev/null || true
sleep 1

# Auto-clamp WSL2 MTU to 1400 to prevent TLS handshake drops on VPN/Clash TUN
if [ "$(uname)" = "Linux" ]; then
    sudo ip link set dev eth0 mtu 1400 2>/dev/null || true
fi

mkdir -p backend/data/logs
export PYTHONPATH="$DIR/backend:$PYTHONPATH"

echo "[*] Starting backend (uvicorn main:app) in background..."
cd "$DIR/backend"
nohup /home/xing/miniconda3/envs/bit_politeia/bin/python -m uvicorn main:app --host 0.0.0.0 --port 8100 > data/logs/backend_stdout.log 2>&1 &
PID=$!
cd "$DIR"
echo "[+] Backend launched with PID: $PID"

for i in {1..35}; do
    if ss -tlpn | grep -q ":8100"; then
        echo "[+] Backend successfully listening on port 8100!"
        curl --noproxy '*' -s http://127.0.0.1:8100/
        echo ""
        exit 0
    fi
    sleep 1
done

echo "[-] Backend did not bind port 8100 within 35s. Checking logs:"
tail -n 30 backend/data/logs/backend_stdout.log
tail -n 30 backend/data/logs/p2p_network.log
exit 1
