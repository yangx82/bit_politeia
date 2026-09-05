import asyncio
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
import httpx

from app.services.aip_quality_gate import (
    Severity,
    QualityIssue,
    QualityReport,
    AsyncCitationVerifier,
    ASTConsistencyAuditor,
    ProposalSignatureVerifier,
    StructuralDuplicateDetector,
    QualityGateService,
    quality_gate_service,
)
from app.services.crypto_service import crypto_service
from app.services.evolution_service import evolution_service, AIPProposal


@pytest.mark.asyncio
async def test_citation_verifier_blocklist():
    """Verify that known hallucinated citations (e.g. 2408.00001) are caught immediately."""
    verifier = AsyncCitationVerifier()
    res = await verifier.verify_citation("2408.00001", claimed_topic="Adaptive TTL Cache")
    assert res["exists"] is True
    assert res["relevant"] is False
    assert "blacklisted" in res["error"].lower()


@pytest.mark.asyncio
async def test_citation_verifier_mocked_success():
    """Verify valid arXiv XML response parsing and semantic relevance."""
    verifier = AsyncCitationVerifier()

    mock_xml = """<?xml version="1.0" encoding="UTF-8"?>
    <feed xmlns="http://www.w3.org/2005/Atom">
      <entry>
        <id>http://arxiv.org/abs/2310.08560v1</id>
        <title>MemGPT: Towards LLMs as Operating Systems</title>
        <summary>This paper introduces MemGPT, an architecture managing memory hierarchies and virtual context.</summary>
      </entry>
    </feed>
    """

    mock_resp = MagicMock(status_code=200, text=mock_xml)
    mock_client = AsyncMock()
    mock_client.get.return_value = mock_resp

    res = await verifier.verify_citation(
        "2310.08560",
        claimed_topic="LLM Memory Hierarchies and Virtual Context Management",
        client=mock_client,
    )
    assert res["exists"] is True
    assert "MemGPT" in res["title"]
    assert res["relevant"] is True
    assert res["is_unreachable"] is False


@pytest.mark.asyncio
async def test_citation_verifier_nonexistent():
    """Verify nonexistent paper returns exists=False."""
    verifier = AsyncCitationVerifier()

    mock_xml = """<?xml version="1.0" encoding="UTF-8"?>
    <feed xmlns="http://www.w3.org/2005/Atom">
    </feed>
    """

    mock_resp = MagicMock(status_code=200, text=mock_xml)
    mock_client = AsyncMock()
    mock_client.get.return_value = mock_resp

    res = await verifier.verify_citation(
        "9999.99999",
        claimed_topic="Unknown paper",
        client=mock_client,
    )
    assert res["exists"] is False
    assert res["relevant"] is False


@pytest.mark.asyncio
async def test_citation_verifier_network_failsafe():
    """Verify that network errors or 429 do NOT falsely claim exists=False, but trigger fail-safe."""
    verifier = AsyncCitationVerifier()

    mock_client = AsyncMock()
    mock_client.get.side_effect = httpx.TimeoutException("Connection timed out")

    res = await verifier.verify_citation(
        "2305.10601",
        claimed_topic="Tree of Thoughts",
        client=mock_client,
    )
    assert res["exists"] is None
    assert res["is_unreachable"] is True
    assert "unreachable" in res["error"].lower()


def test_signature_verification_success_and_tampering():
    """Test cryptographic signature generation, validation, and tamper detection."""
    initiator_id = crypto_service.get_node_id()
    pubkey = crypto_service.get_public_key_string()
    aip_id = "AIP-TEST-001"
    title = "Test Adaptive Cache"
    description = "Implements thread-safe cache hint"
    proposed_diff = "def calculate_ttl(x): return x * 2"

    payload = ProposalSignatureVerifier.get_canonical_proposal_payload(
        aip_id, initiator_id, title, description, proposed_diff
    )
    signature = crypto_service.sign_message(payload)

    # 1. Valid signature
    is_valid, err = ProposalSignatureVerifier.verify_proposal_signature(
        aip_id, initiator_id, title, description, proposed_diff, signature, pubkey
    )
    assert is_valid is True
    assert err is None

    # 2. Tampered code diff
    tampered_diff = "def calculate_ttl(x): return x * 999"
    is_valid, err = ProposalSignatureVerifier.verify_proposal_signature(
        aip_id, initiator_id, title, description, tampered_diff, signature, pubkey
    )
    assert is_valid is False
    assert "verification failed" in err

    # 3. Identity spoofing (signer claims to be a different node ID)
    spoofed_initiator = "0da9e18ddeadbeef1234567890abcdef"
    is_valid, err = ProposalSignatureVerifier.verify_proposal_signature(
        aip_id, spoofed_initiator, title, description, proposed_diff, signature, pubkey
    )
    assert is_valid is False
    assert "Identity Spoofing Detected" in err


def test_ast_dangerous_code_and_syntax():
    """Verify AST blocks syntax errors and dangerous execution patterns."""
    # Syntax error
    invalid_code = "def foo( broken syntax"
    tree, err = ASTConsistencyAuditor.parse_code(invalid_code)
    assert tree is None
    assert "SyntaxError" in err

    # Dangerous patterns
    dangerous_code = "import os\nos.system('rm -rf /')\neval('1+1')"
    patterns = ASTConsistencyAuditor.check_dangerous_code(dangerous_code)
    assert "os.system(" in patterns
    assert "eval(" in patterns


