import threading
import time
import numpy as np
from typing import Dict, Optional, Tuple, Any
from dataclasses import dataclass, field
import logging

logger = logging.getLogger(__name__)

@dataclass
class CacheEntry:
    """Represents a cached vector with metadata."""
    vector: np.ndarray
    timestamp: float
    ttl: int
    access_count: int = 0
    last_latency: float = 0.0

class LatencyAwareVectorCache:
    """Thread-safe vector cache with adaptive TTL and latency tracking."""
    
    def __init__(self, base_ttl: int = 300, max_ttl: int = 3600, min_ttl: int = 30):
        self._cache: Dict[str, CacheEntry] = {}
        self._lock = threading.Lock()
        self.base_ttl = base_ttl
        self.max_ttl = max_ttl
        self.min_ttl = min_ttl
        self._hit_rates: Dict[str, float] = {}
        self._backoff_multipliers: Dict[str, float] = {}
        
    def _validate_hit_rate(self, hit_rate: float) -> float:
        """Validate and clamp hit_rate to [0.0, 1.0] with NaN/inf guards."""
        if not isinstance(hit_rate, (int, float)):
            raise TypeError(f"hit_rate must be numeric, got {type(hit_rate)}")
        if np.isnan(hit_rate) or np.isinf(hit_rate):
            logger.warning(f"Invalid hit_rate {hit_rate}, defaulting to 0.0")
            return 0.0
        return float(np.clip(hit_rate, 0.0, 1.0))
    
    def _validate_vector(self, vector: np.ndarray) -> np.ndarray:
        """Validate vector input."""
        if not isinstance(vector, np.ndarray):
            raise TypeError(f"vector must be numpy.ndarray, got {type(vector)}")
        if vector.size == 0:
            raise ValueError("vector cannot be empty")
        if np.any(np.isnan(vector)) or np.any(np.isinf(vector)):
            raise ValueError("vector contains NaN or inf values")
        return vector
    
    def compute_adaptive_ttl(self, hit_rate: float, latency_ms: float = 0.0) -> int:
        """
        Compute adaptive TTL based on hit rate and latency.
        Higher hit rates and lower latency -> longer TTL.
        
        Args:
            hit_rate: Cache hit rate in [0.0, 1.0]
            latency_ms: Observed latency in milliseconds
            
        Returns:
            Adaptive TTL in seconds
        """
        hit_rate = self._validate_hit_rate(hit_rate)
        
        # Base TTL adjusted by hit rate
        ttl = self.base_ttl * (1.0 + hit_rate)
        
        # Latency factor: lower latency = higher confidence = longer TTL
        if latency_ms > 0:
            latency_factor = 1.0 / (1.0 + np.log1p(latency_ms / 100.0))
            ttl *= latency_factor
        
        # Clamp to bounds
        ttl = int(np.clip(ttl, self.min_ttl, self.max_ttl))
        return ttl
    
    def compute_backoff_delay(self, key: str, consecutive_misses: int) -> float:
        """
        Compute exponential backoff delay for cache misses.
        
        Args:
            key: Cache key
            consecutive_misses: Number of consecutive misses
            
        Returns:
            Backoff delay in seconds
        """
        if consecutive_misses < 0:
            raise ValueError("consecutive_misses cannot be negative")
        
        with self._lock:
            multiplier = self._backoff_multipliers.get(key, 1.0)
        
        # Exponential backoff with jitter
        base_delay = 0.1  # 100ms base
        max_delay = 60.0  # 60s max
        delay = min(base_delay * (multiplier ** consecutive_misses), max_delay)
        
        # Add jitter (±20%)
        jitter = np.random.uniform(0.8, 1.2)
        return delay * jitter
    
    def get(self, key: str) -> Optional[Tuple[np.ndarray, float]]:
        """
        Retrieve vector from cache if not expired.
        
        Returns:
            Tuple of (vector, latency_ms) or None if miss/expired
        """
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                return None
            
            # Check TTL expiration
            age = time.time() - entry.timestamp
            if age > entry.ttl:
                del self._cache[key]
                return None
            
            entry.access_count += 1
            return (entry.vector.copy(), entry.last_latency)
    
    def put(self, key: str, vector: np.ndarray, hit_rate: float, latency_ms: float = 0.0) -> None:
        """
        Store vector in cache with adaptive TTL.
        
        Args:
            key: Cache key
            vector: Vector to cache
            hit_rate: Current hit rate for this key
            latency_ms: Observed retrieval latency
        """
        vector = self._validate_vector(vector)
        ttl = self.compute_adaptive_ttl(hit_rate, latency_ms)
        
        with self._lock:
            self._cache[key] = CacheEntry(
                vector=vector.copy(),
                timestamp=time.time(),
                ttl=ttl,
                last_latency=latency_ms
            )
            self._hit_rates[key] = self._validate_hit_rate(hit_rate)
    
    def update_backoff_multiplier(self, key: str, multiplier: float) -> None:
        """Update backoff multiplier for a key."""
        if multiplier <= 0:
            raise ValueError("multiplier must be positive")
        with self._lock:
            self._backoff_multipliers[key] = float(multiplier)
    
    def clear(self) -> None:
        """Clear all cached entries."""
        with self._lock:
            self._cache.clear()
            self._hit_rates.clear()
            self._backoff_multipliers.clear()
    
    def stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        with self._lock:
            return {
                'size': len(self._cache),
                'keys': list(self._cache.keys()),
                'hit_rates': self._hit_rates.copy(),
                'backoff_multipliers': self._backoff_multipliers.copy()
            }

