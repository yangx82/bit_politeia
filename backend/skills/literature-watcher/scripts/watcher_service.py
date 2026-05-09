import requests
import os
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from history_manager import HistoryManager

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

    def search_openalex(self, topic, from_date=None, limit=20):
        """
        Searches OpenAlex for papers matching topic since from_date.
        """
        params = {
            "filter": f"display_name.search:{topic}",
            "sort": "cited_by_count:desc",
            "per_page": limit
        }
        
        if from_date:
            params["filter"] += f",from_publication_date:{from_date}"
            
        headers = {}
        if self.email:
            params["mailto"] = self.email
            logger.info(f"Using polite pool with email: {self.email}")

        logger.info(f"Searching OpenAlex for '{topic}' since {from_date or 'beginning of time'}...")
        
        try:
            response = requests.get(self.base_url, params=params, headers=headers, timeout=30)
            response.raise_for_status()
            data = response.json()
            return data.get("results", [])
        except Exception as e:
            logger.error(f"OpenAlex search failed: {e}")
            return []

    def get_incremental_papers(self, topic, interval_days=7):
        """
        Retrieves new papers that are NOT in the history.
        """
        from_date = (datetime.now() - timedelta(days=interval_days)).strftime('%Y-%m-%d')
        raw_results = self.search_openalex(topic, from_date=from_date)
        
        new_papers = []
        for raw in raw_results:
            paper = {
                'id': raw.get('id', ''),
                'doi': raw.get('doi', '').replace('https://doi.org/', '') if raw.get('doi') else '',
                'title': raw.get('title', ''),
                'abstract': self._extract_abstract(raw),
                'publication_date': raw.get('publication_date', ''),
                'authors': ", ".join([a.get('author', {}).get('display_name', '') for a in raw.get('memberships', [])[:5]]),
                'source': raw.get('primary_location', {}).get('source', {}).get('display_name', 'OpenAlex'),
                'url': raw.get('doi', raw.get('ids', {}).get('mag', '')),
                'citations': raw.get('cited_by_count', 0),
                'topic': topic
            }
            
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
    papers = service.get_incremental_papers("decentralized AI", interval_days=30)
    print(f"Found {len(papers)} new papers.")
    for p in papers[:3]:
        print(f"- {p['title']} ({p['publication_date']})")
