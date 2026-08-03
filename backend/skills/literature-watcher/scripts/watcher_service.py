import requests
import os
import json
import logging
import urllib3
from datetime import datetime, timedelta
from pathlib import Path
from history_manager import HistoryManager

# 禁用 SSL 警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Try to load .env file from multiple potential locations
def _load_env_file():
    """Load .env file from current directory, parent directories, or package directory.
    Supports manual parsing if python-dotenv is not installed.
    """
    def parse_env_content(content):
        """Simple manual parser for .env files."""
        for line in content.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip().strip("'").strip('"')
                if key and key not in os.environ:
                    os.environ[key] = value

    try:
        from dotenv import load_dotenv
        has_dotenv = True
    except ImportError:
        has_dotenv = False

    # Potential locations to check
    search_dirs = [Path.cwd()]
    
    # Add parent directories of CWD
    cwd = Path.cwd()
    for _ in range(5):
        cwd = cwd.parent
        search_dirs.append(cwd)
        if cwd == cwd.parent: break

    # Add parent directories of the script itself
    script_dir = Path(__file__).resolve().parent
    for _ in range(5):
        search_dirs.append(script_dir)
        script_dir = script_dir.parent
        if script_dir == script_dir.parent:
            break

    return False


class WatcherService:
    def __init__(self):
        # Load env vars first
        _load_env_file()
        self.history = HistoryManager()
        self.email = os.getenv("OPENALEX_EMAIL")
        self.base_url = "https://api.openalex.org/works"

    @staticmethod
    def split_topics(research_field: str) -> list:
        """Split research field string into individual topics.
        
        Supports separators: ';' (primary), ',' (secondary for simple fields)
        Returns cleaned, non-empty topic list.
        """
        if not research_field:
            return []
        # Split by semicolon (primary separator for AGENT_RESEARCH_FIELD)
        raw_topics = research_field.split(';')
        topics = []
        for t in raw_topics:
            t = t.strip()
            if t and len(t) > 2:
                topics.append(t)
        return topics

    # 主题到 OpenAlex 概念的映射（用于精确过滤）
    TOPIC_CONCEPTS = {
        # 神经科学/脑科学相关概念 ID
        "neuroscience": "C154945302",  # Neuroscience
        "brain": "C154945302",
        "cognition": "C2771054173",  # Cognitive science
        "instinct": "C154945302",  # 归入神经科学
        
        # AI/区块链相关概念 ID
        "blockchain": "C208177563",  # Blockchain
        "ai governance": "C154945302",  # 使用通用 AI 概念
    }
    
    # 主题到 OpenAlex 主题的映射（更精确）
    TOPIC_DOMAINS = {
        "neural mechanism": ["T27704", "T27671"],  # Neuroscience, Cognitive Neuroscience
        "instinct": ["T27704"],  # Neuroscience
        "cognition": ["T27671", "T27704"],  # Cognitive Neuroscience, Neuroscience
        "blockchain": ["T10101"],  # Blockchain (如果存在)
        "ai governance": ["T11603"],  # Artificial Intelligence
    }

    def search_openalex(self, topic, from_date=None, limit=20):
        """
        Searches OpenAlex for papers matching topic since from_date.
        
        Uses KEYWORD SEARCH (search=) with domain filtering (filter=) for precise results.
        This avoids semantic search returning irrelevant papers
        (e.g., AI papers for "neural" queries).
        
        OpenAlex API:
        - search=: Full-text keyword search
        - filter=: Domain/concept filtering
        """
        # 使用 search 参数进行关键词搜索
        params = {
            "search": topic,  # 全文关键词搜索
            "sort": "cited_by_count:desc",
            "per_page": limit
        }
        
        # 构建 filter 条件
        filters = []
        
        # 添加领域过滤（根据主题自动选择）
        domain_filter = self._get_domain_filter(topic)
        if domain_filter:
            filters.append(domain_filter)
        
        # 添加日期过滤
        if from_date:
            filters.append(f"from_publication_date:{from_date}")
        
        # 组合所有过滤条件
        if filters:
            params["filter"] = ",".join(filters)
            
        headers = {}
        if self.email:
            params["mailto"] = self.email
            logger.info(f"Using polite pool with email: {self.email}")

        logger.info(f"[Keyword Search] OpenAlex: search='{topic}', filter='{params.get('filter', 'none')}'")
        
        try:
            response = requests.get(self.base_url, params=params, headers=headers, timeout=30, verify=False)
            response.raise_for_status()
            data = response.json()
            results = data.get("results", [])
            logger.info(f"[Keyword Search] Found {len(results)} results for '{topic}'")
            return results
        except Exception as e:
            logger.error(f"OpenAlex keyword search failed: {e}")
            # 降级到语义搜索
            logger.info("Falling back to semantic search...")
            return self._semantic_search_fallback(topic, from_date, limit)
    
    def _get_domain_filter(self, topic: str) -> str:
        """根据主题获取领域过滤条件"""
        topic_lower = topic.lower()
        
        # 检查是否匹配神经科学相关主题
        neuro_keywords = ["neural", "brain", "cognition", "instinct", "neuroscience"]
        if any(kw in topic_lower for kw in neuro_keywords):
            # 使用 primary_topic.id 过滤到神经科学领域
            # T10077: Neuroscience and Neuropharmacology Research
            # T11601: Neuroscience and Neural Engineering
            # T13106: Neuroscience, Education and Cognitive Function
            return "primary_topic.id:T10077|T11601|T13106"
        
        # 检查是否匹配区块链主题
        if "blockchain" in topic_lower:
            return "concepts.id:C208177563"  # Blockchain
        
        # 检查是否匹配 AI 治理主题
        if "ai" in topic_lower or "governance" in topic_lower:
            return "concepts.id:C154945302"  # AI 相关
        
        return ""
    
    def _semantic_search_fallback(self, topic, from_date=None, limit=20):
        """语义搜索降级方案"""
        params = {
            "search": topic,
            "sort": "cited_by_count:desc",
            "per_page": limit
        }
        
        if from_date:
            params["filter"] = f"from_publication_date:{from_date}"
            
        headers = {}
        if self.email:
            params["mailto"] = self.email

        try:
            response = requests.get(self.base_url, params=params, headers=headers, timeout=30, verify=False)
            response.raise_for_status()
            data = response.json()
            return data.get("results", [])
        except Exception as e:
            logger.error(f"OpenAlex semantic search fallback failed: {e}")
            return []

    def get_incremental_papers(self, topic, interval_days=7, positive_keywords=None, negative_keywords=None):
        """
        Retrieves new papers that are NOT in history, incorporating resident preferences.
        
        Supports multi-topic search: if topic contains ';' separators, each sub-topic
        is searched independently and results are merged with deduplication.
        """
        from_date = (datetime.now() - timedelta(days=interval_days)).strftime('%Y-%m-%d')
        
        # Split topic into sub-topics if multiple are provided
        sub_topics = self.split_topics(topic)
        if not sub_topics:
            sub_topics = [topic]
        
        # Collect all raw results across sub-topics
        all_raw_results = []
        seen_ids = set()  # Deduplicate across sub-topics
        
        for sub_topic in sub_topics:
            # Expand search topic with positive keywords if available
            search_topic = sub_topic
            if positive_keywords and isinstance(positive_keywords, list):
                valid_pos = [kw.strip() for kw in positive_keywords if kw and isinstance(kw, str)]
                if valid_pos:
                    search_topic = f"{sub_topic} {' '.join(valid_pos[:3])}"

            raw_results = self.search_openalex(search_topic, from_date=from_date)
            
            for raw in raw_results:
                raw_id = raw.get('id', '')
                if raw_id and raw_id not in seen_ids:
                    seen_ids.add(raw_id)
                    all_raw_results.append((sub_topic, raw))
        
        new_papers = []
        neg_kws = [kw.lower().strip() for kw in negative_keywords] if negative_keywords and isinstance(negative_keywords, list) else []

        for matched_topic, raw in all_raw_results:
            # Safe access helpers for nested None values
            primary_loc = raw.get('primary_location') or {}
            source_info = primary_loc.get('source') or {}
            ids_info = raw.get('ids') or {}
            author_list = raw.get('authorships') or raw.get('memberships') or []

            paper = {
                'id': raw.get('id', ''),
                'doi': raw.get('doi', '').replace('https://doi.org/', '') if raw.get('doi') else '',
                'title': raw.get('title', ''),
                'abstract': self._extract_abstract(raw),
                'publication_date': raw.get('publication_date', ''),
                'authors': ", ".join([
                    (a.get('author') or {}).get('display_name', '')
                    for a in author_list[:5]
                    if a and isinstance(a, dict)
                ]),
                'source': source_info.get('display_name', 'OpenAlex'),
                'url': raw.get('doi') or ids_info.get('mag', ''),
                'citations': raw.get('cited_by_count', 0),
                'topic': matched_topic
            }

            # Filter out papers matching negative keywords
            if neg_kws:
                text_content = f"{paper['title']} {paper['abstract']}".lower()
                if any(neg_kw in text_content for neg_kw in neg_kws if neg_kw):
                    logger.info(f"Filtering out paper '{paper['title']}' due to negative keyword match.")
                    continue
            
            if not self.history.is_duplicate(
                doi=paper['doi'], 
                title=paper['title'], 
                abstract=paper['abstract'],
                external_id=paper['id']
            ):
                new_papers.append(paper)
                
        return new_papers

    def _extract_abstract(self, raw_work):
        """OpenAlex uses an inverted index for abstracts."""
        index = raw_work.get('abstract_inverted_index')
        if not index:
            return ""
        
        # Reconstruct abstract
        word_list = []
        for word, positions in index.items():
            for pos in positions:
                word_list.append((pos, word))
        
        word_list.sort()
        return " ".join([w[1] for w in word_list])

    def save_to_history(self, papers):
        for paper in papers:
            self.history.add_paper(paper)

if __name__ == "__main__":
    service = WatcherService()
    
    # Get research topics from environment variable
    research_field = os.getenv("AGENT_RESEARCH_FIELD", "decentralized AI")
    print(f"🔍 Research Field: {research_field}")
    
    # Split into individual topics
    topics = service.split_topics(research_field)
    print(f"📋 Topics ({len(topics)}): {topics}")
    print()
    
    # Search for papers across all topics
    papers = service.get_incremental_papers(research_field, interval_days=30)
    print(f"Found {len(papers)} new papers.")
    for p in papers[:3]:
        print(f"- {p['title']} ({p['publication_date']})")
    
    # 保存到数据库
    if papers:
        service.save_to_history(papers)
        print(f"\n✅ 已保存 {len(papers)} 篇论文到数据库 (watcher_history.db)")
    else:
        print("\n⚠️ 没有找到新论文")
