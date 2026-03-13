#!/usr/bin/env python
"""
Bootstrap Server Launcher
Run this script to start the Bit-Politeia Bootstrap Server.
"""
import sys
import os

# Add backend directory to Python path
backend_dir = os.path.dirname(os.path.abspath(__file__))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

import uvicorn

if __name__ == "__main__":
    # Import the FastAPI app
    from app.services.p2p_server import app
    
    print("=" * 60)
    print("Starting Bit-Politeia Bootstrap Server")
    print("=" * 60)
    # Check for SSL keys
    ssl_keyfile = os.path.join(backend_dir, "keys", "server.key")
    ssl_certfile = os.path.join(backend_dir, "keys", "server.crt")
    
    use_ssl = os.path.exists(ssl_keyfile) and os.path.exists(ssl_certfile)
    
    if use_ssl:
        print("[OK] SSL Certificates found. Starting in HTTPS mode.")
        print("  - Local:   https://localhost:8000")
        print("  - Network: https://0.0.0.0:8000")
        uvicorn.run(
            "app.services.p2p_server:app",
            host="0.0.0.0",
            port=8000,
            log_level="info",
            ssl_keyfile=ssl_keyfile,
            ssl_certfile=ssl_certfile
        )
    else:
        print("! No SSL Certificates found in backend/keys/")
        print("  Starting in HTTP mode (INSECURE). Run 'python backend/scripts/generate_cert.py' to enable HTTPS.")
        print("  - Local:   http://localhost:8000")
        print("  - Network: http://0.0.0.0:8000")
        uvicorn.run(
            "app.services.p2p_server:app",
            host="0.0.0.0",
            port=8000,
            log_level="info"
        )
