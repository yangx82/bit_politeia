import sys
import os
import asyncio
import logging

# Ensure we can import from backend
sys.path.append(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend"))

from app.services.knowledge_base import knowledge_base

# Add mock data
mock_history = [
    {"content": "The sky is blue because of Rayleigh scattering.", "timestamp": "2025-01-01T12:00:00", "sender": "agent"},
    {"content": "Photosynthesis is the process by which plants make food.", "timestamp": "2025-01-02T12:00:00", "sender": "agent"},
    {"content": "The capital of France is Paris.", "timestamp": "2025-01-03T12:00:00", "sender": "agent"}
]

def test_semantic_search():
    print("Initializing Knowledge Base...")
    # This should trigger ChromaDB ingestion
    knowledge_base.ingest_history(mock_history)
    
    print("\n[TEST 1] Query: 'Why is the atmosphere azure?'")
    # Should match "The sky is blue..." even without sharing words
    results = knowledge_base.retrieve_context("Why is the atmosphere azure?", limit=1)
    print(f"Result:\n{results}")
    
    if "Rayleigh scattering" in results:
        print("[PASS] Semantic match found.")
    else:
        print("[FAIL] Semantic match failed.")
        
    print("\n[TEST 2] Query: 'How do trees eat?'")
    results = knowledge_base.retrieve_context("How do trees eat?", limit=1)
    print(f"Result:\n{results}")
    
    if "Photosynthesis" in results:
        print("[PASS] Semantic match found.")
    else:
        print("[FAIL] Semantic match failed.")

if __name__ == "__main__":
    try:
        test_semantic_search()
    except Exception as e:
        print(f"Test Failed: {e}")
