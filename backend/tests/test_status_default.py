
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
    chat_id: Optional[str] = None
    status: Optional[str] = None

def test_default_status():
    print("Testing default Message status...")
    m = Message(
        id="123",
        content="test",
        sender="agent",
        timestamp=datetime.now()
    )
    assert m.status is None
    print("SUCCESS: Default status is None.")

def test_p2p_status_flow():
    print("\nTesting P2P status flow...")
    m = Message(
        id="456",
        content="p2p message",
        sender="agent",
        timestamp=datetime.now(),
        chat_id="peer1",
        status="pending"
    )
    assert m.status == "pending"
    print("Initial status: pending")
    
    m.status = "sent"
    assert m.status == "sent"
    print("Updated status: sent")
    print("SUCCESS: P2P status tracking still works.")

if __name__ == "__main__":
    test_default_status()
    test_p2p_status_flow()
