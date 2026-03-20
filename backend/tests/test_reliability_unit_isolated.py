
import json
import os
import uuid
from pathlib import Path
from datetime import datetime
from pydantic import BaseModel
from typing import Optional, List

# Define the models locally
class Message(BaseModel):
    id: str
    content: str
    sender: str
    timestamp: datetime
    session_id: Optional[str] = None
    status: str = "sent"

def log_interaction_logic(file_path, sender, content, session_id, status):
    entry = {
        "id": str(uuid.uuid4()),
        "timestamp": datetime.now().isoformat(),
        "sender": sender,
        "content": content,
        "session_id": session_id,
        "status": status
    }
    with open(file_path, 'a', encoding='utf-8') as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry["id"]

def update_message_status_logic(file_path, message_id, status):
    temp_path = file_path.with_suffix(".tmp")
    updated = False
    with open(file_path, 'r', encoding='utf-8') as f_in, \
         open(temp_path, 'w', encoding='utf-8') as f_out:
        for line in f_in:
            data = json.loads(line)
            if data.get("id") == message_id:
                data["status"] = status
                updated = True
            f_out.write(json.dumps(data, ensure_ascii=False) + "\n")
    if updated:
        os.replace(temp_path, file_path)
    else:
        os.remove(temp_path)
    return updated

def test_status_cycle():
    print("Testing isolated status update logic...")
    data_dir = Path("./test_data_v2")
    data_dir.mkdir(exist_ok=True)
    log_file = data_dir / "chat.jsonl"
    
    # 1. Log pending
    msg_id = log_interaction_logic(log_file, "agent", "hello", "peer1", "pending")
    
    with open(log_file, 'r') as f:
        data = json.loads(f.read())
        assert data["status"] == "pending"
        print(f"SUCCESS: Logged as 'pending' (ID: {msg_id})")
        
    # 2. Update to sent
    updated = update_message_status_logic(log_file, msg_id, "sent")
    assert updated == True
    
    with open(log_file, 'r') as f:
        data = json.loads(f.read())
        assert data["status"] == "sent"
        print("SUCCESS: Log entry updated to 'sent'")
        
    # 3. Update to failed
    updated = update_message_status_logic(log_file, msg_id, "failed")
    assert updated == True
    with open(log_file, 'r') as f:
        data = json.loads(f.read())
        assert data["status"] == "failed"
        print("SUCCESS: Log entry updated to 'failed'")

    # Cleanup
    os.remove(log_file)
    data_dir.rmdir()

if __name__ == "__main__":
    test_status_cycle()
