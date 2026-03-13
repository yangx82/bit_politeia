import asyncio
from fastapi import FastAPI
import uvicorn
import threading
import httpx
import os

app = FastAPI()

@app.on_event("startup")
async def startup_event():
    print("Test App Startup complete.")

@app.get("/")
def read_root():
    return {"status": "ok"}

def run_server(port, ssl=False):
    kwargs = {
        "host": "0.0.0.0",
        "port": port,
        "log_level": "info"
    }
    if ssl:
        backend_dir = os.path.dirname(os.path.abspath(__file__))
        backend_dir = os.path.dirname(backend_dir)
        ssl_keyfile = os.path.join(backend_dir, "keys", "server.key")
        ssl_certfile = os.path.join(backend_dir, "keys", "server.crt")
        if os.path.exists(ssl_keyfile) and os.path.exists(ssl_certfile):
            kwargs["ssl_keyfile"] = ssl_keyfile
            kwargs["ssl_certfile"] = ssl_certfile
            print(f"Starting HTTPS server on port {port}...")
        else:
            print("SSL keys not found, falling back to HTTP...")
            ssl = False
    
    if not ssl:
        print(f"Starting HTTP server on port {port}...")
        
    uvicorn.run(app, **kwargs)

async def test_connection(port, ssl=False):
    print(f"Waiting 3 seconds for server on port {port} to start...")
    await asyncio.sleep(3)
    protocol = "https" if ssl else "http"
    url = f"{protocol}://127.0.0.1:{port}/"
    try:
        print(f"Attempting GET {url}...")
        # Disable cert verification for local test
        async with httpx.AsyncClient(timeout=5.0, verify=False) as client:
            resp = await client.get(url)
            print(f"SUCCESS: Server on port {port} responded: {resp.text}")
    except Exception as e:
        print(f"FAILED: Connection to port {port} failed: {e}")

if __name__ == "__main__":
    print("--- Test 1: HTTP Traffic ---")
    t1 = threading.Thread(target=run_server, args=(8090, False), daemon=True)
    t1.start()
    asyncio.run(test_connection(8090, False))
    
    print("\n--- Test 2: HTTPS Traffic ---")
    t2 = threading.Thread(target=run_server, args=(8091, True), daemon=True)
    t2.start()
    asyncio.run(test_connection(8091, True))
