import requests
import json
import os
import sys

# Assume backend is running at http://localhost:8001
API_URL = "http://localhost:8001/api/v1"

def verify_config_update():
    print(f"Testing Config Update on {API_URL}...")
    
    # 1. Update Config via API
    payload = {
        "base_url": "https://api.openai.com/v1",
        "api_key": "sk-test-key",
        "model": "gpt-4o",
        "name": "APITestAgent",
        "personality": "Robotic",
        "research_field": "Testing",
        "bootstrap_url": "http://localhost:8000",
        "bootstrap_verify": True
    }
    
    try:
        response = requests.post(f"{API_URL}/config", json=payload)
        response.raise_for_status()
        data = response.json()
        
        print(f"API Response: Name={data.get('name')}")
        
        if data.get("name") != "APITestAgent":
            print("FAIL: API response did not return updated name")
            return False
            
    except Exception as e:
        print(f"API Request Failed: {e}")
        return False

    # 2. Check JSON file directly (assuming we are on same machine)
    # We need to find where the backend wrote it. 
    # Try CWD or backend/ directory
    paths_to_check = [
        "agent_config.json", 
        "backend/agent_config.json", 
        "d:/BaiduSyncdisk/SIAT/coding/bit_politeia/backend/agent_config.json"
    ]
    
    found = False
    for p in paths_to_check:
        if os.path.exists(p):
            with open(p, 'r') as f:
                content = json.load(f)
                print(f"Found config at {p}: {content}")
                if content.get("name") == "APITestAgent":
                    print("PASS: JSON file updated correctly")
                    found = True
                    break
                else:
                    print(f"FAIL: JSON file at {p} has wrong name: {content.get('name')}")
    
    if not found:
        print("FAIL: Could not find agent_config.json or it was not updated.")
        return False

    # 3. Check ENV file (sensitive data)
    # This is harder to check programmatically without parsing .env, but let's try
    env_path = ".env"
    if os.path.exists(env_path):
        with open(env_path, 'r') as f:
            env_content = f.read()
            if "AGENT_NAME=APITestAgent" in env_content:
                print("PASS: .env updated with Agent Name")
            else:
                print("FAIL: .env NOT updated with Agent Name")
            
            # Check sensitive data
            if "AGENT_API_KEY=sk-test-key" in env_content:
                print("PASS: .env updated with API Key")
    
    return True

if __name__ == "__main__":
    verify_config_update()
