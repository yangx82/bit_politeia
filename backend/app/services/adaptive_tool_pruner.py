"""
Adaptive Tool Result Pruning with Full-Content SHA-256 Hashing
AIP-83980595 v4 - Production-Ready Thread-Safe LRU Cache

Features:
- FIX #1: Full-content SHA-256 hashing (no truncation)
- FIX #2: Bounded LRU cache with OrderedDict
- FIX #3: Thread-safe operations with threading.Lock
- FIX #4: tiktoken estimation with fallback
- FIX #5: Pruned content retrieval API
- FIX #6: IMPORTANCE_WEIGHTS with 'default' key

Research Sources:
- https://arxiv.org/abs/2310.06825 (Mistral 7B)
- https://arxiv.org/abs/2401.07872 (Context Length Extension)
- https://arxiv.org/abs/2305.14327 (Dynosaur)
"""

import json
import hashlib
import threading
from typing import Dict, Optional
from dataclasses import dataclass
from collections import OrderedDict


@dataclass
class ToolResult:
    """Cached tool result with metadata."""
    tool_name: str
    raw_output: str
    token_count: int
    importance_score: float
    pruned_output: Optional[str] = None


class AdaptiveToolResultPruner:
    """Thread-safe adaptive tool result pruner with bounded LRU cache."""

    TOOL_BUDGETS = {
        'file_read': 2000,
        'web_search': 1500,
        'shell_command': 3000,
        'database_query': 2500,
        'default': 1000,
    }

    IMPORTANCE_WEIGHTS = {
        'error': 1.0,
        'structured_data': 0.8,
        'code_output': 0.7,
        'search_results': 0.6,
        'file_content': 0.5,
        'default': 0.5,  # FIX #6: Added missing 'default' key
    }

    def __init__(self, total_budget: int = 16000, max_cache_size: int = 256):
        self.total_budget = total_budget
        self.max_cache_size = max_cache_size
        self.cache: OrderedDict[str, ToolResult] = OrderedDict()  # FIX #2: Bounded LRU
        self._lock = threading.Lock()  # FIX #3: Thread-safety
        
        # FIX #4: Initialize tiktoken encoder with fallback
        try:
            import tiktoken
            self._tokenizer = tiktoken.get_encoding('cl100k_base')
        except ImportError:
            self._tokenizer = None

    def compute_result_hash(self, tool_name: str, output: str) -> str:
        """FIX #1: Hash FULL content, not just first 500 chars."""
        key_data = f"{tool_name}:{output}"  # Full output, no truncation
        return hashlib.sha256(key_data.encode()).hexdigest()[:16]

    def estimate_tokens(self, text: str) -> int:
        """FIX #4: Use tiktoken for accurate token estimation."""
        if self._tokenizer is not None:
            return len(self._tokenizer.encode(text))
        # Fallback if tiktoken unavailable
        return len(text) // 4

    def score_importance(self, tool_name: str, output: str) -> float:
        """Score importance based on content type and keywords."""
        base_weight = self.IMPORTANCE_WEIGHTS.get('default', 0.5)  # FIX #6: Safe access
        
        error_keywords = ['error', 'exception', 'traceback', 'failed', 'critical']
        if any(kw in output.lower() for kw in error_keywords):
            base_weight = max(base_weight, self.IMPORTANCE_WEIGHTS['error'])
        
        try:
            json.loads(output)
            base_weight = max(base_weight, self.IMPORTANCE_WEIGHTS['structured_data'])
        except (json.JSONDecodeError, ValueError):
            pass
        
        return min(base_weight, 1.0)

    def prune_result(self, tool_name: str, output: str, budget: int) -> str:
        """Prune output to fit within token budget."""
        current_tokens = self.estimate_tokens(output)
        if current_tokens <= budget:
            return output
        
        lines = output.split('\n')
        if len(lines) > 20:
            header = '\n'.join(lines[:5])
            tail = '\n'.join(lines[-5:])
            summary = f"\n... [{len(lines) - 10} lines truncated, {current_tokens - budget} tokens saved] ...\n"
            return f"{header}{summary}{tail}"
        else:
            char_budget = budget * 4
            return output[:char_budget] + '\n... [truncated] ...'

    def process_tool_result(self, tool_name: str, output: str) -> str:
        """Process and cache tool result with thread-safety."""
        result_hash = self.compute_result_hash(tool_name, output)
        
        # FIX #3: Thread-safe cache access
        with self._lock:
            if result_hash in self.cache:
                # Mark as most recently used
                self.cache.move_to_end(result_hash)
                return f"[Duplicate of previous {tool_name} result - cached, hash={result_hash}]"
        
        importance = self.score_importance(tool_name, output)
        category = self._categorize_tool(tool_name)
        budget = int(self.TOOL_BUDGETS.get(category, self.TOOL_BUDGETS['default']) * importance)
        pruned = self.prune_result(tool_name, output, budget)
        
        # FIX #3: Thread-safe cache insertion with LRU eviction
        with self._lock:
            # FIX #2: Evict LRU entry if cache is full
            if len(self.cache) >= self.max_cache_size:
                self.cache.popitem(last=False)  # Remove least recently used
            
            self.cache[result_hash] = ToolResult(
                tool_name=tool_name,
                raw_output=output,
                token_count=self.estimate_tokens(output),
                importance_score=importance,
                pruned_output=pruned,
            )
        
        return pruned

    def get_cached_result(self, result_hash: str) -> Optional[ToolResult]:
        """FIX #5: Retrieve cached ToolResult by hash (pruned content retrieval API)."""
        with self._lock:
            if result_hash in self.cache:
                self.cache.move_to_end(result_hash)  # Mark as recently used
                return self.cache[result_hash]
        return None

    def get_full_output(self, result_hash: str) -> Optional[str]:
        """FIX #5: Retrieve full (unpruned) output from cache by hash."""
        result = self.get_cached_result(result_hash)
        return result.raw_output if result else None

    def get_pruned_output(self, result_hash: str) -> Optional[str]:
        """FIX #5: Retrieve pruned output from cache by hash."""
        result = self.get_cached_result(result_hash)
        return result.pruned_output if result else None

    def _categorize_tool(self, tool_name: str) -> str:
        """Categorize tool by name for budget allocation."""
        name_lower = tool_name.lower()
        if 'file' in name_lower or 'read' in name_lower:
            return 'file_read'
        elif 'search' in name_lower or 'web' in name_lower:
            return 'web_search'
        elif 'shell' in name_lower or 'command' in name_lower or 'exec' in name_lower:
            return 'shell_command'
        elif 'database' in name_lower or 'query' in name_lower:
            return 'database_query'
        return 'default'

    def clear_cache(self):
        """Clear all cached results (thread-safe)."""
        with self._lock:
            self.cache.clear()

    def get_cache_stats(self) -> Dict[str, int]:
        """Get cache statistics (thread-safe)."""
        with self._lock:
            return {
                'size': len(self.cache),
                'max_size': self.max_cache_size,
                'utilization': len(self.cache) / self.max_cache_size if self.max_cache_size > 0 else 0
            }


