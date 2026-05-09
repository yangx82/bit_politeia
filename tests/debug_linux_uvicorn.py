import asyncio
import threading

import httpx
import uvicorn
from fastapi import FastAPI

app = FastAPI()


@app.on_event("startup")
async def startup_event():
    print("Minimal App Startup Event Fired!")


@app.get("/")
def read_root():
    return {"status": "ok"}


def run_server():
    uvicorn.run(app, host="127.0.0.1", port=8089, log_level="debug")


async def test_connection():
    print("Waiting 3 seconds for server to start...")
    await asyncio.sleep(3)
    try:
        print("Attempting to connect to http://127.0.0.1:8089/")
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get("http://127.0.0.1:8089/")
            print(f"Connection Successful! Response: {resp.text}")
    except Exception as e:
        print(f"Connection Failed: {e}")


if __name__ == "__main__":
    import threading

    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()
    asyncio.run(test_connection())
