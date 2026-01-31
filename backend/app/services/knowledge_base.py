import logging
import json
import httpx
import xml.etree.ElementTree as ET
import urllib.parse
from typing import List, Dict, Any
from datetime import datetime

logger = logging.getLogger(__name__)

class WebResearcher:
    """
    Fetches real research papers from ArXiv and BioRxiv.
    """
    def search(self, query: str) -> List[Dict[str, str]]:
        # Handle user's request for space/AND support
        # If no explicit operators (AND, OR, ANDNOT) are found, assume intersection (AND)
        if not any(op in query for op in ["AND", "OR", "ANDNOT"]):
             # Replace spaces with ' AND ' to ensure all terms must be present
             # Collapsing multiple spaces first
             import re
             formatted_query = re.sub(r'\s+', ' AND ', query.strip())
             # Wrap in parens just in case
             formatted_query = f"({formatted_query})"
        else:
             formatted_query = f"({query})"
             
        encoded_query = urllib.parse.quote(formatted_query)
        logger.info(f"Searching web for: {query} (Encoded: {encoded_query})")
        print(f"\n[Search Run] Query: {query}")
        results = []
        
        # 1. ArXiv Search
        try:
            # Fetch 100 results and sort by relevance to get "importance"
            arxiv_url = (
                f"https://export.arxiv.org/api/query?"
                f"search_query=all:{encoded_query}&"
                f"start=0&max_results=100&"
                f"sortBy=relevance&sortOrder=descending"
            )
            response = httpx.get(arxiv_url, timeout=15.0)
            print(f"ArXiv Status: {response.status_code}")
            if response.status_code == 200:
                root = ET.fromstring(response.text)
                ns = {'atom': 'http://www.w3.org/2005/Atom'}
                entries = root.findall('atom:entry', ns)
                print(f"ArXiv Entries Found: {len(entries)}")
                for entry in entries:
                    title_elem = entry.find('atom:title', ns)
                    summary_elem = entry.find('atom:summary', ns)
                    id_elem = entry.find('atom:id', ns)
                    published_elem = entry.find('atom:published', ns)
                    
                    if title_elem is not None and summary_elem is not None:
                        title = title_elem.text.strip().replace('\n', ' ')
                        summary = summary_elem.text.strip().replace('\n', ' ')
                        paper_id = id_elem.text if id_elem is not None else "Unknown ID"
                        published = published_elem.text if published_elem is not None else ""
                        
                        results.append({
                            "title": title,
                            "abstract": summary, # Keep full abstract for translation
                            "source": paper_id,
                            "published": published
                        })
        except Exception as e:
            logger.error(f"ArXiv search failed: {e}")
            print(f"ArXiv Error: {e}")

        # 2. BioRxiv Search
        try:
            today = datetime.now().strftime("%Y-%m-%d")
            biorxiv_url = f"https://api.biorxiv.org/details/biorxiv/2025-01-01/{today}/0"
            resp = httpx.get(biorxiv_url, timeout=12.0)
            print(f"BioRxiv Status: {resp.status_code}")
            if resp.status_code == 200:
                data = resp.json()
                if "collection" in data and isinstance(data["collection"], list):
                    q_lower = query.lower()
                    count = 0
                    for item in data["collection"]:
                        if q_lower in item["title"].lower() or q_lower in item["abstract"].lower():
                            results.append({
                                "title": item["title"],
                                "abstract": item["abstract"][:300] + "...",
                                "source": f"BioRxiv ({item['doi']})"
                            })
                            count += 1
                            if count >= 2: break
                    print(f"BioRxiv Relevant Matches: {count}")
        except Exception as e:
            logger.error(f"BioRxiv search failed: {e}")
            print(f"BioRxiv Error: {e}")

        return results

class KnowledgeBase:
    """
    Local Retrieval System (RAG).
    Indexes local history (Memory) and public archives (Blockchain).
    """
    def __init__(self):
        self.documents: List[Dict] = []
        self.web_researcher = WebResearcher()

    def ingest_history(self, history: List[Dict]):
        self.documents = []
        for msg in history:
            text = msg.get("content", "")
            if text:
                self.documents.append({
                    "content": text,
                    "source": "resident_history",
                    "timestamp": msg.get("timestamp"),
                    "metadata": {"type": msg.get("type", "chat")}
                })
        logger.info(f"Ingested {len(history)} history items into Knowledge Base")

    def ingest_archives(self, chain_data: List[Dict]):
        count = 0
        for block in chain_data:
            data = block.get("data", {})
            content = f"Block {block.get('index')} Summary: {json.dumps(data)}"
            self.documents.append({
                "content": content,
                "source": "community_archive",
                "timestamp": block.get("timestamp"),
                "metadata": {"block_hash": block.get("hash")}
            })
            count += 1
        logger.info(f"Ingested {count} blocks into Knowledge Base")

    def retrieve_context(self, query: str, limit: int = 3) -> str:
        query_terms = set(query.lower().split())
        scored_docs = []
        for doc in self.documents:
            content = doc["content"].lower()
            score = sum(1 for term in query_terms if term in content)
            if score > 0:
                scored_docs.append((score, doc))
        scored_docs.sort(key=lambda x: (x[0], x[1].get("timestamp", "")), reverse=True)
        top_docs = scored_docs[:limit]
        context_parts = []
        for score, doc in top_docs:
            source = doc["source"]
            text = doc["content"]
            context_parts.append(f"[{source.upper()}] {text}")
        return "\n\n".join(context_parts) if context_parts else "No relevant local context found."

    def search_web_and_context(self, query: str) -> str:
        local_context = self.retrieve_context(query)
        web_results = self.web_researcher.search(query)
        
        web_text = ""
        if web_results:
            for res in web_results:
                web_text += f"Title: {res['title']}\nAbstract: {res['abstract']}\nSource: {res['source']}\n\n"
        else:
            web_text = "No recent research found for this topic."
            
        return f"""
=== Local Knowledge ===
{local_context}

=== Web Research ===
{web_text}
"""

knowledge_base = KnowledgeBase()
