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

    def search_openalex(self, topic, from_date=None, limit=20, max_retries=3):
        """
        Searches OpenAlex for papers matching topic since from_date.
        Uses clean keyword search (search=) with date filtering and rate-limit backoff.
        """
        import time

        params = {
            "search": topic,
            "sort": "cited_by_count:desc",
            "per_page": limit
        }
        
        filters = []
        if from_date:
            filters.append(f"from_publication_date:{from_date}")
        if filters:
            params["filter"] = ",".join(filters)
            
        headers = {}
        if self.email:
            params["mailto"] = self.email

        logger.info(f"[Keyword Search] OpenAlex: search='{topic}', filter='{params.get('filter', 'none')}'")
        
        for attempt in range(max_retries):
            try:
                # Polite spacing between calls
                time.sleep(0.35)
                response = requests.get(self.base_url, params=params, headers=headers, timeout=30, verify=False)
                if response.status_code == 429:
                    wait_sec = (attempt + 1) * 1.5
                    logger.warning(f"OpenAlex 429 rate limit reached. Backing off for {wait_sec}s...")
                    time.sleep(wait_sec)
                    continue
                response.raise_for_status()
                data = response.json()
                results = data.get("results", [])
                logger.info(f"[Keyword Search] Found {len(results)} results for '{topic}'")
                return results
            except Exception as e:
                if attempt == max_retries - 1:
                    logger.error(f"OpenAlex keyword search failed for '{topic}': {e}")
                time.sleep(0.5)
        return []

    def expand_topics_with_llm(self, topic: str, llm=None) -> list:
        """
        Uses LLM to expand a research topic into 3-5 synonym / semantic search phrases.
        Falls back to [topic] if LLM is unavailable or fails.
        """
        if not topic or not isinstance(topic, str) or not topic.strip():
            return [topic] if topic else []

        expanded = [topic.strip()]
        
        prompt = (
            f"You are an academic literature search assistant. "
            f"Given the research topic: '{topic}', generate 3 to 4 synonymous or closely related academic search phrases in English for literature database querying.\n"
            f"Output MUST be a JSON array of strings only, e.g. [\"phrase1\", \"phrase2\", \"phrase3\"]. Do not include markdown code blocks or explanations."
        )

        try:
            raw_response = None
            if llm:
                if hasattr(llm, "invoke"):
                    res = llm.invoke(prompt)
                    raw_response = getattr(res, "content", str(res))
                elif hasattr(llm, "ainvoke"):
                    import asyncio
                    try:
                        res = asyncio.run(llm.ainvoke(prompt))
                    except RuntimeError:
                        # Event loop is already running
                        loop = asyncio.get_event_loop()
                        res = loop.run_until_complete(llm.ainvoke(prompt))
                    raw_response = getattr(res, "content", str(res))
            else:
                base_url = os.getenv("AGENT_BASE_URL")
                api_key = os.getenv("AGENT_API_KEY")
                model = os.getenv("AGENT_MODEL", "gpt-4o")

                if base_url and api_key:
                    url = f"{base_url.rstrip('/')}/chat/completions"
                    headers = {
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    }
                    payload = {
                        "model": model,
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": 0.3,
                        "max_tokens": 150,
                    }
                    resp = requests.post(url, json=payload, headers=headers, timeout=10, verify=False)
                    if resp.status_code == 200:
                        data = resp.json()
                        raw_response = data["choices"][0]["message"]["content"]

            if raw_response:
                clean_str = raw_response.strip()
                if clean_str.startswith("```"):
                    clean_str = clean_str.split("```")[1]
                    if clean_str.startswith("json"):
                        clean_str = clean_str[4:].strip()
                clean_str = clean_str.strip()
                
                parsed = json.loads(clean_str)
                if isinstance(parsed, list):
                    for item in parsed:
                        if isinstance(item, str) and item.strip() and item.strip() not in expanded:
                            expanded.append(item.strip())
                    logger.info(f"[Semantic Expansion] Topic '{topic}' expanded to {len(expanded)} queries: {expanded}")
        except Exception as e:
            logger.debug(f"[Semantic Expansion] LLM query expansion failed for '{topic}': {e}. Using original topic.")

        return expanded

    def get_incremental_papers(self, topic, interval_days=7, positive_keywords=None, negative_keywords=None, llm=None, enable_expansion=True):
        """
        Retrieves new papers that are NOT in history, incorporating resident preferences and LLM query expansion.
        
        Supports independent multi-topic search:
        - Splits multiple topics (by ';' or 'and') and queries them separately.
        - Positive keywords are queried as independent search queries, NOT blindly concatenated to topics.
        - Results are aggregated, deduplicated, and reranked based on resident positive preferences.
        """
        from_date = (datetime.now() - timedelta(days=interval_days)).strftime('%Y-%m-%d')
        
        # 1. Parse sub-topics
        sub_topics = self.split_topics(topic)
        if not sub_topics:
            sub_topics = [topic] if topic else []
        
        # 2. Build independent search queries pool
        search_queries = []
        for st in sub_topics:
            st_clean = st.strip()
            if not st_clean:
                continue
            if st_clean not in search_queries:
                search_queries.append(st_clean)
            
            # If compound topic contains ' and ', also index key constituent phrases
            if " and " in st_clean.lower():
                for sub in st_clean.split(" and "):
                    sub_c = sub.strip()
                    if len(sub_c) > 3 and sub_c not in search_queries:
                        search_queries.append(sub_c)
            
            # Expand sub-topics using LLM semantic expansion if enabled
            if enable_expansion:
                expanded = self.expand_topics_with_llm(st_clean, llm=llm)
                for eq in expanded:
                    if eq not in search_queries:
                        search_queries.append(eq)

        # 3. Add positive keywords as independent parallel queries
        if positive_keywords and isinstance(positive_keywords, list):
            for pk in positive_keywords:
                if pk and isinstance(pk, str):
                    pk_clean = pk.strip()
                    if pk_clean and len(pk_clean) > 2 and pk_clean not in search_queries:
                        search_queries.append(pk_clean)

        logger.info(f"[LiteratureWatcher] Searching with {len(search_queries)} independent queries: {search_queries}")

        # 4. Collect raw results across independent queries
        all_raw_results = []
        seen_ids = set()
        
        for q in search_queries:
            raw_results = self.search_openalex(q, from_date=from_date, limit=15)
            for raw in raw_results:
                raw_id = raw.get('id', '')
                if raw_id and raw_id not in seen_ids:
                    seen_ids.add(raw_id)
                    all_raw_results.append((q, raw))
        
        new_papers = []
        neg_kws = [kw.lower().strip() for kw in negative_keywords] if negative_keywords and isinstance(negative_keywords, list) else []
        pos_kws = [kw.lower().strip() for kw in positive_keywords] if positive_keywords and isinstance(positive_keywords, list) else []

        for matched_topic, raw in all_raw_results:
            primary_loc = raw.get('primary_location') or {}
            source_info = primary_loc.get('source') or {}
            ids_info = raw.get('ids') or {}
            author_list = raw.get('authorships') or raw.get('memberships') or []
            
            abstract_text = self._extract_abstract(raw)
            title_text = raw.get('title') or ''
            full_text_lower = f"{title_text} {abstract_text}".lower()

            # Filter out papers matching negative keywords
            if neg_kws:
                if any(neg_kw in full_text_lower for neg_kw in neg_kws if neg_kw):
                    logger.info(f"Filtering out paper '{title_text}' due to negative keyword match.")
                    continue

            # Calculate preference relevance score for reranking
            relevance_score = 0.0
            for pk in pos_kws:
                if pk and pk in full_text_lower:
                    relevance_score += 2.0
            for st in sub_topics:
                if st and st.lower() in full_text_lower:
                    relevance_score += 1.5
            relevance_score += min((raw.get('cited_by_count') or 0) * 0.1, 5.0)

            paper = {
                'id': raw.get('id', ''),
                'doi': raw.get('doi', '').replace('https://doi.org/', '') if raw.get('doi') else '',
                'title': title_text,
                'abstract': abstract_text,
                'publication_date': raw.get('publication_date', ''),
                'authors': ", ".join([
                    (a.get('author') or {}).get('display_name', '')
                    for a in author_list[:5]
                    if a and isinstance(a, dict)
                ]),
                'source': source_info.get('display_name', 'OpenAlex'),
                'url': raw.get('doi') or ids_info.get('mag', ''),
                'citations': raw.get('cited_by_count', 0),
                'topic': matched_topic,
                'relevance_score': round(relevance_score, 2),
            }

            if not self.history.is_duplicate(
                doi=paper['doi'], 
                title=paper['title'], 
                abstract=paper['abstract'],
                external_id=paper['id']
            ):
                new_papers.append(paper)

        # Sort candidates by relevance score and citations descending
        new_papers.sort(key=lambda p: (p.get('relevance_score', 0), p.get('citations', 0)), reverse=True)
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