# Integration example for agent_service.py
class AgentServiceIntegration:
    """Example integration with agent_service.py"""
    
    def __init__(self):
        self.cache = LatencyAwareVectorCache(base_ttl=300)
        self._consecutive_misses: Dict[str, int] = {}
    
    async def get_agent_vector(self, agent_id: str) -> Optional[np.ndarray]:
        """Retrieve agent vector with caching and backoff."""
        # Try cache first
        cached = self.cache.get(agent_id)
        if cached is not None:
            vector, latency = cached
            return vector
        
        # Cache miss - apply backoff
        misses = self._consecutive_misses.get(agent_id, 0)
        backoff_delay = self.cache.compute_backoff_delay(agent_id, misses)
        
        # Simulate async fetch with latency tracking
        start_time = time.time()
        try:
            # Fetch from source (placeholder)
            vector = await self._fetch_agent_vector(agent_id)
            latency_ms = (time.time() - start_time) * 1000
            
            # Update cache with observed hit rate
            hit_rate = 1.0 / (1.0 + misses)  # Decreasing hit rate with more misses
            self.cache.put(agent_id, vector, hit_rate, latency_ms)
            self._consecutive_misses[agent_id] = 0
            
            return vector
        except Exception as e:
            logger.error(f"Failed to fetch vector for {agent_id}: {e}")
            self._consecutive_misses[agent_id] = misses + 1
            raise
    
    async def _fetch_agent_vector(self, agent_id: str) -> np.ndarray:
        """Placeholder for actual vector fetching logic."""
        # This would integrate with your actual vector storage
        raise NotImplementedError("Implement actual vector fetching")

# Unit tests
def test_cache_validation():
    """Test input validation."""
    cache = LatencyAwareVectorCache()
    
    # Test hit_rate validation
    assert cache._validate_hit_rate(0.5) == 0.5
    assert cache._validate_hit_rate(-0.1) == 0.0
    assert cache._validate_hit_rate(1.5) == 1.0
    assert cache._validate_hit_rate(float('nan')) == 0.0
    assert cache._validate_hit_rate(float('inf')) == 0.0
    
    # Test vector validation
    valid_vector = np.array([1.0, 2.0, 3.0])
    assert np.array_equal(cache._validate_vector(valid_vector), valid_vector)
    
    try:
        cache._validate_vector(np.array([]))
        assert False, "Should raise ValueError for empty vector"
    except ValueError:
        pass
    
    try:
        cache._validate_vector(np.array([1.0, np.nan]))
        assert False, "Should raise ValueError for NaN"
    except ValueError:
        pass

def test_adaptive_ttl():
    """Test adaptive TTL computation."""
    cache = LatencyAwareVectorCache(base_ttl=300, min_ttl=30, max_ttl=3600)
    
    # Low hit rate -> lower TTL
    ttl_low = cache.compute_adaptive_ttl(0.1)
    assert 30 <= ttl_low <= 3600
    
    # High hit rate -> higher TTL
    ttl_high = cache.compute_adaptive_ttl(0.9)
    assert ttl_high > ttl_low
    
    # With latency
    ttl_with_latency = cache.compute_adaptive_ttl(0.5, latency_ms=500.0)
    assert 30 <= ttl_with_latency <= 3600

def test_backoff():
    """Test exponential backoff."""
    cache = LatencyAwareVectorCache()
    cache.update_backoff_multiplier('test_key', 2.0)
    
    delay_0 = cache.compute_backoff_delay('test_key', 0)
    delay_1 = cache.compute_backoff_delay('test_key', 1)
    delay_2 = cache.compute_backoff_delay('test_key', 2)
    
    # Delays should increase (with jitter)
    assert delay_0 > 0
    assert delay_1 > delay_0 * 0.8  # Account for jitter
    assert delay_2 > delay_1 * 0.8

def test_thread_safety():
    """Test concurrent access."""
    cache = LatencyAwareVectorCache()
    vector = np.array([1.0, 2.0, 3.0])
    
    def writer():
        for i in range(100):
            cache.put(f'key_{i}', vector, 0.5)
    
    def reader():
        for i in range(100):
            cache.get(f'key_{i}')
    
    import threading
    threads = [threading.Thread(target=writer), threading.Thread(target=reader)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    
    # Should not crash or deadlock
    stats = cache.stats()
    assert stats['size'] > 0

if __name__ == '__main__':
    test_cache_validation()
    test_adaptive_ttl()
    test_backoff()
    test_thread_safety()
    print('All tests passed!')
