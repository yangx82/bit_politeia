import ast
import os
import shutil
import tempfile
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

UTC = timezone.utc

from app.p2p_community.governance import AIPProposal, Vote
from app.services.evolution_service import EvolutionService


@pytest.fixture
def temp_evo_dir():
    temp_dir = tempfile.mkdtemp(prefix="test_ponytail_evo_")
    yield temp_dir
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def evo_service(temp_evo_dir):
    return EvolutionService(data_dir=temp_evo_dir)


def test_calculate_draft_importance_score_ponytail_bonus_and_penalty(evo_service):
    """
    Verify that calculate_draft_importance_score rewards focused atomic classes (<=2)
    and penalizes multi-class sprawl (>=3 classes) as per Ponytail Ladder.
    """
    local_id = "node_local_5a40"

    # 1. Minimalist atomic implementation (1 class)
    focused_code = (
        "import threading\n"
        "class AtomicTokenLimiter:\n"
        "    def __init__(self, limit: int = 100):\n"
        "        self._limit = max(1, int(limit))\n"
        "        self._lock = threading.Lock()\n"
        "    def check(self) -> bool:\n"
        "        with self._lock:\n"
        "            return self._limit > 0\n"
        "def test_limiter():\n"
        "    limiter = AtomicTokenLimiter(10)\n"
        "    assert limiter.check() is True\n"
    )
    focused_aip = AIPProposal(
        aip_id="AIP-FOCUSED-1",
        initiator_id=local_id,
        title="Focused Token Limiter",
        description="Atomic thread-safe rate limiter with bounds checking",
        target_files=["backend/app/services/agent_service.py"],
        proposed_diff=focused_code,
        research_sources=["https://arxiv.org/abs/2304.03442"],
        status="draft",
    )
    score_focused = evo_service.calculate_draft_importance_score(focused_aip)

    # 2. Over-engineered multi-class sprawl (4 classes: factory, interface, builder, impl)
    sprawl_code = (
        "import threading\n"
        "class ITokenLimiter:\n"
        "    pass\n"
        "class LimiterConfig:\n"
        "    pass\n"
        "class LimiterFactory:\n"
        "    pass\n"
        "class ConcreteTokenLimiter(ITokenLimiter):\n"
        "    def __init__(self):\n"
        "        self._lock = threading.Lock()\n"
        "def test_sprawl():\n"
        "    assert True\n"
    )
    sprawl_aip = AIPProposal(
        aip_id="AIP-SPRAWL-1",
        initiator_id=local_id,
        title="Over-engineered Token Limiter",
        description="Multi-tier factory interface wrapper limiter",
        target_files=["backend/app/services/agent_service.py"],
        proposed_diff=sprawl_code,
        research_sources=["https://arxiv.org/abs/2304.03442"],
        status="draft",
    )
    score_sprawl = evo_service.calculate_draft_importance_score(sprawl_aip)

    # Focused atomic proposal should score significantly higher than the sprawling one
    assert score_focused > score_sprawl
    # Sprawl penalty: 4 classes means (4 - 2) * 5.0 = 10.0 deduction vs +10.0 bonus
    assert score_focused - score_sprawl >= 15.0


@pytest.mark.asyncio
async def test_audit_aip_dimension_6_rejects_excessive_class_sprawl(evo_service):
    """
    Verify that Dimension 6 (Anti-Over-Engineering / Ponytail Minimalism)
    rejects proposals that define 4 or more classes in an atomic AIP.
    """
    sprawl_code = (
        "import threading\n"
        "class BaseHandler:\n"
        "    pass\n"
        "class HandlerFactory:\n"
        "    pass\n"
        "class HandlerConfig:\n"
        "    pass\n"
        "class ConcreteHandler(BaseHandler):\n"
        "    def __init__(self):\n"
        "        self._lock = threading.Lock()\n"
        "def test_handler():\n"
        "    assert True\n"
    )
    sprawl_aip = AIPProposal(
        aip_id="AIP-AUDIT-SPRAWL",
        initiator_id="node_5a40",
        title="Excessive Handler Overhaul",
        description="Over-engineered component with 4 classes",
        target_files=["backend/app/services/agent_service.py"],
        proposed_diff=sprawl_code,
        research_sources=["https://arxiv.org/abs/2304.03442"],
        status="draft",
    )
    evo_service.aips[sprawl_aip.aip_id] = sprawl_aip

    with patch("app.services.aip_quality_gate.quality_gate_service.evaluate_proposal") as mock_gate:
        mock_gate.return_value = MagicMock(passed=True, issues=[])
        vote = await evo_service.audit_aip(sprawl_aip.aip_id, llm_client=None)

        assert vote.approval is False
        assert "Dimension 6: Excessive Over-Engineering / Class Sprawl" in vote.reason
        assert "Ponytail Standard" in vote.reason


