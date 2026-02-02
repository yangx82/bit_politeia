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
    print("Server will be available at:")
    print("  - Local:   http://localhost:8000")
    print("  - Network: http://0.0.0.0:8000")
    print("=" * 60)
    
    # Run the server
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info"
    )
