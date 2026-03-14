import asyncio
import os
import sys

# Add backend to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../backend')))

from app.agent.sandbox import get_default_sandbox

async def test_network():
    sandbox = get_default_sandbox()
    
    # Test 1: Filesystem (dir)
    print("--- Test 1: DIR ---")
    stdout, stderr, code = await sandbox.execute("dir", timeout=10)
    print(f"Code: {code}\nStdout: {stdout}\nStderr: {stderr}")

    # Test 2: Network (curl)
    print("--- Test 2: CURL ---")
    stdout, stderr, code = await sandbox.execute("curl -I https://arxiv.org", timeout=10)
    print(f"Code: {code}\nStdout: {stdout}\nStderr: {stderr}")

    # Test 3: Python urllib
    print("--- Test 3: PYTHON URLLIB ---")
    py_code = "import urllib.request; print(urllib.request.urlopen('https://arxiv.org').getcode())"
    stdout, stderr, code = await sandbox.execute(f"python -c \"{py_code}\"", timeout=10)
    print(f"Code: {code}\nStdout: {stdout}\nStderr: {stderr}")

    sandbox.cleanup()

if __name__ == "__main__":
    asyncio.run(test_network())
