
import asyncio
import json
import websockets
import sys
import os
import requests

# Ensure we can import from backend if needed, but this script acts as external client
sys.path.append(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend"))

async def test_gateway():
    # Agent Node runs on 8001 (by default in main.py)
    # And currently no SSL in main.py
    uri = "ws://127.0.0.1:8001/ws/gateway" 
    
    # Load .env for token
    from dotenv import load_dotenv
    env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
    load_dotenv(env_path)
    token = os.getenv("AGENT_API_KEY")
    
    if token:
        uri += f"?token={token}"
        print(f"Using Auth Token: {token[:4]}***")
    
    print(f"Connecting to {uri}...")

    # Poll for HTTP readiness first
    # HTTP poll might be flaky if uvicorn is busy?
    import time
    print("Waiting 10s for server startup...")
    time.sleep(10)

    # No retry loop, fail fast
    try:
        async with websockets.connect(uri) as websocket:
            print("[OK] Connected to WebSocket Gateway")
            
            # Send Handshake
            handshake = {
                "type": "handshake",
                "id": "test_1",
                "timestamp": 1234567890,
                "node_id": "tester_node",
                "capabilities": ["echo"]
            }
            await websocket.send(json.dumps(handshake))
            print("[OK] Sent Handshake")
            
            # Send Ping
            ping = {
                "type": "ping",
                "id": "test_2",
                "timestamp": 1234567891
            }
            await websocket.send(json.dumps(ping))
            print("[OK] Sent Ping")
            
            # Wait for Pong
            response = await websocket.recv()
            print(f"[OK] Received: {response}")

            # 3.5 Configure Agent via REST (needed for thinking)
            print("Configuring Agent...")
            config_payload = {
                "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
                "api_key": token if token else "mock_key",
                "model": "qwen-plus",
                "research_field": "AI Governance",
                "bootstrap_url": "http://localhost:8000"
            }
            try:
                # Use requests to POST /api/v1/config
                resp = requests.post("http://127.0.0.1:8001/api/v1/config", json=config_payload)
                print(f"[OK] Configured Agent: {resp.status_code}")
            except Exception as e:
                print(f"[WARN] Config failed: {e}")

            # 4. Trigger Agent Thought Process (Chat)
            chat_event = {
                "type": "event",
                "id": "test_3",
                "timestamp": 1234567892,
                "node_id": "tester_node",
                "payload": "Hello, please think about the meaning of life." 
            }
            await websocket.send(json.dumps(chat_event))
            print("[OK] Sent Chat Event")
            
            # Listen for stream
            print("Listening for 30 seconds...")
            for _ in range(30):
                try:
                    resp = await asyncio.wait_for(websocket.recv(), timeout=2.0)
                    data = json.loads(resp)
                    print(f"[STREAM] Type: {data.get('event_type')} | Content: {str(data.get('payload', {}).get('content'))[:50]}...")
                    
                    if data.get('event_type') == 'agent_thought':
                        print("[SUCCESS] Received Thought Event!")
                        return # Exit success
                        
                except asyncio.TimeoutError:
                    print(".", end="", flush=True)
                    continue
            
    except Exception as e:
        print(f"[FAIL] Connection error: {e}")


if __name__ == "__main__":
    try:
        asyncio.run(test_gateway())
    except KeyboardInterrupt:
        pass
