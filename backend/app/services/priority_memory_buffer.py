"""
PriorityMemoryBuffer: Bounded Context Management with Priority-Based Eviction

A thread-safe, bounded priority memory buffer for managing context windows.
Supports working memory (hot data) and archival storage (cold data), with
importance-based eviction of low-priority entries.

This is NOT LLM-driven distillation. It's a priority queue with concatenation.
For true MemGPT-style LLM self-editing, a different architecture is needed.

Reference: MemGPT (arXiv:2310.08560) - Towards LLMs as Operating Systems
"""

import threading
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass(order=True)
class MemoryEntry:
    """A memory entry with importance-based ordering."""
    importance: float
    content: str = field(compare=False)
    timestamp: float = field(compare=False)
    metadata: dict = field(default_factory=dict, compare=False)


class PriorityMemoryBuffer:
    """
    Thread-safe bounded priority memory buffer.
    
    Manages two storage tiers:
    - Working memory: Hot data with configurable capacity
    - Archival storage: Cold data (evicted entries) with configurable capacity
    
    Eviction is based on importance score (lowest first).
    Thread-safe using RLock for all shared state operations.
    """
    
    def __init__(
        self,
        working_capacity: int = 100,
        archival_capacity: int = 1000,
        eviction_ratio: float = 0.1
    ):
        """
        Initialize the priority memory buffer.
        
        Args:
            working_capacity: Maximum entries in working memory (1-1000)
            archival_capacity: Maximum entries in archival storage (10-10000)
            eviction_ratio: Fraction of working memory to evict when full (0.01-0.5)
        """
        if not 1 <= working_capacity <= 1000:
            raise ValueError(f"working_capacity must be in [1, 1000], got {working_capacity}")
        if not 10 <= archival_capacity <= 10000:
            raise ValueError(f"archival_capacity must be in [10, 10000], got {archival_capacity}")
        if not 0.01 <= eviction_ratio <= 0.5:
            raise ValueError(f"eviction_ratio must be in [0.01, 0.5], got {eviction_ratio}")
        
        self._working_capacity = working_capacity
        self._archival_capacity = archival_capacity
        self._eviction_ratio = eviction_ratio
        
        self._working: List[MemoryEntry] = []
        self._archival: List[MemoryEntry] = []
        self._lock = threading.RLock()
    
    def add(self, content: str, importance: float, timestamp: float, metadata: Optional[dict] = None) -> None:
        """
        Add an entry to working memory.
        
        If working memory is full, evict lowest-importance entries.
        Evicted entries are moved to archival storage.
        
        Args:
            content: The memory content (non-empty)
            importance: Priority score (0.0-10.0, higher = more important)
            timestamp: When this entry was created
            metadata: Optional metadata dictionary
        """
        if not content or not content.strip():
            raise ValueError("content must be non-empty")
        if not 0.0 <= importance <= 10.0:
            raise ValueError(f"importance must be in [0.0, 10.0], got {importance}")
        
        entry = MemoryEntry(
            importance=importance,
            content=content,
            timestamp=timestamp,
            metadata=metadata or {}
        )
        
        with self._lock:
            self._working.append(entry)
            # Sort by importance (ascending) for eviction
            self._working.sort(key=lambda e: e.importance)
            
            # Evict if over capacity
            while len(self._working) > self._working_capacity:
                self._evict_to_archival()
    
    def _evict_to_archival(self) -> None:
        """
        Evict lowest-importance entries from working memory to archival.
        
        Evicts eviction_ratio fraction of working memory.
        If archival is full, oldest entries are removed first.
        
        NOTE: Caller must hold self._lock.
        """
        num_to_evict = max(1, int(self._working_capacity * self._eviction_ratio))
        num_to_evict = min(num_to_evict, len(self._working))
        
        evicted = self._working[:num_to_evict]
        self._working = self._working[num_to_evict:]
        
        # Add to archival
        self._archival.extend(evicted)
        
        # If archival over capacity, remove oldest (lowest timestamp)
        while len(self._archival) > self._archival_capacity:
            self._archival.sort(key=lambda e: e.timestamp)
            self._archival = self._archival[1:]
    
    def get_working(self, limit: Optional[int] = None) -> List[MemoryEntry]:
        """
        Get entries from working memory, sorted by importance (highest first).
        
        Args:
            limit: Maximum number of entries to return (1-1000)
            
        Returns:
            List of MemoryEntry objects, sorted by importance descending
        """
        if limit is not None and not 1 <= limit <= 1000:
            raise ValueError(f"limit must be in [1, 1000], got {limit}")
        
        with self._lock:
            # Return sorted by importance descending
            sorted_working = sorted(self._working, key=lambda e: e.importance, reverse=True)
            if limit:
                return sorted_working[:limit]
            return sorted_working[:]
    
    def get_archival(self, limit: Optional[int] = None) -> List[MemoryEntry]:
        """
        Get entries from archival storage, sorted by importance (highest first).
        
        Args:
            limit: Maximum number of entries to return (1-1000)
            
        Returns:
            List of MemoryEntry objects, sorted by importance descending
        """
        if limit is not None and not 1 <= limit <= 1000:
            raise ValueError(f"limit must be in [1, 1000], got {limit}")
        
        with self._lock:
            sorted_archival = sorted(self._archival, key=lambda e: e.importance, reverse=True)
            if limit:
                return sorted_archival[:limit]
            return sorted_archival[:]
    
    def get_working_contents(self, limit: Optional[int] = None) -> List[str]:
        """
        Get content strings from working memory (convenience method).
        
        Args:
            limit: Maximum number of entries to return
            
        Returns:
            List of content strings, sorted by importance descending
        """
        return [e.content for e in self.get_working(limit)]
    
    def get_archival_contents(self, limit: Optional[int] = None) -> List[str]:
        """
        Get content strings from archival storage (convenience method).
        
        Args:
            limit: Maximum number of entries to return
            
        Returns:
            List of content strings, sorted by importance descending
        """
        return [e.content for e in self.get_archival(limit)]
    
    def clear_working(self) -> None:
        """Clear all entries from working memory."""
        with self._lock:
            self._working.clear()
    
    def clear_archival(self) -> None:
        """Clear all entries from archival storage."""
        with self._lock:
            self._archival.clear()
    
    def clear_all(self) -> None:
        """Clear all entries from both working and archival storage."""
        with self._lock:
            self._working.clear()
            self._archival.clear()
    
    @property
    def working_count(self) -> int:
        """Number of entries in working memory."""
        with self._lock:
            return len(self._working)
    
    @property
    def archival_count(self) -> int:
        """Number of entries in archival storage."""
        with self._lock:
            return len(self._archival)
    
    @property
    def working_capacity(self) -> int:
        """Maximum capacity of working memory."""
        return self._working_capacity
    
    @property
    def archival_capacity(self) -> int:
        """Maximum capacity of archival storage."""
        return self._archival_capacity
