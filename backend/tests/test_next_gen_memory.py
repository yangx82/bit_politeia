import pytest
from backend.app.services.next_gen_memory import NextGenMemoryClient, next_gen_memory
from backend.app.services.resident_memory_service import ResidentMemory

def test_next_gen_memory_client_fallback():
    """Verify that NextGenMemoryClient gracefully handles offline services without raising exceptions."""
    client = NextGenMemoryClient()
    health = client.check_health()
    assert isinstance(health, dict)
    assert "active" in health

    # Operations should safely return False or empty structures when services are disconnected
    res = client.write_short_term("test_session", "user", "hello")
    assert isinstance(res, bool)

    stm = client.read_short_term("test_session", 5)
    assert isinstance(stm, list)

    refl = client.record_reflection("test_session", "TimeoutError", "Increase timeout limit")
    assert isinstance(refl, bool)

    search_refl = client.search_reflections("TimeoutError")
    assert isinstance(search_refl, list)

    fact_res = client.add_temporal_fact("Agent", "SEARCHES", "Literature")
    assert isinstance(fact_res, bool)

    facts = client.search_temporal_facts("Agent")
    assert isinstance(facts, list)

def test_resident_memory_next_gen_integration(tmp_path):
    """Verify ResidentMemory methods with NextGen memory integration."""
    mem = ResidentMemory()
    mem.log_interaction("user", "Testing NextGen Memory Sync", msg_type="chat")
    mem.record_reflection("test_session", "APIError", "Use retry handler")
    reflections = mem.get_reflections("APIError")
    assert isinstance(reflections, list)
