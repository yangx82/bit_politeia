#!/usr/bin/env python
"""
Bootstrap Server Launcher
Run this script to start the Bit-Politeia Bootstrap Server.
"""
import sys
import os

# Add current directory to Python path to support 'app.services...' imports
backend_dir = os.path.dirname(os.path.abspath(__file__))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

import uvicorn
from app.utils.env_utils import load_dotenv_safe

def main():
    # Load Environment Variables early to get the port
    load_dotenv_safe()
    
    # Configure Host and Port from Env
    host = os.getenv("BOOTSTRAP_HOST", "0.0.0.0")
    port = int(os.getenv("BOOTSTRAP_PORT", "8000"))
    
    print("=" * 60)
    print(f"Starting Bit-Politeia Bootstrap Server on {host}:{port}")
    print("=" * 60)
    
    # Check for SSL keys
    ssl_keyfile = os.path.join(backend_dir, "keys", "server.key")
    ssl_certfile = os.path.join(backend_dir, "keys", "server.crt")
    
    use_ssl = os.path.exists(ssl_keyfile) and os.path.exists(ssl_certfile)
    protocol = "https" if use_ssl else "http"
    
    if use_ssl:
        print(f"[OK] SSL Certificates found. Starting in {protocol.upper()} mode.")
    else:
        print("! No SSL Certificates found in backend/keys/")
        print(f"  Starting in {protocol.upper()} mode (INSECURE).")
        
    print(f"  - Local:   {protocol}://localhost:{port}")
    print(f"  - Network: {protocol}://{host}:{port}")

    # Launch uvicorn
    if use_ssl:
        uvicorn.run(
            "app.services.p2p_server:app",
            host=host,
            port=port,
            log_level="info",
            ssl_keyfile=ssl_keyfile,
            ssl_certfile=ssl_certfile
        )
    else:
        uvicorn.run(
            "app.services.p2p_server:app",
            host=host,
            port=port,
            log_level="info"
        )

if __name__ == "__main__":
    main()
