import json
import logging
import os
from datetime import datetime
from typing import List, Dict, Any
import uuid
from langchain_core.messages import SystemMessage, HumanMessage

logger = logging.getLogger(__name__)

# Constants
PRIVATE_MEMORY_FILE = "resident_memory.json"

class ResidentMemory:
    """
    Manages private interaction logs between Agent and Resident.
    Stored locally in a JSON file, NOT on the blockchain.
    """
    def __init__(self, file_path: str = PRIVATE_MEMORY_FILE):
        self.file_path = file_path
        self._ensure_file_exists()

    def _ensure_file_exists(self):
        if not os.path.exists(self.file_path):
            with open(self.file_path, 'w', encoding='utf-8') as f:
                json.dump([], f)

    def log_interaction(self, sender: str, content: str, msg_type: str = "chat"):
        """Append a message to the private log."""
        entry = {
            "id": str(uuid.uuid4()),
            "timestamp": datetime.now().isoformat(),
            "sender": sender,
            "content": content,
            "type": msg_type
        }
        
        try:
            with open(self.file_path, 'r+', encoding='utf-8') as f:
                history = json.load(f)
                history.append(entry)
                f.seek(0)
                json.dump(history, f, indent=2, ensure_ascii=False)
                f.truncate()
        except Exception as e:
            logger.error(f"Failed to log resident interaction: {e}")

    def get_recent_history(self, limit: int = 50) -> List[Dict]:
        try:
            with open(self.file_path, 'r', encoding='utf-8') as f:
                history = json.load(f)
                return history[-limit:]
        except Exception:
            return []

    def get_all_history(self) -> List[Dict]:
        """Retrieve the entire interaction history."""
        try:
            with open(self.file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return []

    def search_history(self, query: str = None, date_from: str = None, date_to: str = None) -> List[Dict]:
        """Filter history by keywords and date range."""
        history = self.get_all_history()
        filtered = []
        
        q_lower = query.lower() if query else None
        dt_from = datetime.fromisoformat(date_from) if date_from else None
        dt_to = datetime.fromisoformat(date_to) if date_to else None

        for entry in history:
            if q_lower and q_lower not in entry.get('content', '').lower():
                continue
            if dt_from or dt_to:
                try:
                    ts = datetime.fromisoformat(entry.get('timestamp'))
                    if dt_from and ts < dt_from: continue
                    if dt_to and ts > dt_to: continue
                except Exception:
                    continue
            filtered.append(entry)
        return filtered

class ResidentReporter:
    """
    Generates periodic reports for the Resident.
    Aggregates community activity and fetches external research updates.
    """
    def __init__(self, agent_service):
        self.agent = agent_service

    async def collect_community_activity(self) -> str:
        """Summarize Governance and Economy events."""
        summary = []
        
        # Governance
        if self.agent.governance_manager:
            gov = self.agent.governance_manager
            active = len(gov.active_elections)
            summary.append(f"Active Elections: {active}")
            
        # Economy
        if self.agent.ledger:
            balance = await self.agent.get_balance()
            summary.append(f"Current Balance: {balance} STATER")
            
        return "\n".join(summary)

    async def collect_research_updates(self, interests: List[str]) -> str:
        """
        Retrieves real research progress with robust de-duplication.
        """
        from .knowledge_base import knowledge_base
        import re
        
        # Get history to avoid duplication
        recent_history = self.agent.resident_memory.get_recent_history(500)
        seen_titles = set()
        
        # Scan entire history for common "Title: ..." pattern
        for msg in recent_history:
            content = msg.get('content', '')
            titles = re.findall(r"Title:\s*(.*)", content)
            for t in titles:
                seen_titles.add(t.strip().lower())
        
        logger.info(f"DEBUG: Found {len(seen_titles)} seen titles in history.")
        
        updates = []
        all_topics = []
        for interest in interests:
            # Only split by semicolon to allow space/AND/comma boolean logic within a topic
            all_topics.extend([t.strip() for t in interest.split(';') if t.strip()])
        
        logger.info(f"DEBUG: Topics to search: {all_topics}")

        for topic in all_topics:
            search_results = knowledge_base.web_researcher.search(topic)
            logger.info(f"DEBUG: Search for '{topic}' returned {len(search_results)} results.")
            
            topic_candidates = []
            
            # 1. Initial Filtering & Scoring
            for idx, res in enumerate(search_results):
                title = res["title"]
                if title.strip().lower() in seen_titles:
                    # logger.info(f"DEBUG: Skipping seen title: {title[:30]}...")
                    continue
                
                # Calculate Hybrid Score
                res['score'] = self._calculate_hybrid_score(res, idx)
                topic_candidates.append(res)

            logger.info(f"DEBUG: Topic '{topic}' has {len(topic_candidates)} new candidates after filtering.")

            if not topic_candidates:
                continue

            # 2. Sort by Hybrid Score and pick Top 5 for LLM Review
            topic_candidates.sort(key=lambda x: x['score'], reverse=True)
            top_5_candidates = topic_candidates[:5]
            
            # 3. LLM Impact Assessment (Select Top 2 from Top 5)
            selected_indices = await self._select_best_candidates(topic, top_5_candidates)
            selected = [top_5_candidates[i] for i in selected_indices if i < len(top_5_candidates)]
            
            # Fallback if LLM fails
            if not selected:
                selected = top_5_candidates[:2]

            updates.append(f"### Topic: {topic}")
            for res in selected:
                abstract_cn = await self._translate_abstract(res['abstract'])
                updates.append(
                    f"Title: {res['title']}\n"
                    f"Abstract: {res['abstract']}\n"
                    f"【中文摘要】: {abstract_cn}\n"
                    f"Source: {res['source']}"
                )
            updates.append("") 
                
        if updates:
            return "\n".join(updates)
            
        return debug_msg

    async def _translate_abstract(self, abstract: str) -> str:
        """Translate abstract to Chinese using LLM."""
        if not self.agent.llm:
            return "Translation service unavailable."
        for attempt in range(3):
            try:
                prompt = [
                    SystemMessage(content="You are a professional scientific translator. Translate the following English abstract into concise, academic Chinese."),
                    HumanMessage(content=f"Abstract:\n{abstract}")
                ]
                response = await self.agent.llm.ainvoke(prompt)
                return response.content.strip()
            except Exception as e:
                logger.warning(f"Translation attempt {attempt+1} failed: {e}")
                if attempt < 2:
                    await asyncio.sleep(2) # Wait 2 seconds before retry
                    
        return "（翻译不可用：请求超时或服务繁忙）"

    def _calculate_hybrid_score(self, paper: Dict, rank_index: int) -> float:
        """
        Calculate score based on Relevance (Rank) and Recency (Date).
        Score = 0.4 * Relevance + 0.6 * Recency
        """
        # Relevance: 0-100 based on search rank (assuming input is sorted by relevance)
        # Rank 0 = 100, Rank 99 = 0
        relevance_score = max(0, 100 - rank_index)
        
        # Recency: 0-100 based on days since publication
        recency_score = 0
        try:
            pub_date = datetime.strptime(paper.get('published', '')[:10], "%Y-%m-%d")
            days_diff = (datetime.now() - pub_date).days
            # Linear decay: 100 today, 0 after 60 days
            recency_score = max(0, 100 - (days_diff * 1.6)) 
        except Exception:
            recency_score = 50 # Default if date logic fails

        return (0.4 * relevance_score) + (0.6 * recency_score)

    async def _select_best_candidates(self, topic: str, candidates: List[Dict]) -> List[int]:
        """Ask LLM to select the 2 most impactful papers from the list."""
        if not self.agent.llm:
            return [0, 1]

        try:
            candidate_text = ""
            for i, p in enumerate(candidates):
                candidate_text += f"[{i}] Title: {p['title']}\n    Abstract: {p['abstract'][:200]}...\n\n"

            prompt = [
                SystemMessage(content="You are a senior academic editor. Select the 2 papers with the highest potential impact, novelty, and relevance to the topic."),
                HumanMessage(content=f"Topic: {topic}\n\nCandidates:\n{candidate_text}\n\nReturn ONLY a JSON list of the 2 best indices, e.g. [0, 3].")
            ]
            response = await self.agent.llm.ainvoke(prompt)
            content = response.content.strip()
            
            # Naive JSON parsing
            import json
            # Handle potential markdown fence wrapping
            if "```" in content:
                content = content.split("```")[1].replace("json", "").strip()
            
            indices = json.loads(content)
            if isinstance(indices, list):
                return indices[:2]
        except Exception as e:
            logger.error(f"LLM selection failed: {e}")
        
        return [0, 1] # Fallback to first two

    async def generate_daily_brief(self, interests: List[str] = None) -> str:
        """Compose the full daily brief."""
        interests = interests or ["AI Governance", "P2P Economics"]
        
        community_news = await self.collect_community_activity()
        # Infer additional interests from history
        inferred_interests = await self._infer_interests_from_history(interests)
        if inferred_interests:
            logger.info(f"Inferred implicit interests: {inferred_interests}")
            # Merge and de-duplicate (simple set logic might not be enough if case differs, but good for now)
            # We append inferred to the end
            interests = list(set(interests + inferred_interests))
        
        research_news = await self.collect_research_updates(interests)
        
        brief = f"""
== Daily Community Brief ==
{datetime.now().strftime('%Y-%m-%d')}

[Community Updates]
{community_news}

[Research Radar]
{research_news}

[Agent Status]
Online and Monitoring.
"""
        return brief

    async def _infer_interests_from_history(self, explicit_interests: List[str]) -> List[str]:
        """Analyze recent chat history to find implicit research interests."""
        if not self.agent.llm:
            return []
            
        try:
            # Get last 20 messages, exclude reports
            recent_msgs = self.agent.resident_memory.get_recent_history(20)
            conversation_text = ""
            for msg in recent_msgs:
                if msg.get('sender') in ['user', 'agent'] and msg.get('type') == 'chat':
                    conversation_text += f"{msg.get('sender')}: {msg.get('content')}\n"
            
            if not conversation_text.strip():
                return []

            prompt = [
                SystemMessage(content="You are a research assistant. Analyze the conversation history and identify 1-2 SPECIFIC research topics the user is interested in. "
                                      "Ignore general chit-chat. Return ONLY a comma-separated list of topics (e.g., 'Quantum Computing, DAO Governance'). "
                                      "If no clear research topic is found, return empty string."),
                HumanMessage(content=f"Explicit Interests: {', '.join(explicit_interests)}\n\nConversation History:\n{conversation_text}")
            ]
            
            response = await self.agent.llm.ainvoke(prompt)
            content = response.content.strip()
            
            if not content or "no clear" in content.lower():
                return []
                
            inferred = [t.strip() for t in content.split(',') if t.strip()]
            # Simple de-duplication against explicit
            new_interests = []
            for inf in inferred:
                is_new = True
                for exp in explicit_interests:
                    if inf.lower() in exp.lower() or exp.lower() in inf.lower():
                        is_new = False
                        break
                if is_new:
                    new_interests.append(inf)
                    
            return new_interests[:2] # Max 2 inferred topics
            
        except Exception as e:
            logger.error(f"Failed to infer interests: {e}")
            return []
