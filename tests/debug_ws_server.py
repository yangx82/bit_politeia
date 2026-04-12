import uvicorn
from fastapi import FastAPI, WebSocket

# Minimal WebSocket Server to test connectivity on Port 8001
# Usage: python tests/debug_ws_server.py

app = FastAPI()


@app.websocket("/ws/gateway")
async def websocket_endpoint(websocket: WebSocket):
    print("[DEBUG] New connection attempt...")
    await websocket.accept()
    print("[DEBUG] Connection accepted!")
    await websocket.send_text("Hello from Minimal Server")
    while True:
        data = await websocket.receive_text()
        print(f"[DEBUG] Received: {data}")
        await websocket.send_text(f"Echo: {data}")


@app.get("/")
def read_root():
    return {"status": "Minimal Server Running"}


if __name__ == "__main__":
    print("Starting Minimal WS Server on 0.0.0.0:8001...")
    uvicorn.run(app, host="0.0.0.0", port=8001)
