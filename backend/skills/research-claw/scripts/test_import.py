import sys
import os
from pathlib import Path

# Try to import backend
try:
    import backend
    from backend.app.services.task_manager import task_manager
    print("SUCCESS: Backend and TaskManager imported successfully.")
    print(f"Project Root in sys.path: {any('bit_politeia' in p for p in sys.path)}")
except Exception as e:
    print(f"FAILURE: {e}")
    print(f"sys.path: {sys.path}")
    sys.exit(1)