@pytest.mark.asyncio
async def test_audit_aip_dimension_6_approves_minimalist_code(evo_service):
    """Verify that Dimension 6 approves minimalist atomic code (<=2 classes)."""
    clean_code = (
        "import threading\n"
        "class CleanComponent:\n"
        "    def __init__(self, limit: int = 10):\n"
        "        self._limit = max(1, min(100, int(limit)))\n"
        "        self._lock = threading.Lock()\n"
        "    def get_limit(self) -> int:\n"
        "        with self._lock:\n"
        "            return self._limit\n"
        "def test_clean():\n"
        "    c = CleanComponent(5)\n"
        "    assert c.get_limit() == 5\n"
    )
    clean_aip = AIPProposal(
        aip_id="AIP-AUDIT-CLEAN",
        initiator_id="node_5a40",
        title="Clean Atomic Component",
        description="Clean atomic implementation with bounds checking and lock",
        target_files=["backend/app/services/agent_service.py"],
        proposed_diff=clean_code,
        research_sources=["https://arxiv.org/abs/2304.03442"],
        status="draft",
    )
    evo_service.aips[clean_aip.aip_id] = clean_aip

    with patch("app.services.aip_quality_gate.quality_gate_service.evaluate_proposal") as mock_gate:
        mock_gate.return_value = MagicMock(passed=True, issues=[])
        vote = await evo_service.audit_aip(clean_aip.aip_id, llm_client=None)

        assert vote.approval is True
        assert "Ponytail minimalist architecture" in vote.reason


@pytest.mark.asyncio
async def test_auto_explore_and_propose_embeds_ponytail_ladder(evo_service):
    """
    Verify that auto_explore_and_propose transmits the Ponytail 7-rung ladder
    and YAGNI constraints to both the Planner (Stage 1) and Coding Sub-Agent (Stage 2).
    """
    captured_prompts = []

    async def mock_invoke(client, prompt):
        captured_prompts.append(prompt)
        if "Lead Architecture Planner" in prompt:
            return {
                "title": "Atomic Fast Buffer",
                "description": "Minimalist buffer using collections.deque",
                "target_files": ["backend/app/services/agent_service.py"],
                "coding_specification": "Implement thread-safe FastBuffer with maxlen",
            }
        else:
            return {
                "proposed_diff": (
                    "import threading\nfrom collections import deque\n"
                    "class FastBuffer:\n"
                    "    def __init__(self, maxlen: int = 100):\n"
                    "        self._buf = deque(maxlen=max(1, int(maxlen)))\n"
                    "        self._lock = threading.Lock()\n"
                    "def test_buf():\n"
                    "    assert True\n"
                )
            }

    mock_llm = MagicMock()
    with patch("app.services.evolution_service._invoke_llm_json", side_effect=mock_invoke), \
         patch.object(evo_service, "is_in_cooldown", return_value=(False, "")):

        aip = await evo_service.auto_explore_and_propose(llm_client=mock_llm)
        assert aip is not None
        assert len(captured_prompts) == 2

        # Check Stage 1 Planner prompt
        planner_prompt = captured_prompts[0]
        assert "PONYTAIL MINIMALIST ARCHITECTURE PRINCIPLES" in planner_prompt
        assert "The Ladder - Anti-Over-Engineering" in planner_prompt
        assert "YAGNI -> omit it" in planner_prompt
        assert "NO unrequested abstractions" in planner_prompt

        # Check Stage 2 Coding Sub-Agent prompt
        coder_prompt = captured_prompts[1]
        assert "STRICT PONYTAIL RULES" in coder_prompt
        assert "The best code is the code you never wrote" in coder_prompt
        assert "Zero Over-Engineering" in coder_prompt


@pytest.mark.asyncio
async def test_revise_aip_prompt_contains_ponytail_root_cause_principle(evo_service):
    """Verify that revise_aip prompt embeds the Ponytail Root-Cause Revision Principle."""
    aip = AIPProposal(
        aip_id="AIP-REVISE-1",
        initiator_id="node_5a40",
        title="Revise Test",
        description="Desc",
        proposed_diff="def foo(): pass",
        status="draft",
    )
    evo_service.aips[aip.aip_id] = aip

    captured_prompt = []

    async def mock_invoke(client, prompt):
        captured_prompt.append(prompt)
        return {
            "title": "Revised Test",
            "description": "Updated",
            "proposed_diff": "def foo_fixed(): assert True",
        }

    mock_llm = MagicMock()
    with patch("app.services.evolution_service._invoke_llm_json", side_effect=mock_invoke):
        revised = await evo_service.revise_aip(aip.aip_id, feedback="Missing assertion", llm_client=mock_llm)
        assert revised is not None
        assert len(captured_prompt) == 1
        assert "PONYTAIL ROOT-CAUSE REVISION PRINCIPLE" in captured_prompt[0]
        assert "Fix the root cause, not the symptom" in captured_prompt[0]
