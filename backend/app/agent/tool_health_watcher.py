"""
Tool Health Watcher & Adaptive Pruner (Aristocles / AIP-5FAA-A9EB73 Distillation)
Tracks tool execution telemetry (call counts, success/failure rates, moving average latency),
dynamically prunes degraded tools from prompt injection, and manages cooldown probe recovery.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
import logging
import threading
import time

logger = logging.getLogger(__name__)


@dataclass
class ToolScore:
    """Telemetry and health metrics for a single tool."""
    tool_name: str
    calls: int = 0
    successes: int = 0
    failures: int = 0
    consecutive_failures: int = 0
    avg_latency: float = 0.0
    last_used: float = 0.0
    is_pruned: bool = False
    pruned_at: Optional[float] = None
    probe_in_flight: bool = False

    @property
    def success_rate(self) -> float:
        """Computes current success rate (0.0 to 1.0). Defaults to 1.0 if never called."""
        return (self.successes / self.calls) if self.calls > 0 else 1.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tool_name": self.tool_name,
            "calls": self.calls,
            "successes": self.successes,
            "failures": self.failures,
            "consecutive_failures": self.consecutive_failures,
            "avg_latency": round(self.avg_latency, 4),
            "success_rate": round(self.success_rate, 4),
            "last_used": self.last_used,
            "is_pruned": self.is_pruned,
            "pruned_at": self.pruned_at,
            "probe_in_flight": self.probe_in_flight,
        }


class ToolHealthWatcher:
    """
    Thread-safe monitor for tool health and availability.
    Implements circuit-breaker pattern with cooldown probe recovery.
    """

    def __init__(
        self,
        failure_threshold: int = 3,
        min_success_rate: float = 0.3,
        min_calls_for_rate: int = 5,
        cooldown_seconds: float = 60.0,
    ):
        self.failure_threshold = max(1, int(failure_threshold))
        self.min_success_rate = max(0.0, min(1.0, float(min_success_rate)))
        self.min_calls_for_rate = max(1, int(min_calls_for_rate))
        self.cooldown_seconds = max(0.01, float(cooldown_seconds))

        self._scores: Dict[str, ToolScore] = {}
        self._lock = threading.Lock()

    def record_execution(
        self,
        tool_name: str,
        success: bool,
        latency: float = 0.0,
    ) -> ToolScore:
        """
        Record a tool invocation outcome and update health status atomically.
        """
        valid_latency = max(0.0, float(latency))
        now = time.time()

        with self._lock:
            score = self._scores.get(tool_name)
            if not score:
                score = ToolScore(tool_name=tool_name)
                self._scores[tool_name] = score

            score.calls += 1
            score.last_used = now
            # Running average latency
            score.avg_latency = (
                (score.avg_latency * (score.calls - 1) + valid_latency) / score.calls
            )

            if success:
                score.successes += 1
                score.consecutive_failures = 0
                if score.is_pruned:
                    score.is_pruned = False
                    score.pruned_at = None
                    score.probe_in_flight = False
                    logger.info(
                        f"[ToolHealthWatcher] Tool '{tool_name}' recovered via successful probe. Restored to healthy."
                    )
            else:
                score.failures += 1
                score.consecutive_failures += 1
                should_prune = (
                    score.consecutive_failures >= self.failure_threshold
                    or (
                        score.calls >= self.min_calls_for_rate
                        and score.success_rate < self.min_success_rate
                    )
                )
                if should_prune and not score.is_pruned:
                    score.is_pruned = True
                    score.pruned_at = now
                    score.probe_in_flight = False
                    logger.warning(
                        f"[ToolHealthWatcher] Pruning tool '{tool_name}' due to health degradation "
                        f"(consecutive_failures={score.consecutive_failures}, "
                        f"success_rate={score.success_rate:.2%}). Cooldown: {self.cooldown_seconds}s"
                    )

            return score

    def is_healthy(self, tool_name: str) -> bool:
        """
        Checks if a tool is healthy and available for use.
        If pruned but cooldown expired, allows a single probe request (half-open state).
        """
        with self._lock:
            score = self._scores.get(tool_name)
            if not score or not score.is_pruned:
                return True

            # Tool is pruned; check if cooldown period has elapsed
            now = time.time()
            if score.pruned_at and (now - score.pruned_at >= self.cooldown_seconds):
                if not score.probe_in_flight:
                    score.probe_in_flight = True
                    logger.info(
                        f"[ToolHealthWatcher] Tool '{tool_name}' cooldown elapsed ({self.cooldown_seconds}s). "
                        f"Permitting single probe execution."
                    )
                    return True

            return False

    def filter_healthy_tools(self, tools: List[Any]) -> List[Any]:
        """
        Filters a collection of tools (ToolMeta objects or strings) returning only healthy items.
        """
        healthy = []
        for t in tools:
            name = getattr(t, "name", str(t))
            if self.is_healthy(name):
                healthy.append(t)
        return healthy

    def get_score(self, tool_name: str) -> Optional[ToolScore]:
        """Retrieve a copy or reference of a tool's current score."""
        with self._lock:
            return self._scores.get(tool_name)

    def get_all_scores(self) -> Dict[str, ToolScore]:
        """Retrieve snapshot of all tracked tool scores."""
        with self._lock:
            return dict(self._scores)

    def reset(self, tool_name: Optional[str] = None) -> None:
        """Reset telemetry for a specific tool or all tools."""
        with self._lock:
            if tool_name:
                self._scores.pop(tool_name, None)
            else:
                self._scores.clear()


# Shared singleton instance
tool_health_watcher = ToolHealthWatcher()
