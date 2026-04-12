import os
import sys

# Ensure we can import from backend
sys.path.append(
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")
)

from app.services.knowledge_base import knowledge_base

# Add mock data
# 1. "The sky is blue" (Semantic match for "atmosphere azure")
# 2. "Error code 505: HTTP Version Not Supported" (Keyword match for "505")
# 3. "The capital of France is Paris." (Distractor)

mock_history = [
    {
        "content": "The sky is blue because of Rayleigh scattering.",
        "timestamp": "2025-01-01T12:00:00",
        "sender": "agent",
    },
    {
        "content": "Error code 505 means HTTP Version Not Supported.",
        "timestamp": "2025-01-02T12:00:00",
        "sender": "system",
    },
    {
        "content": "The capital of France is Paris.",
        "timestamp": "2025-01-03T12:00:00",
        "sender": "agent",
    },
]


def test_hybrid_search():
    print("Initializing Knowledge Base...")
    # This should trigger Chroma ingestion AND BM25 indexing
    knowledge_base.ingest_history(mock_history)

    # Test 1: Semantic Query (Vector should win)
    print("\n[TEST 1] Query: 'Why is the atmosphere azure?'")
    results = knowledge_base.retrieve_hybrid("Why is the atmosphere azure?", limit=2)
    print(f"Result:\n{results}")

    if "Rayleigh scattering" in results:
        print("[PASS] Semantic match found.")
    else:
        print("[FAIL] Semantic match failed.")

    # Test 2: Keyword Query (BM25 should win)
    print("\n[TEST 2] Query: 'Error code 505'")
    results = knowledge_base.retrieve_hybrid("Error code 505", limit=2)
    print(f"Result:\n{results}")

    if "HTTP Version Not Supported" in results:
        print("[PASS] Keyword match found.")
    else:
        print("[FAIL] Keyword match failed.")

    # Test 3: RRF (Both should contribute)
    # "France 505" -> Should retrieve both ideally, or rank based on strength
    print("\n[TEST 3] Query: 'France 505'")
    results = knowledge_base.retrieve_hybrid("France 505", limit=2)
    print(f"Result:\n{results}")

    if "Paris" in results and "HTTP" in results:
        print("[PASS] Combined retrieval successful.")
    else:
        print(f"[INFO] Partial match. Got: {results}")


if __name__ == "__main__":
    try:
        test_hybrid_search()
    except Exception as e:
        print(f"Test Failed: {e}")
