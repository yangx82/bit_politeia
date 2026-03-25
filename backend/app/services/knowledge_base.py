import logging
import json
import os
import time
from typing import List, Dict, Any
from datetime import datetime, timezone
import httpx
import xml.etree.ElementTree as ET
import re
import urllib.parse

logger = logging.getLogger(__name__)


class WebResearcher:
    """
    Simulates a web search tool.
    In production, this would use Tavily, Bing, or Google Search API.
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
        search_results = []
        
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
                arxiv_entries = root.findall('atom:entry', ns)
                print(f"ArXiv Entries Found: {len(arxiv_entries)}")
                for entry in arxiv_entries:
                    title_elem = entry.find('atom:title', ns)
                    summary_elem = entry.find('atom:summary', ns)
                    id_elem = entry.find('atom:id', ns)
                    published_elem = entry.find('atom:published', ns)
                    
                    if title_elem is not None and summary_elem is not None:
                        title = title_elem.text.strip().replace('\n', ' ')
                        summary = summary_elem.text.strip().replace('\n', ' ')
                        paper_id = id_elem.text if id_elem is not None else "Unknown ID"
                        published = published_elem.text if published_elem is not None else ""
                        
                        search_results.append({
                            "title": title,
                            "abstract": summary, # Keep full abstract for translation
                            "source": paper_id,
                            "published": published
                        })
        except Exception as e:
            logger.error(f"ArXiv search failed: {e}")
            print(f"ArXiv Error: {e}")

        # 2. BioRxiv Search (Metadata interval - expand to last 30 days)
        try:
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            # Using a fixed start date for 2025 or relative past
            biorxiv_url = f"https://api.biorxiv.org/details/biorxiv/2025-01-01/{today}/0"
            resp = httpx.get(biorxiv_url, timeout=12.0)
            print(f"BioRxiv Status: {resp.status_code}")
            if resp.status_code == 200:
                biorxiv_data = resp.json()
                if "collection" in biorxiv_data and isinstance(biorxiv_data["collection"], list):
                    q_lower = query.lower()
                    match_count = 0
                    for item in biorxiv_data["collection"]:
                        # Match any of the words if it's a multiple topic field
                        if q_lower in item["title"].lower() or q_lower in item["abstract"].lower():
                            search_results.append({
                                "title": item["title"],
                                "abstract": item["abstract"][:300] + "...",
                                "source": f"BioRxiv ({item['doi']})"
                            })
                            match_count += 1
                            if match_count >= 2: break
                    print(f"BioRxiv Relevant Matches: {match_count}")
        except Exception as e:
            logger.error(f"BioRxiv search failed: {e}")
            print(f"BioRxiv Error: {e}")

        return search_results


try:
    import chromadb
    from chromadb.config import Settings
    from sentence_transformers import SentenceTransformer
    CHROMA_AVAILABLE = True
except ImportError:
    CHROMA_AVAILABLE = False
    logger.warning("ChromaDB or SentenceTransformers not found. Falling back to simple keyword search.")


try:
    import sqlite3
    SQLITE_AVAILABLE = True
except ImportError:
    SQLITE_AVAILABLE = False
    logger.warning("sqlite3 not found. Keyword search will be disabled.")

class KnowledgeBase:
    """
    Local Retrieval System (RAG).
    Indexes local history (Memory) and public archives (Blockchain).
    Uses ChromaDB for Vector Semantic Search.
    """
    def __init__(self):
        self.documents: List[Dict] = [] # Fallback / Cache
        self.web_researcher = WebResearcher()
        self.chroma_client = None
        self.collection = None
        self.embedding_model = None
        
        if CHROMA_AVAILABLE:
            try:
                # Initialize Persistent Client
                data_path = "backend/data/chroma"
                self.chroma_client = chromadb.PersistentClient(path=data_path)
                
                
                # Initialize Embedding Model with Offline Fallback & Frequency Check
                # Use full model name to avoid alias resolution network call
                self.embedding_model = self._load_embedding_model('sentence-transformers/all-MiniLM-L6-v2')
                
                # Get or Create Collection
                self.collection = self.chroma_client.get_or_create_collection(name="episodic_memory")
                logger.info(f"ChromaDB initialized at {data_path}")
            except Exception as e:
                logger.error(f"Failed to initialize ChromaDB: {e}")
                # Do not assign to global CHROMA_AVAILABLE here to avoid UnboundLocalError
                self.collection = None
                self.chroma_client = None

        # SQLite FTS5 Init
        self.fts_db_path = "backend/data/memory_fts.db"
        self.fts_conn = None
        if SQLITE_AVAILABLE:
            try:
                self.fts_conn = sqlite3.connect(self.fts_db_path, check_same_thread=False)
                self.fts_conn.execute("""
                    CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(
                        content, 
                        source, 
                        timestamp, 
                        sender, 
                        type
                    )
                """)
                self.fts_conn.commit()
                logger.info(f"SQLite FTS5 initialized at {self.fts_db_path}")
            except Exception as e:
                logger.error(f"Failed to initialize SQLite FTS5: {e}")
                self.fts_conn = None

    def _load_embedding_model(self, model_name: str):
        """
        Load SentenceTransformer with smart offline/fallback logic.
        1. Check update frequency (default 30 days).
        2. Fallback to offline if connection fails.
        """
        cache_dir = "backend/data"
        if not os.path.exists(cache_dir):
            os.makedirs(cache_dir)
            
        check_file = os.path.join(cache_dir, ".model_last_check")
        should_check_online = True
        
        # 1. Frequency Check (30 days = 2592000 seconds)
        if os.path.exists(check_file):
            try:
                with open(check_file, 'r') as f:
                    last_check = float(f.read().strip())
                if time.time() - last_check < 2592000:
                    should_check_online = False
                    logger.info(f"Skipping model update check (Last checked: {time.ctime(last_check)})")
            except Exception:
                pass # File corrupted, check online

        # 2. Try Load
        model = None
        original_offline = os.environ.get("HF_HUB_OFFLINE") # Backup

        try:
            # Try to load offline first if we decided to skip online check
            if not should_check_online:
                try:
                    # Force offline
                    os.environ["HF_HUB_OFFLINE"] = "1"
                    logger.info(f"Loading {model_name} in Offline Mode...")
                    model = SentenceTransformer(model_name, cache_folder=cache_dir, local_files_only=True)
                except Exception as offline_error:
                    logger.warning(f"Offline load failed ({offline_error}). Forcing online check...")
                    should_check_online = True
                    if "HF_HUB_OFFLINE" in os.environ:
                        del os.environ["HF_HUB_OFFLINE"]

            # If we need to check online (either initially true or fallback from above)
            if should_check_online:
                # Allow online
                if "HF_HUB_OFFLINE" in os.environ:
                    del os.environ["HF_HUB_OFFLINE"]
                
                logger.info(f"Checking for updates for {model_name}...")
                model = SentenceTransformer(model_name, cache_folder=cache_dir)
                
                # Save timestamp on success
                with open(check_file, 'w') as f:
                    f.write(str(time.time()))

        except Exception as e:
            logger.warning(f"Failed to load model: {e}")
            raise e
        finally:
            # Restore env var
            if original_offline is not None:
                os.environ["HF_HUB_OFFLINE"] = original_offline
            elif "HF_HUB_OFFLINE" in os.environ:
                del os.environ["HF_HUB_OFFLINE"]

        return model

                


        # Hybrid Search Init
        self.bm25 = None
        self.bm25_corpus = [] # List of {text, metadata}


    def ingest_history(self, history: List[Dict]):
        """Load resident chat history/memory into Vector Store."""
        if not CHROMA_AVAILABLE or not self.collection:
            self._ingest_history_fallback(history)
            return

        documents = []
        metadatas = []
        ids = []
        embeddings = []
        
        count = 0
        seen_ids = set()
        for msg in history:
            text = msg.get("content", "")
            if text:
                # Use message ID or hash as ID
                msg_id = msg.get("id") or str(hash(text + str(msg.get("timestamp"))))
                
                # Deduplicate within batch to prevent ChromaDB DuplicateIDError
                if msg_id in seen_ids:
                    continue
                seen_ids.add(msg_id)
                
                # Metadata
                meta = {
                    "source": "resident_history",
                    "timestamp": str(msg.get("timestamp", "")),
                    "type": str(msg.get("type", "chat")),
                    "sender": str(msg.get("sender", "unknown"))
                }
                
                documents.append(text)
                metadatas.append(meta)
                ids.append(msg_id)
                count += 1
        
        if count > 0:
            # Generate Embeddings Batch
            logger.info(f"Computing embeddings for {count} items...")
            embeddings = self.embedding_model.encode(documents).tolist()
            
            # Upsert to Chroma
            self.collection.upsert(
                documents=documents,
                embeddings=embeddings,
                metadatas=metadatas,
                ids=ids
            )
            logger.info(f"Ingested {count} items into Semantic Memory")
        else:
            logger.info("No items to ingest.")


        # update FTS index (persistent)
        if self.fts_conn:
            self._update_fts_index(history)

    def ingest_insights(self, insights: List[str]):
        """Ingest consolidated insights into Vector Store."""
        if not CHROMA_AVAILABLE or not self.collection:
            logger.warning("ChromaDB unavailable, skipping insight ingestion.")
            return

        documents = []
        metadatas = []
        ids = []
        embeddings = []
        
        seen_ids = set()
        for text in insights:
            if text:
                # Use hash as ID
                import hashlib
                doc_id = hashlib.md5(text.encode()).hexdigest()
                
                # Deduplicate within batch
                if doc_id in seen_ids:
                    continue
                seen_ids.add(doc_id)
                
                meta = {
                    "source": "core_memory",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "type": "insight"
                }
                
                documents.append(text)
                metadatas.append(meta)
                ids.append(doc_id)
        
        if documents:
            logger.info(f"Computing embeddings for {len(documents)} insights...")
            embeddings = self.embedding_model.encode(documents).tolist()
            
            self.collection.upsert(
                documents=documents,
                embeddings=embeddings,
                metadatas=metadatas,
                ids=ids
            )
            logger.info(f"Ingested {len(documents)} insights into Core Memory")
            

            # Also update FTS
            if self.fts_conn:
                # reconstruct dicts to match _update_fts_index expectation
                mock_history = [{"content": t, "timestamp": m["timestamp"], "sender": "system", "type": "insight"} for t, m in zip(documents, metadatas)]
                self._update_fts_index(mock_history)

    def _ingest_history_fallback(self, history: List[Dict]):
        """Legacy keyword ingestion."""
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
        logger.info(f"Ingested {len(history)} history items into Knowledge Base (Fallback)")

    def ingest_archives(self, chain_data: List[Dict]):
        """Load blockchain blocks."""
        # TODO: Implement vector ingestion for archives too
        # For now, just logging
        logger.info(f"Archive ingestion not yet implemented for Vector Store")

    def retrieve_context(self, query: str, limit: int = 3) -> str:
        """
        Semantic retrieval using Vector Search.
        """
        if not CHROMA_AVAILABLE or not self.collection:
            return self._retrieve_context_fallback(query, limit)
            
        try:
            # Encode Query
            query_embedding = self.embedding_model.encode([query]).tolist()
            
            # Query Chroma
            results = self.collection.query(
                query_embeddings=query_embedding,
                n_results=limit
            )
            
            # Format Results
            context_parts = []
            
            # results['documents'] is a list of lists (one list per query)
            if results['documents']:
                docs = results['documents'][0]
                metas = results['metadatas'][0]
                distances = results['distances'][0] if results['distances'] else []
                
                for i, doc_text in enumerate(docs):
                    meta = metas[i]
                    source = meta.get("source", "unknown")
                    # sender = meta.get("sender", "unknown")
                    timestamp = meta.get("timestamp", "")
                    
                    context_parts.append(f"[{source.upper()} {timestamp}] {doc_text}")
            
            return "\n\n".join(context_parts) if context_parts else "No relevant memory found."
            
        except Exception as e:
            logger.error(f"Vector search failed: {e}")
            return self._retrieve_context_fallback(query, limit)


    def _update_fts_index(self, history: List[Dict]):
        """Update SQLite FTS5 index."""
        if not self.fts_conn:
            return

        try:
            cursor = self.fts_conn.cursor()
            new_rows = []
            for msg in history:
                text = msg.get("content", "")
                if text:
                    new_rows.append((
                        text,
                        "resident_history",
                        str(msg.get("timestamp", "")),
                        str(msg.get("sender", "unknown")),
                        str(msg.get("type", "chat"))
                    ))
            
            if new_rows:
                cursor.executemany("INSERT INTO memory_fts (content, source, timestamp, sender, type) VALUES (?, ?, ?, ?, ?)", new_rows)
                self.fts_conn.commit()
                logger.info(f"Inserted {len(new_rows)} items into FTS index.")
        except Exception as e:
            logger.error(f"Failed to update FTS index: {e}")

    def _search_fts(self, query: str, limit: int = 10) -> List[Dict]:
        """Search SQLite FTS5 index."""
        if not self.fts_conn:
            return []
            
        try:
            # Sanitize query for FTS5 (basic)
            # FTS5 uses specific syntax, user query might break it. 
            # We treat the whole query as a phrase or set of tokens.
            # Simple approach: remove special chars or quote.
            # safe_query = f'"{query.replace("\"", "")}"' 
            # actually better to just let sqlite handle simple tokens, or wrap in Double Quotes for phrase
            
            cursor = self.fts_conn.cursor()
            # Ranking by BM25 (default in FTS5)
            sql = "SELECT content, source, timestamp, sender, type FROM memory_fts WHERE memory_fts MATCH ? ORDER BY rank LIMIT ?"
            cursor.execute(sql, (query, limit))
            rows = cursor.fetchall()
            
            results = []
            for r in rows:
                results.append({
                    "content": r[0],
                    "metadata": {
                        "source": r[1],
                        "timestamp": r[2],
                        "sender": r[3],
                        "type": r[4]
                    }
                })
            return results
        except Exception as e:
            logger.warning(f"FTS search error: {e}")
            return []

    def retrieve_hybrid(self, query: str, limit: int = 3) -> str:
        """
        Hyperim retrieval using Reciprocal Rank Fusion (RRF).
        Combines semantic results (Chroma) and keyword results (BM25).
        """
        if not CHROMA_AVAILABLE:
            return self._retrieve_context_fallback(query, limit)
        
        try:
            # 1. Vector Search
            vector_docs = []
            query_embedding = self.embedding_model.encode([query]).tolist()
            chroma_res = self.collection.query(query_embeddings=query_embedding, n_results=limit * 2) 
            
            if chroma_res['documents']:
                c_docs = chroma_res['documents'][0]
                c_metas = chroma_res['metadatas'][0]
                for i, text in enumerate(c_docs):
                    vector_docs.append({
                        "content": text,
                        "metadata": c_metas[i],
                        "score": 0.0 # Placeholder
                    })

            # 2. Keyword Search (SQLite FTS5)
            fts_docs = []
            if self.fts_conn:
                # Get top N * 2
                fts_top = self._search_fts(query, limit=limit * 2)
                for doc in fts_top:
                    fts_docs.append({
                        "content": doc["content"],
                        "metadata": doc["metadata"]
                    })
            else:
                 # Fallback if no FTS
                 return self.retrieve_context(query, limit)

            # 3. Reciprocal Rank Fusion
            # RRF Score = 1 / (k + rank)
            k = 60
            fusion_scores = {} # text -> score
            doc_map = {} # text -> doc_obj

            # Score Vector Results
            for rank, doc in enumerate(vector_docs):
                text = doc["content"]
                doc_map[text] = doc
                fusion_scores[text] = fusion_scores.get(text, 0) + (1 / (k + rank + 1))

            # Score FTS Results
            for rank, doc in enumerate(fts_docs):
                text = doc["content"]
                if text not in doc_map:
                     doc_map[text] = doc
                fusion_scores[text] = fusion_scores.get(text, 0) + (1 / (k + rank + 1))

            # Sort by fused score
            sorted_docs = sorted(fusion_scores.items(), key=lambda item: item[1], reverse=True)
            top_docs = sorted_docs[:limit]

            # Format
            context_parts = []
            for text, score in top_docs:
                doc = doc_map[text]
                meta = doc["metadata"]
                source = meta.get("source", "unknown")
                timestamp = meta.get("timestamp", "")
                context_parts.append(f"[{source.upper()} {timestamp}] {text}")

            return "\n\n".join(context_parts) if context_parts else "No relevant memory found."

        except Exception as e:
            logger.error(f"Hybrid search failed: {e}")
            return self.retrieve_context(query, limit)

    def _retrieve_context_fallback(self, query: str, limit: int = 3) -> str:
        """Simple retrieval based on keyword overlap."""
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
        """Combined Local Context + Web Search"""
        local_context = self.retrieve_context(query)
        web_context = self.web_researcher.search(query)
        
        return f"""
=== Local Knowledge (Semantic Memory) ===
{local_context}

=== Web Research ===
{web_context}
"""

knowledge_base = KnowledgeBase()
