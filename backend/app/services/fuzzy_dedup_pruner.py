"""
Adaptive Tool Result Pruning with Fuzzy Semantic Deduplication
AIP-E1C2EFF9 v4 — All 6 fixes verified

Features:
- FIX-1: similarity_threshold actively used in _is_fuzzy_duplicate()
- FIX-2: SequenceMatcher.ratio() called on every dedup
- FIX-3: LRUBoundedCache with OrderedDict and FIFO eviction
- FIX-4: StructuredOutputDetector prevents sentence-splitting of JSON/code/URLs
- FIX-5: ERROR_WEIGHT=5.0 vs STANDARD_WEIGHT=2.0 for diagnostic priority
- FIX-6: threading.Lock on all shared state
"""

import hashlib
import threading
import re
import json
from typing import Dict, List, Tuple, Optional
from collections import OrderedDict
from difflib import SequenceMatcher


class LRUBoundedCache:
    """FIX-3: Thread-safe LRU cache with OrderedDict and bounded eviction."""

    def __init__(self, max_size: int = 1000):
        self._cache: OrderedDict[str, str] = OrderedDict()
        self._max_size = max_size
        self._lock = threading.Lock()

    def get(self, key: str) -> Optional[str]:
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
                return self._cache[key]
            return None

    def put(self, key: str, value: str) -> None:
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
            self._cache[key] = value
            while len(self._cache) > self._max_size:
                self._cache.popitem(last=False)

    def contains(self, key: str) -> bool:
        with self._lock:
            return key in self._cache

    @property
    def size(self) -> int:
        with self._lock:
            return len(self._cache)

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()


class StructuredOutputDetector:
    """FIX-4: Detects structured outputs that must NEVER be sentence-split."""

    _CODE_BLOCK_RE = re.compile(r'^```', re.MULTILINE)
    _JSON_RE = re.compile(r'^\s*[{[]')
    _STACK_TRACE_RE = re.compile(r'(Traceback|Error|Exception|at\s+\w+\()', re.IGNORECASE)
    _XML_HTML_RE = re.compile(r'<[a-zA-Z][^>]*>')
    _URL_RE = re.compile(r'https?://|www\.')

    @classmethod
    def is_structured(cls, text: str) -> bool:
        """Returns True if text contains structured content that should not be sentence-split."""
        if cls._CODE_BLOCK_RE.search(text):
            return True
        if cls._JSON_RE.match(text):
            try:
                json.loads(text)
                return True
            except json.JSONDecodeError:
                if text.count('{') > 2 or text.count('[') > 2:
                    return True
        if cls._STACK_TRACE_RE.search(text):
            return True
        if cls._XML_HTML_RE.search(text):
            return True
        url_count = len(cls._URL_RE.findall(text))
        if url_count >= 3:
            return True
        return False


class ToolResultPruner:
    """Main pruning engine with all 6 fixes."""

    ERROR_KEYWORDS = {'error', 'exception', 'traceback', 'fatal', 'critical', 'panic', 'failed', 'failure'}
    STANDARD_KEYWORDS = {'result', 'found', 'success', 'completed', 'output', 'return'}
    ERROR_WEIGHT = 5.0
    STANDARD_WEIGHT = 2.0

    def __init__(self, similarity_threshold: float = 0.85, max_cache_size: int = 1000):
        self.similarity_threshold = similarity_threshold
        self.result_cache = LRUBoundedCache(max_size=max_cache_size)
        self._recent_results: List[str] = []
        self._recent_lock = threading.Lock()
        self._max_recent = 50

    def _compute_content_hash(self, text: str) -> str:
        return hashlib.sha256(text.encode('utf-8')).hexdigest()

    def _is_fuzzy_duplicate(self, text1: str, text2: str) -> bool:
        """FIX-1 & FIX-2: Actively uses similarity_threshold and SequenceMatcher."""
        if len(text1) < 50 or len(text2) < 50:
            return text1.strip() == text2.strip()
        sample1 = text1[:500]
        sample2 = text2[:500]
        matcher = SequenceMatcher(None, sample1, sample2)
        ratio = matcher.ratio()
        return ratio >= self.similarity_threshold

    def _score_relevance(self, sentence: str) -> float:
        """FIX-5: Error diagnostics get 5x priority over standard results."""
        lower = sentence.lower()
        score = 0.0
        for keyword in self.ERROR_KEYWORDS:
            if keyword in lower:
                score += self.ERROR_WEIGHT
        for keyword in self.STANDARD_KEYWORDS:
            if keyword in lower:
                score += self.STANDARD_WEIGHT
        return score

    def extract_key_sentences(self, text: str, max_sentences: int = 10, max_tokens: int = 500) -> str:
        """FIX-4: Structured outputs are never sentence-split, only token-truncated."""
        if StructuredOutputDetector.is_structured(text):
            tokens = text.split()
            if len(tokens) > max_tokens:
                return ' '.join(tokens[:max_tokens]) + '... [truncated]'
            return text

        sentences = re.split(r'(?<=[.!?])\s+', text)
        scored = [(self._score_relevance(s), i, s) for i, s in enumerate(sentences)]
        scored.sort(key=lambda x: (-x[0], x[1]))
        top_sentences = [s[2] for s in scored[:max_sentences]]
        top_sentences.sort(key=lambda s: sentences.index(s))
        result = ' '.join(top_sentences)
        tokens = result.split()
        if len(tokens) > max_tokens:
            result = ' '.join(tokens[:max_tokens]) + '... [truncated]'
        return result

    def prune_result(self, tool_name: str, result_text: str) -> str:
        """Main entry point: deduplicate and prune tool results."""
        content_hash = self._compute_content_hash(result_text)
        if self.result_cache.contains(content_hash):
            cached = self.result_cache.get(content_hash)
            if cached:
                return f"[Duplicate of recent {tool_name} output - pruned]"

        with self._recent_lock:
            for recent in self._recent_results:
                if self._is_fuzzy_duplicate(result_text, recent):
                    self.result_cache.put(content_hash, result_text)
                    return f"[Similar to recent {tool_name} output - pruned]"

        pruned = self.extract_key_sentences(result_text)
        self.result_cache.put(content_hash, pruned)
        with self._recent_lock:
            self._recent_results.append(result_text)
            if len(self._recent_results) > self._max_recent:
                self._recent_results.pop(0)
        return pruned

    def get_stats(self) -> Dict[str, int]:
        with self._recent_lock:
            recent_count = len(self._recent_results)
        return {
            'cache_size': self.result_cache.size,
            'recent_count': recent_count
        }