def test_ast_inflation_and_scope_correction():
    """Verify description inflation detection and [Scope-Corrected] exemption."""
    inflated_desc = """
    This proposal implements the entire system multi-tier framework:
    (1) Adaptive Vector Cache Eviction
    (2) Gossip Protocol Compression
    (3) Distributed State Synchronization
    (4) Byzantine Fault Tolerance Consensus
    (5) Automatic Token Staking and Slashing
    (6) End-to-end Neural Network Inference
    """
    stub_code = """
def simple_add(a, b):
    return a + b
"""
    tree, _ = ASTConsistencyAuditor.parse_code(stub_code)
    res = ASTConsistencyAuditor.audit_consistency_and_inflation(
        inflated_desc, stub_code, tree, threshold=0.6
    )
    assert res["is_inflated"] is True
    assert res["passed"] is False

    # Now add [Scope-Corrected] declaration
    corrected_desc = inflated_desc + "\n[Scope-Corrected | Atomic Enhancement: Only implements simple_add helper]"
    res2 = ASTConsistencyAuditor.audit_consistency_and_inflation(
        corrected_desc, stub_code, tree, threshold=0.1
    )
    assert res2["is_inflated"] is False


def test_ast_structural_deduplication():
    """Verify AST normalization detects duplicate logic with different variable names and comments."""
    code_a = """
import threading

class CacheManager:
    # A thread safe cache
    def __init__(self, capacity: int = 100):
        self.lock = threading.Lock()
        self.capacity = capacity

    def get_val(self, key_name: str) -> int:
        with self.lock:
            return 42
"""

    code_b = """
import threading

class CacheManager:
    \"\"\"Docstring different.\"\"\"
    def __init__(self, max_size: int = 100):
        self._mutex = threading.Lock()
        self._limit = max_size

    def get_val(self, item_id: str) -> int:
        with self._mutex:
            return 42
"""

    fp_a = StructuralDuplicateDetector.compute_ast_fingerprint(code_a)
    fp_b = StructuralDuplicateDetector.compute_ast_fingerprint(code_b)
    assert fp_a == fp_b

    known = {"AIP-ORIGINAL": fp_a}
    is_dup, dup_id = StructuralDuplicateDetector.check_duplicate(code_b, known)
    assert is_dup is True
    assert dup_id == "AIP-ORIGINAL"


@pytest.mark.asyncio
async def test_quality_gate_service_evaluate_proposal():
    """Comprehensive test of QualityGateService.evaluate_proposal."""
    qg = QualityGateService()

    initiator_id = crypto_service.get_node_id()
    pubkey = crypto_service.get_public_key_string()
    aip_id = "AIP-TEST-002"
    title = "Adaptive Cache TTL Manager"
    description = """
    Implements:
    - AdaptiveCacheManager with threading.Lock
    - calculate_ttl function
    [Scope-Corrected | Atomic Enhancement]
    """
    valid_code = """
import threading

class AdaptiveCacheManager:
    def __init__(self, base_ttl=300):
        self._lock = threading.Lock()
        self.base_ttl = base_ttl

    def calculate_ttl(self, hit_rate: float) -> int:
        with self._lock:
            rate = max(0.0, min(1.0, float(hit_rate)))
            return int(self.base_ttl * (1.0 + rate))
"""
    payload = ProposalSignatureVerifier.get_canonical_proposal_payload(
        aip_id, initiator_id, title, description, valid_code
    )
    sig = crypto_service.sign_message(payload)

    # 1. Valid proposal should PASS
    report = await qg.evaluate_proposal(
        aip_id=aip_id,
        initiator_id=initiator_id,
        title=title,
        description=description,
        proposed_diff=valid_code,
        signature=sig,
        public_key=pubkey,
        require_signature=True,
    )
    assert report.passed is True
    assert report.summary["p0_count"] == 0

    # 2. Blocklisted citation should trigger P0
    report_bad_cit = await qg.evaluate_proposal(
        aip_id="AIP-TEST-003",
        initiator_id=initiator_id,
        title=title,
        description=description,
        proposed_diff=valid_code,
        research_sources=["https://arxiv.org/abs/2408.00001"],
        signature=sig,
        public_key=pubkey,
        require_signature=False,
    )
    assert report_bad_cit.passed is False
    p0_categories = [i.category for i in report_bad_cit.issues if i.severity == Severity.P0]
    assert "citation_relevance" in p0_categories


@pytest.mark.asyncio
async def test_evolution_service_integration_audit_gate():
    """Verify that evolution_service.audit_aip rejects P0 issues without invoking LLM."""
    test_aip = evolution_service.create_aip(
        initiator_id="test_node",
        title="Malicious or Dangerous Proposal",
        description="Dangerous command execution",
        proposed_diff="import os\nos.system('echo dangerous')",
    )

    vote = await evolution_service.audit_aip(test_aip.aip_id, llm_client=None)
    assert vote.approval is False
    assert "P0 Quality Gate Rejected" in vote.reason
    assert "security" in vote.reason or "dangerous" in vote.reason
