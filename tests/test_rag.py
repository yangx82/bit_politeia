import pytest

from backend.app.services.knowledge_base import KnowledgeBase


@pytest.fixture
def kb():
    return KnowledgeBase()


def test_ingestion(kb):
    history = [
        {"content": "I love AI safety research", "timestamp": "2025-01-01", "source": "chat"},
        {"content": "Voting for proposal 1", "timestamp": "2025-01-02", "source": "chat"},
    ]
    archives = [{"index": 1, "timestamp": 12345, "data": {"summary": "Election 1 passed"}}]

    kb.ingest_history(history)
    kb.ingest_archives(archives)

    assert len(kb.documents) == 3
    assert any(d["source"] == "resident_history" for d in kb.documents)
    assert any(d["source"] == "community_archive" for d in kb.documents)


def test_retrieval(kb):
    kb.documents = [
        {"content": "AI Safety is critical", "source": "doc1"},
        {"content": "Local weather is nice", "source": "doc2"},
    ]

    # Should retrieve doc1
    context = kb.retrieve_context("Tell me about AI Safety")
    assert "AI Safety is critical" in context
    assert "Local weather" not in context

    # Should retrive nothing relevant
    context = kb.retrieve_context("Quantum mechanics")
    assert "No relevant" in context or context == ""


def test_web_search_integration(kb):
    # Test specific keyword triggers
    res = kb.web_researcher.search("AI Governance")
    assert "AI Governance trends" in res

    res = kb.web_researcher.search("P2P economy")
    assert "Tokenomics" in res

    # Test combined RAG + Web
    kb.documents = [{"content": "We use P2P voting", "source": "local"}]
    combined = kb.search_web_and_context("P2P economy")

    assert "We use P2P voting" in combined
    assert "Tokenomics" in combined