# Basic test cases
def test_adaptive_pruner():
    """Verify all 6 fixes are working."""
    pruner = AdaptiveToolResultPruner(max_cache_size=3)
    
    # Test #1: Full-content hashing (no false cache hits)
    output1 = "A" * 1000
    output2 = "A" * 1000 + "B"  # Same prefix, different content
    hash1 = pruner.compute_result_hash("tool", output1)
    hash2 = pruner.compute_result_hash("tool", output2)
    assert hash1 != hash2, "Fix #1 failed: Different outputs should have different hashes"
    
    # Test #2: Bounded LRU cache
    for i in range(5):
        pruner.process_tool_result(f"tool_{i}", f"output_{i}")
    stats = pruner.get_cache_stats()
    assert stats['size'] <= 3, "Fix #2 failed: Cache exceeded max_size"
    
    # Test #3: Thread-safety (basic smoke test)
    import threading
    results = []
    def worker():
        for i in range(100):
            pruner.process_tool_result("concurrent", f"data_{i}")
            results.append(pruner.get_cache_stats())
    
    threads = [threading.Thread(target=worker) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert all(s['size'] <= 3 for s in results), "Fix #3 failed: Thread-safety violation"
    
    # Test #4: tiktoken estimation
    token_count = pruner.estimate_tokens("Hello world")
    assert token_count > 0, "Fix #4 failed: Token estimation returned 0"
    
    # Test #5: Pruned content retrieval API
    test_hash = pruner.compute_result_hash("test", "test_output")
    pruner.process_tool_result("test", "test_output")
    result = pruner.get_cached_result(test_hash)
    assert result is not None, "Fix #5 failed: Cannot retrieve cached result"
    assert result.raw_output == "test_output", "Fix #5 failed: Full output mismatch"
    
    # Test #6: IMPORTANCE_WEIGHTS has 'default' key
    assert 'default' in pruner.IMPORTANCE_WEIGHTS, "Fix #6 failed: Missing 'default' key"
    score = pruner.score_importance("unknown_tool", "plain text")
    assert score == 0.5, "Fix #6 failed: Default weight not applied"
    
    print("All 6 fixes verified successfully!")


if __name__ == "__main__":
    test_adaptive_pruner()
