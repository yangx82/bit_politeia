"""
ToolExecutionPipeline - Thread-safe tool execution with Toolformer-inspired
scoring and adaptive pruning. Input bounds checking on all parameters.
"""
import threading
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Callable, Any


@dataclass
class ToolScore:
    """Tracks execution statistics for a single tool."""
    name: str
    calls: int = 0
    successes: int = 0
    avg_latency: float = 0.0
    last_used: float = 0.0

    @property
    def success_rate(self) -> float:
        return self.successes / max(1, self.calls)


class ToolExecutionPipeline:
    """Thread-safe pipeline for tool execution with adaptive pruning.

    Inspired by Toolformer: scores each tool invocation and prunes
    low-value tools from the active set based on a configurable threshold.
    """

    def __init__(
        self,
        prune_threshold: float = 0.3,
        max_tools: int = 64,
        cooldown_seconds: float = 5.0,
    ):
        # Defensive bounds checking on all inputs
        self._prune_threshold = max(0.0, min(1.0, float(prune_threshold)))
        self._max_tools = max(1, min(512, int(max_tools)))
        self._cooldown = max(0.1, min(3600.0, float(cooldown_seconds)))
        self._lock = threading.RLock()
        self._scores: Dict[str, ToolScore] = {}
        self._pruned: Dict[str, float] = {}  # name -> prune timestamp
        self._handlers: Dict[str, Callable] = {}

    @property
    def prune_threshold(self) -> float:
        return self._prune_threshold

    @property
    def max_tools(self) -> int:
        return self._max_tools

    def register_tool(self, name: str, handler: Callable) -> None:
        """Register a tool handler. Name must be non-empty."""
        if not name or not isinstance(name, str):
            raise ValueError("Tool name must be a non-empty string")
        with self._lock:
            self._handlers[name] = handler
            if name not in self._scores:
                self._scores[name] = ToolScore(name=name)

    def should_use_tool(self, name: str) -> bool:
        """Toolformer-style decision: should this tool be invoked?"""
        with self._lock:
            if name not in self._handlers:
                return False
            # Check cooldown after pruning
            if name in self._pruned:
                if time.time() - self._pruned[name] < self._cooldown:
                    return False
                del self._pruned[name]
            score = self._scores.get(name)
            if score is None or score.calls == 0:
                return True  # Allow first invocation
            return score.success_rate >= self._prune_threshold

    def execute(self, name: str, *args: Any, **kwargs: Any) -> Any:
        """Execute a tool with score tracking and latency measurement."""
        if not self.should_use_tool(name):
            raise RuntimeError(f"Tool '{name}' is pruned or unregistered")
        start = time.time()
        handler = self._handlers[name]
        try:
            result = handler(*args, **kwargs)
            elapsed = time.time() - start
            with self._lock:
                s = self._scores[name]
                s.calls += 1
                s.successes += 1
                s.avg_latency = (s.avg_latency * (s.calls - 1) + elapsed) / s.calls
                s.last_used = time.time()
            return result
        except Exception:
            with self._lock:
                s = self._scores[name]
                s.calls += 1
                s.last_used = time.time()
            raise

    def prune_low_value(self) -> List[str]:
        """Remove tools below prune_threshold. Returns list of pruned names."""
        pruned = []
        now = time.time()
        with self._lock:
            for name, score in list(self._scores.items()):
                if score.calls >= 3 and score.success_rate < self._prune_threshold:
                    self._pruned[name] = now
                    pruned.append(name)
        return pruned

    def get_stats(self) -> Dict[str, dict]:
        """Return a snapshot of all tool scores."""
        with self._lock:
            return {
                n: {"calls": s.calls, "success_rate": round(s.success_rate, 4),
                    "avg_latency": round(s.avg_latency, 4)}
                for n, s in self._scores.items()
            }


# ── Minimal Tests ──────────────────────────────────────────────────────

def test_pipeline_basic_execution():
    p = ToolExecutionPipeline(prune_threshold=0.5, max_tools=10)
    p.register_tool("add", lambda a, b: a + b)
    assert p.execute("add", 2, 3) == 5
    stats = p.get_stats()
    assert stats["add"]["calls"] == 1
    assert stats["add"]["success_rate"] == 1.0


def test_pipeline_bounds_and_pruning():
    p = ToolExecutionPipeline(prune_threshold=0.0, max_tools=0)
    assert p.max_tools == 1  # clamped from 0
    p2 = ToolExecutionPipeline(prune_threshold=2.0)
    assert p2.prune_threshold == 1.0  # clamped from 2.0
    # Pruning: tool with 0% success after 3 calls
    p3 = ToolExecutionPipeline(prune_threshold=0.5)
    call_count = [0]
    def failing_tool():
        call_count[0] += 1
        raise ValueError("fail")
    p3.register_tool("bad", failing_tool)
    for _ in range(3):
        try:
            p3.execute("bad")
        except ValueError:
            pass
    pruned = p3.prune_low_value()
    assert "bad" in pruned
    assert not p3.should_use_tool("bad")


def test_pipeline_thread_safety():
    import concurrent.futures
    p = ToolExecutionPipeline(prune_threshold=0.0)
    p.register_tool("inc", lambda: 1)
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        futs = [ex.submit(p.execute, "inc") for _ in range(200)]
        results = [f.result() for f in futs]
    assert all(r == 1 for r in results)
    assert p.get_stats()["inc"]["calls"] == 200
