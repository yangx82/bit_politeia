
import asyncio
import httpx
import sys
import os

# Add backend to path
sys.path.append(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend"))

async def test_https_connection():
    url = "https://localhost:8000"
    print(f"Testing HTTPS connection to {url}...")
    
    # 1. Test with verify=False (Self-signed cert expected)
    try:
        async with httpx.AsyncClient(verify=False) as client:
            resp = await client.get(f"{url}/")
            print(f"[OK] Connection successful (verify=False): {resp.status_code}")
            print(f"  Response: {resp.json()}")
    except Exception as e:
        print(f"[FAIL] Connection failed (verify=False): {e}")
        return False

    # 2. Test with verify=True (Should fail with self-signed unless CA is trusted)
    print("\nTesting validation (expecting failure for self-signed without CA)...")
    try:
        async with httpx.AsyncClient(verify=True) as client:
            await client.get(f"{url}/")
            print(f"? Unexpected success (Did you trust the CA?): {resp.status_code}")
    except httpx.ConnectError:
        print("[FAIL] Connection refused (Is server running?)")
        return False
    except httpx.ConnectTimeout:
        print("[FAIL] Connection timed out")
        return False
    except Exception as e:
        print(f"[OK] Validation correctly failed for untrusted self-signed cert: {e}")
        
    return True

if __name__ == "__main__":
    try:
        success = asyncio.run(test_https_connection())
        if not success:
            sys.exit(1)
    except KeyboardInterrupt:
        pass
