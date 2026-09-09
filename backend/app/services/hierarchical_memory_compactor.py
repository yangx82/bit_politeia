"""HierarchicalMemoryCompactor with Semantic Importance Scoring for Context Distillation."""
import hashlib
import math
import pickle
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field


@dataclass(frozen=True)
class MemoryEntry:
    content: str
    timestamp: float
    role: str
    metadata: dict = field(default_factory=dict)


@dataclass
class CompactedTier:
    hot: list
    warm: list
    cold: str


GOVERNANCE_KEYWORDS = {'election', 'proposal', 'vote', 'ballot', 'governance', 'rule', 'core_node', 'AIP'}
ROLE_WEIGHTS = {'resident': 1.5, 'agent': 1.0, 'system': 0.7}


class HierarchicalMemoryCompactor:
    def __init__(
        self,
        hot_window: int = 10,
        warm_window: int = 30,
        cold_threshold: int = 50,
        decay_factor: float = 0.99,
        compaction_threshold: int = 10,
        **kwargs,
    ):
        if not (0 < hot_window <= warm_window <= cold_threshold <= 500):
            raise ValueError(f'Invalid windows: hot={hot_window}, warm={warm_window}, cold={cold_threshold}')
        self._hot = hot_window
        self._warm = warm_window
        self._cold = cold_threshold
        self._decay_factor = decay_factor
        self._compaction_threshold = compaction_threshold
        self._lock = threading.Lock()
        self._cache: OrderedDict = OrderedDict()

    def score_importance(self, entry: MemoryEntry, now: float) -> float:
        decay_rate = -math.log(self._decay_factor) if (0.0 < self._decay_factor < 1.0) else 0.001
        recency = math.exp(-decay_rate * (now - entry.timestamp))
        role_w = ROLE_WEIGHTS.get(entry.role, 0.7)
        kw_boost = 0.3 * sum(1 for kw in GOVERNANCE_KEYWORDS if kw in entry.content.lower())
        meta_boost = 0.5 if entry.metadata.get('governance') else 0.0
        return round(max(0.0, min(5.0, recency * role_w + kw_boost + meta_boost)), 3)

    def compact(self, entries: list) -> CompactedTier:
        key = hashlib.md5(pickle.dumps([(e.content, e.timestamp) for e in entries])).hexdigest()[:12]
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
                return self._cache[key]
            sorted_e = sorted(entries, key=lambda e: e.timestamp, reverse=True)
            hot = sorted_e[:self._hot]
            warm_cands = sorted_e[self._hot:self._warm]
            cold_cands = sorted_e[self._warm:]
            warm = [f'[{e.role}] {e.content.split(". ")[0]}' for e in warm_cands]
            cold_sents = '. '.join(e.content.split('. ')[0] for e in cold_cands)
            cold = f'[Distilled] {cold_sents[:500]}' if cold_sents else ''
            tier = CompactedTier(hot=hot, warm=warm, cold=cold)
            self._cache[key] = tier
            if len(self._cache) > 64:
                self._cache.popitem(last=False)
            return tier

    def prune_by_threshold(self, entries: list, min_score: float = 1.0) -> list:
        if not (0.0 <= min_score <= 5.0):
            raise ValueError(f'min_score must be in [0.0, 5.0], got {min_score}')
        now = time.time()
        with self._lock:
            return [e for e in entries
                    if e.metadata.get('governance') or self.score_importance(e, now) >= min_score]


# --- Integration point for context_manager.py ---

def get_compacted_context(conversation_history: list, max_tokens_estimate: int = 4000) -> str:
    compactor = HierarchicalMemoryCompactor(hot_window=10, warm_window=30)
    tier = compactor.compact(conversation_history)
    parts = []
    if tier.cold:
        parts.append(f'### Distilled History\n{tier.cold}')
    if tier.warm:
        parts.append('### Recent Context\n' + '\n'.join(tier.warm))
    parts.append('### Active Conversation\n' + '\n'.join(e.content for e in tier.hot))
    return '\n\n'.join(parts)


# --- Unit Tests ---

def test_score_importance_governance_boost():
    entry = MemoryEntry(content='New election proposed', timestamp=time.time(),
                        role='system', metadata={'governance': True})
    compactor = HierarchicalMemoryCompactor()
    score = compactor.score_importance(entry, time.time())
    assert score >= 1.5, f'Governance entry should score >= 1.5, got {score}'


def test_compact_respects_hot_window():
    entries = [MemoryEntry(content=f'msg {i}', timestamp=float(i),
                           role='agent', metadata={}) for i in range(25)]
    compactor = HierarchicalMemoryCompactor(hot_window=10, warm_window=20)
    tier = compactor.compact(entries)
    assert len(tier.hot) == 10, f'Expected 10 hot entries, got {len(tier.hot)}'
    assert len(tier.warm) == 10, f'Expected 10 warm entries, got {len(tier.warm)}'
    assert len(tier.cold) > 0, 'Cold tier should contain distilled summary'


def test_prune_preserves_governance_entries():
    low = MemoryEntry(content='hello', timestamp=0.0, role='agent', metadata={})
    gov = MemoryEntry(content='vote', timestamp=0.0, role='system', metadata={'governance': True})
    compactor = HierarchicalMemoryCompactor()
    result = compactor.prune_by_threshold([low, gov], min_score=3.0)
    assert gov in result, 'Governance entries must survive pruning regardless of score'
    assert low not in result, 'Low-score non-governance entries should be pruned'


if __name__ == '__main__':
    test_score_importance_governance_boost()
    test_compact_respects_hot_window()
    test_prune_preserves_governance_entries()
    print('All tests passed.')
