"""HierarchicalMemoryCompactor with Semantic Importance Scoring & Lexical Distillation."""
import hashlib
import math
import pickle
import re
import threading
import time
from collections import Counter, OrderedDict
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
RESEARCH_KEYWORDS = {
    'arxiv', 'doi', 'benchmark', 'dataset', 'experiment', 'hypothesis',
    'ablation', 'baseline', 'metric', 'evaluation', 'paper', 'citation'
}
ROLE_WEIGHTS = {'resident': 1.5, 'agent': 1.0, 'system': 0.7}

ARXIV_DOI_REGEX = re.compile(
    r'(arxiv:\d+\.\d+|10\.\d{4,9}/[-._;()/:A-Z0-9]+|https?://(?:arxiv\.org|doi\.org)/\S+)',
    re.IGNORECASE,
)

STOP_WORDS = {
    'the', 'a', 'an', 'in', 'on', 'at', 'to', 'for', 'of', 'and', 'or', 'is', 'are', 'was',
    'were', 'it', 'this', 'that', 'with', 'as', 'by', 'from', 'be', 'have', 'has', 'had',
    'not', 'but', 'what', 'which', 'who', 'whom', 'their', 'there', 'they', 'we', 'you',
    'our', 'my', 'your', 'i', 'me', 'us', 'him', 'her', 'his', 'its', 'about', 'can', 'will'
}


def tokenize_words(text: str) -> list[str]:
    """Tokenize lowercase alphanumeric words of length >= 2."""
    return re.findall(r'[a-zA-Z0-9_]{2,}', (text or "").lower())


def lexical_cosine_similarity(text1: str, text2: str) -> float:
    """
    Computes pure-Python lexical cosine similarity between two text strings.
    Zero external dependencies (Aarron / AIP-9778-97D267 Distillation).
    """
    tokens1 = tokenize_words(text1)
    tokens2 = tokenize_words(text2)
    if not tokens1 or not tokens2:
        return 0.0
    vec1 = Counter(tokens1)
    vec2 = Counter(tokens2)
    intersection = set(vec1.keys()) & set(vec2.keys())
    dot_product = sum(vec1[k] * vec2[k] for k in intersection)
    mag1 = math.sqrt(sum(v * v for v in vec1.values()))
    mag2 = math.sqrt(sum(v * v for v in vec2.values()))
    if mag1 == 0.0 or mag2 == 0.0:
        return 0.0
    return round(dot_product / (mag1 * mag2), 4)


def extract_key_topics(entries: list, top_k: int = 5) -> list[str]:
    """Extract top-k non-stopwords keywords across memory entries."""
    freq = Counter()
    for e in entries:
        content = getattr(e, "content", str(e))
        tokens = tokenize_words(content)
        for t in tokens:
            if t not in STOP_WORDS and len(t) > 2:
                freq[t] += 1
    return [w for w, _ in freq.most_common(top_k)]


def cluster_by_lexical_similarity(entries: list, threshold: float = 0.25) -> list[list[MemoryEntry]]:
    """
    Groups memory entries into topic clusters based on lexical cosine similarity.
    Preserves chronological / relative order within clusters.
    """
    if not entries:
        return []
    clusters: list[list[MemoryEntry]] = []
    for entry in entries:
        best_cluster = None
        best_sim = -1.0
        for cluster in clusters:
            sim = lexical_cosine_similarity(entry.content, cluster[0].content)
            if sim > best_sim:
                best_sim = sim
                best_cluster = cluster
        if best_cluster is not None and best_sim >= threshold:
            best_cluster.append(entry)
        else:
            clusters.append([entry])
    return clusters


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

        # Component 3: Research Semantic Survival Boost (Bit Plato / AIP-5A40-798604 Distillation)
        is_research = (
            bool(entry.metadata.get('research'))
            or bool(ARXIV_DOI_REGEX.search(entry.content))
        )
        research_boost = 0.5 if is_research else 0.0
        res_kw_boost = 0.2 * min(2, sum(1 for kw in RESEARCH_KEYWORDS if kw in entry.content.lower()))

        raw_score = recency * role_w + kw_boost + meta_boost + research_boost + res_kw_boost
        return round(max(0.0, min(5.0, raw_score)), 3)

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

            # Warm tier: cluster by lexical similarity to aggregate related discussions
            if warm_cands:
                clusters = cluster_by_lexical_similarity(warm_cands, threshold=0.25)
                warm = []
                for cl in clusters:
                    for e in cl:
                        warm.append(f'[{e.role}] {e.content.split(". ")[0]}')
            else:
                warm = []

            # Cold tier: extract topic keywords and produce distilled summary
            if cold_cands:
                topics = extract_key_topics(cold_cands, top_k=5)
                topic_str = f'[Topics: {", ".join(topics)}] ' if topics else ''
                cold_sents = '. '.join(e.content.split('. ')[0] for e in cold_cands)
                cold = f'[Distilled] {topic_str}{cold_sents[:500]}'
            else:
                cold = ''

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
            survivors = []
            for e in entries:
                is_gov = bool(e.metadata.get('governance'))
                is_res = bool(e.metadata.get('research')) or bool(ARXIV_DOI_REGEX.search(e.content))
                if is_gov or is_res or self.score_importance(e, now) >= min_score:
                    survivors.append(e)
            return survivors


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


def test_score_importance_research_boost():
    entry = MemoryEntry(content='Referencing arXiv:2304.03442 generative agents experiment baseline',
                        timestamp=time.time(), role='resident', metadata={})
    compactor = HierarchicalMemoryCompactor()
    score = compactor.score_importance(entry, time.time())
    assert score >= 2.0, f'Research entry should score >= 2.0, got {score}'


def test_lexical_cosine_similarity():
    sim_high = lexical_cosine_similarity('machine learning models', 'deep machine learning')
    sim_none = lexical_cosine_similarity('apple banana orange', 'quantum gravity physics')
    assert sim_high > 0.4, f'Expected similarity > 0.4, got {sim_high}'
    assert sim_none == 0.0, f'Expected similarity 0.0, got {sim_none}'


def test_compact_respects_hot_window():
    entries = [MemoryEntry(content=f'msg {i}', timestamp=float(i),
                           role='agent', metadata={}) for i in range(25)]
    compactor = HierarchicalMemoryCompactor(hot_window=10, warm_window=20)
    tier = compactor.compact(entries)
    assert len(tier.hot) == 10, f'Expected 10 hot entries, got {len(tier.hot)}'
    assert len(tier.warm) == 10, f'Expected 10 warm entries, got {len(tier.warm)}'
    assert len(tier.cold) > 0, 'Cold tier should contain distilled summary'


def test_prune_preserves_governance_and_research_entries():
    low = MemoryEntry(content='hello world', timestamp=0.0, role='agent', metadata={})
    gov = MemoryEntry(content='vote', timestamp=0.0, role='system', metadata={'governance': True})
    res = MemoryEntry(content='benchmark result at 10.1145/3318464.3389700', timestamp=0.0, role='resident', metadata={})
    compactor = HierarchicalMemoryCompactor()
    result = compactor.prune_by_threshold([low, gov, res], min_score=3.0)
    assert gov in result, 'Governance entries must survive pruning regardless of score'
    assert res in result, 'Research entries must survive pruning regardless of score'
    assert low not in result, 'Low-score generic entries should be pruned'

