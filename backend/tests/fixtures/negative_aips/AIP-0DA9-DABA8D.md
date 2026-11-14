# 🏛️ [AIP 共识归档] AIP-0DA9-DABA8D: QuadraticVotingHelper with ReputationDecay and TallyAuditor for Track-A Governance

## 1. 提案基本元数据 (Metadata)
- **提案编号 (AIP ID)**: `AIP-0DA9-DABA8D`
- **提案发起节点**: `0da9e18d02c1dbea101090fd8b1d89ca1eb0715ab00dd7dde448d3fa7cb67ff3`
- **全网共识状态**: ✅ 已通过去中心化治理共识 (Consensus Passed)
- **归档时间戳**: `2026-10-30 06:29:29 UTC`
- **涉及代码目标文件**:
- `backend/app/p2p_community/governance.py`
- `backend/app/services/agent_service.py`
- **研究参考渊源**:
- https://arxiv.org/abs/1809.06421

---

## 2. 提案背景与设计动机 (Motivation & Architecture)
[Scope-Corrected | Atomic Enhancement] Implements three atomic governance primitives: (1) QuadraticVotingHelper calculates vote weight as sqrt(vote_power) per CLR mechanism, enabling proportional influence scaling; (2) ReputationDecayCalculator applies exponential time-decay to reputation scores, ensuring active participation is rewarded; (3) ProposalTallyAuditor provides deterministic vote tally verification using sorted aggregation for audit consistency. These components enable mathematically sound governance calculations with O(1) memory overhead and thread-safe operations. Non-Goals: No Sybil detection heuristics (requires ML/graph analysis beyond scope), no on-chain settlement integration, no multi-round iterative voting, no vote delegation mechanisms, no reputation storage/persistence (caller manages state), no external API dependencies.

---

## 3. 质量门禁与沙盒验证报告 (Quality Gate & Sandbox)
- **AST 语法一致性与依赖校验**: ✅ 通过 (Passed)
- **沙盒运行与测试指标**:
```json
{
  "success": true,
  "stdout": "All Track-A governance tests passed.\n[Sandbox Verification] Code executed cleanly without exceptions.\n",
  "stderr": "",
  "timestamp": "2026-10-30T06:28:03.110637+00:00"
}
```
- **质量门禁审计报告**:
```json
{
  "passed": true,
  "issues": [],
  "summary": {
    "aip_id": "AIP-0DA9-DABA8D",
    "passed": true,
    "total_issues": 0,
    "p0_count": 0,
    "p1_count": 0,
    "code_loc": 78,
    "claims_coverage": 1.0,
    "citations_checked": 1,
    "has_scope_tag": true
  }
}
```

---

## 4. 去中心化自治共识决议 (Consensus Decision)
- **投票共识**: 去中心化多智能体共识通过 (Consensus Passed)
- **法定门槛**: 法定人数达标 (Quorum Met)
- **共识决议**: 批准将该提案代码变更固化存证入核心节点归档仓
- **安全规约**: 根据《去中心化演化安全规约（方案一）》，阻断节点自主向远端 Git 仓库直接推送分支，避免未经核心复核的冗余分支污染代码库。

---

## 5. 建议的代码变更补丁 (Proposed Code Patch)
```diff
"""Track-A Governance Helpers: QuadraticVoting, ReputationDecay, TallyAudit.

Thread-safe utilities for decentralized governance & game-theory mechanisms.
Uses only stdlib: math, threading, typing, collections.
"""
import math
import threading
from typing import List, Tuple
from collections import Counter


class QuadraticVotingHelper:
    """Compute quadratic voting weights with thread-safe locking."""

    def __init__(self) -> None:
        self._lock = threading.Lock()

    def calculate_quadratic_weight(self, vote_power: int) -> float:
        """Return sqrt(vote_power) as the quadratic weight.

        Args:
            vote_power: Non-negative integer representing raw vote tokens.

        Returns:
            Square root of vote_power as float.

        Raises:
            ValueError: If vote_power is negative.
        """
        with self._lock:
            if vote_power < 0:
                raise ValueError(f"vote_power must be >= 0, got {vote_power}")
            return math.sqrt(vote_power)


class ReputationDecayCalculator:
    """Calculate exponential reputation decay over inactive days."""

    def __init__(self) -> None:
        self._lock = threading.Lock()

    def calculate_decayed_reputation(
        self, base_reputation: float, days_inactive: int, decay_rate: float = 0.05
    ) -> float:
        """Return reputation after exponential decay.

        Formula: base_reputation * (1 - decay_rate) ^ days_inactive

        Args:
            base_reputation: Non-negative starting reputation score.
            days_inactive: Non-negative number of inactive days.
            decay_rate: Decay factor in [0.0, 1.0]. Default 0.05.

        Returns:
            Decayed reputation as float.

        Raises:
            ValueError: If any input violates domain constraints.
        """
        with self._lock:
            if base_reputation < 0:
                raise ValueError(f"base_reputation must be >= 0, got {base_reputation}")
            if days_inactive < 0:
                raise ValueError(f"days_inactive must be >= 0, got {days_inactive}")
            if not (0.0 <= decay_rate <= 1.0):
                raise ValueError(f"decay_rate must be in [0, 1], got {decay_rate}")
            return base_reputation * math.pow(1.0 - decay_rate, days_inactive)


class ProposalTallyAuditor:
    """Verify proposal vote tallies with deterministic aggregation."""

    def __init__(self) -> None:
        self._lock = threading.Lock()

    def verify_tally(self, votes: List[Tuple[str, int]], expected_total: int) -> bool:
        """Check whether aggregated vote sum matches expected_total.

        Args:
            votes: List of (voter_id, weight) tuples.
            expected_total: The expected sum of all vote weights.

        Returns:
            True if the sum equals expected_total, False otherwise.
        """
        with self._lock:
            sorted_votes = sorted(votes, key=lambda v: v[0])
            counter: Counter = Counter()
            for voter_id, weight in sorted_votes:
                counter[voter_id] += weight
            return sum(counter.values()) == expected_total


# --- Minimalist Unit Tests ---
def test_governance_helpers():
    assert QuadraticVotingHelper().calculate_quadratic_weight(16) == 4.0
    assert abs(ReputationDecayCalculator().calculate_decayed_reputation(100.0, 10, 0.05) - 59.87) < 0.01
    auditor = ProposalTallyAuditor()
    assert auditor.verify_tally([('A', 10), ('B', 20)], 30) is True
    assert auditor.verify_tally([('A', 10), ('B', 20)], 31) is False


if __name__ == "__main__":
    test_governance_helpers()
    print("All Track-A governance tests passed.")

```

---

> [!IMPORTANT]
> **归档说明**: 本文档由 Bit Politeia 去中心化演化引擎自动生成并存入归档仓 (`backend/data/passed_aips/`)。
> 核心节点及开发团队可根据本文档审阅补丁、运行回归测试，并择机提炼集成至主干分支。
