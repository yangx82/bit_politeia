# 🏛️ [AIP 共识归档] AIP-0DA9-1A7DBE: QuadraticVotingHelper based on A Flexible Design for Funding 

## 1. 提案基本元数据 (Metadata)
- **提案编号 (AIP ID)**: `AIP-0DA9-1A7DBE`
- **提案发起节点**: `0da9e18d02c1dbea101090fd8b1d89ca1eb0715ab00dd7dde448d3fa7cb67ff3`
- **全网共识状态**: ✅ 已通过去中心化治理共识 (Consensus Passed)
- **归档时间戳**: `2026-10-30 18:29:28 UTC`
- **涉及代码目标文件**:
- `backend/app/p2p_community/governance.py`
- `backend/app/services/agent_service.py`
- **研究参考渊源**:
- https://arxiv.org/abs/1809.06421

---

## 2. 提案背景与设计动机 (Motivation & Architecture)
[Scope-Corrected | Atomic Enhancement] Implements atomic 去中心化治理与博弈机制 (Decentralized Governance & Game Theory) component inspired by A Flexible Design for Funding Public Goods (Quadratic Funding / CLR). Provides bounded validation and thread-safety. Non-Goals: Broad architectural overhaul, external daemon dependencies.

---

## 3. 质量门禁与沙盒验证报告 (Quality Gate & Sandbox)
- **AST 语法一致性与依赖校验**: ✅ 通过 (Passed)
- **沙盒运行与测试指标**:
```json
{
  "success": true,
  "stdout": "[Sandbox Verification] Code executed cleanly without exceptions.\n",
  "stderr": "",
  "timestamp": "2026-10-30T18:27:33.609812+00:00"
}
```
- **质量门禁审计报告**:
```json
{
  "passed": true,
  "issues": [],
  "summary": {
    "aip_id": "AIP-0DA9-1A7DBE",
    "passed": true,
    "total_issues": 0,
    "p0_count": 0,
    "p1_count": 0,
    "code_loc": 70,
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
import threading
import math
from typing import Dict


class QuadraticVotingHelper:
    """Thread-safe quadratic voting/funding helper.

    Based on 'A Flexible Design for Funding' (Buterin, Hitzig, Weyl).
    Cost of v votes = v² tokens.  Matching uses (Σ√cᵢ)² allocation.
    """

    def __init__(self, max_budget: float = 1_000_000.0, min_contribution: float = 0.01):
        self._lock = threading.Lock()
        self._max_budget: float = max(0.0, float(max_budget))
        self._min_contribution: float = max(0.0, float(min_contribution))
        self._contributions: Dict[str, float] = {}

    def set_budget(self, budget: float) -> None:
        """Update the matching pool budget with bounds checking."""
        with self._lock:
            self._max_budget = max(0.0, float(budget))

    def add_contribution(self, project_id: str, amount: float) -> float:
        """Record a contribution; returns cumulative total for the project."""
        if not project_id:
            raise ValueError("project_id must be non-empty")
        amount = max(self._min_contribution, min(self._max_budget, float(amount)))
        with self._lock:
            self._contributions[project_id] = self._contributions.get(project_id, 0.0) + amount
            return self._contributions[project_id]

    def get_quadratic_votes(self, project_id: str) -> float:
        """Return √(total_contributions) for a project."""
        with self._lock:
            total = self._contributions.get(project_id, 0.0)
        return math.sqrt(total) if total > 0 else 0.0

    def calculate_matching(self, project_id: str) -> float:
        """QF matching share: (√c_proj / Σ√c_all)² * budget."""
        with self._lock:
            if not self._contributions:
                return 0.0
            contributions = dict(self._contributions)
            budget = self._max_budget

        sqrt_vals = {pid: math.sqrt(amt) for pid, amt in contributions.items() if amt > 0}
        if project_id not in sqrt_vals:
            return 0.0
        sum_all = sum(sqrt_vals.values())
        if sum_all <= 0:
            return 0.0
        share = (sqrt_vals[project_id] / sum_all) ** 2
        return min(share * budget, budget)

    def get_all_shares(self) -> Dict[str, float]:
        """Return matching allocation for every project."""
        with self._lock:
            contributions = dict(self._contributions)
            budget = self._max_budget
        sqrt_vals = {pid: math.sqrt(a) for pid, a in contributions.items() if a > 0}
        sum_all = sum(sqrt_vals.values())
        if sum_all <= 0:
            return {}
        return {pid: min((sv / sum_all) ** 2 * budget, budget) for pid, sv in sqrt_vals.items()}

    def reset(self) -> None:
        """Clear all recorded contributions."""
        with self._lock:
            self._contributions.clear()


def test_quadratic_voting_helper() -> None:
    qv = QuadraticVotingHelper(max_budget=1000.0)
    qv.add_contribution("A", 100.0)
    qv.add_contribution("B", 25.0)
    # √100=10, √25=5, sum=15 → A share=(10/15)²≈0.4444 → ~444.44
    match_a = qv.calculate_matching("A")
    assert 440.0 < match_a < 450.0, f"Expected ~444.4 got {match_a}"
    assert abs(qv.get_quadratic_votes("A") - 10.0) < 1e-9
    qv.reset()
    assert qv.calculate_matching("A") == 0.0
    # Bounds: contribution below min is clamped up
    qv.add_contribution("C", 0.001)
    assert qv.get_quadratic_votes("C") >= math.sqrt(0.01)

```

---

> [!IMPORTANT]
> **归档说明**: 本文档由 Bit Politeia 去中心化演化引擎自动生成并存入归档仓 (`backend/data/passed_aips/`)。
> 核心节点及开发团队可根据本文档审阅补丁、运行回归测试，并择机提炼集成至主干分支。
