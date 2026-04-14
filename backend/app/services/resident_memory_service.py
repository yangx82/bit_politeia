import json
import logging
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from langchain_core.messages import HumanMessage

from .memory_store import memory_store

logger = logging.getLogger(__name__)


class ResidentMemory:
    """
    Manages resident interaction logs using a layered cognitive architecture:
    - Working Memory: Short-term active buffer.
    - Episodic Memory: Raw chronological journals (JSONL).
    - Semantic Memory: Extracted facts, preferences, and persona.
    - Social Memory: Relationship graph with trust and types.
    - User Vault (NEW): Private/Secret keys and sensitive data.
    - Procedural Memory (NEW): Skill/Tool awareness and policies.
    """

    def __init__(self, workspace_root: str = None):
        # Use the same memory root as MemoryStore
        self.memory_dir = memory_store.memory_dir
        self.legacy_file = self.memory_dir.parent / "resident_memory.json"

        # Topic files (Episodic Storage)
        self.topic_files = {
            "chat": self.memory_dir / "chat.jsonl",
            "research": self.memory_dir / "research.jsonl",
            "system": self.memory_dir / "system.jsonl",
            "agent": self.memory_dir / "agent.jsonl",
        }

        # Semantic Storage
        self.semantic_file = self.memory_dir / "semantic_profile.json"
        self._semantic_profile: dict[str, Any] = {}

        # Social Graph Storage (Relationships)
        self.social_file = self.memory_dir / "social_graph.json"
        self._social_graph: dict[str, dict[str, Any]] = {}

        # User Vault (Private Secrets)
        self.vault_file = self.memory_dir / "vault.json"
        self._vault: dict[str, Any] = {}

        # Working Memory (In-memory buffer)
        self._working_memory: list[dict] = []
        self._working_limit = 10

        self._ensure_files()
        self._migrate_legacy_json()
        self._load_semantic_profile()
        self._load_social_graph()
        self._load_vault()

    def _ensure_files(self):
        """Ensure all topic files exist with metadata header."""
        for topic, path in self.topic_files.items():
            if not path.exists():
                self._write_metadata(path, topic)

    def _write_metadata(self, path: Path, topic: str):
        """Write metadata header to a new JSONL file."""
        metadata = {"_type": "metadata", "created_at": datetime.now().isoformat(), "topic": topic}
        with open(path, "w", encoding="utf-8") as f:
            f.write(json.dumps(metadata) + "\n")

    def _load_semantic_profile(self):
        """Load stored facts and preferences from disk."""
        if self.semantic_file.exists():
            try:
                with open(self.semantic_file, encoding="utf-8") as f:
                    self._semantic_profile = json.load(f)
            except Exception as e:
                logger.error(f"Failed to load semantic profile: {e}")
        if not self._semantic_profile:
            self._semantic_profile = {
                "facts": [],
                "preferences": {},
                "persona": "Neutral Resident",
                "last_updated": None,
                "last_consolidation_time": None,
            }

    def _load_social_graph(self):
        """Load peer relationships from disk."""
        if self.social_file.exists():
            try:
                with open(self.social_file, encoding="utf-8") as f:
                    self._social_graph = json.load(f)
            except Exception as e:
                logger.error(f"Failed to load social graph: {e}")
        if not self._social_graph:
            self._social_graph = {}

    def _load_vault(self):
        """Load private secrets from disk."""
        if self.vault_file.exists():
            try:
                with open(self.vault_file, encoding="utf-8") as f:
                    self._vault = json.load(f)
            except Exception as e:
                logger.error(f"Failed to load vault: {e}")
        if not self._vault:
            self._vault = {}

    def save_semantic_profile(self):
        """Persist semantic profile to disk."""
        try:
            self._semantic_profile["last_updated"] = datetime.now().isoformat()
            with open(self.semantic_file, "w", encoding="utf-8") as f:
                json.dump(self._semantic_profile, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Failed to save semantic profile: {e}")

    def save_social_graph(self):
        """Persist social graph to disk."""
        try:
            with open(self.social_file, "w", encoding="utf-8") as f:
                json.dump(self._social_graph, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Failed to save social graph: {e}")

    def save_vault(self):
        """Persist vault to disk."""
        try:
            with open(self.vault_file, "w", encoding="utf-8") as f:
                json.dump(self._vault, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Failed to save vault: {e}")

    def update_semantic_fact(self, fact: str):
        """Add a new fact to semantic memory if not already present."""
        if "facts" not in self._semantic_profile:
            self._semantic_profile["facts"] = []
        if fact not in self._semantic_profile["facts"]:
            self._semantic_profile["facts"].append(fact)
            self.save_semantic_profile()

    def update_social_edge(
        self, peer_id: str, trust_diff: float = 0, rel_type: str = None, name: str = None
    ):
        """Update or create relationship edge with a peer."""
        if peer_id not in self._social_graph:
            self._social_graph[peer_id] = {
                "name": name or "Unknown Peer",
                "trust_score": 50.0,
                "relationship_type": "observer",
                "last_interaction": None,
                "interaction_count": 0,
            }

        edge = self._social_graph[peer_id]
        edge["trust_score"] = max(0, min(100, edge["trust_score"] + trust_diff))
        if rel_type:
            edge["relationship_type"] = rel_type
        if name:
            edge["name"] = name

        edge["last_interaction"] = datetime.now().isoformat()
        edge["interaction_count"] += 1
        self.save_social_graph()

    def update_vault_item(self, key: str, value: Any):
        """Add or update a private item in the resident vault."""
        self._vault[key] = value
        self.save_vault()

    def _migrate_legacy_json(self):
        """Migrate old resident_memory.json to chat.jsonl."""
        if not self.legacy_file.exists():
            return
        try:
            with open(self.legacy_file, encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list) and data:
                with open(self.topic_files["chat"], "a", encoding="utf-8") as f_out:
                    for entry in data:
                        if "timestamp" not in entry:
                            entry["timestamp"] = datetime.now().isoformat()
                        f_out.write(json.dumps(entry, ensure_ascii=False) + "\n")
            backup_name = (
                self.legacy_file.parent
                / f"resident_memory_backup_{datetime.now().strftime('%Y%m%d%H%M%S')}.json"
            )
            os.rename(self.legacy_file, backup_name)
        except Exception as e:
            logger.error(f"Migration failed: {e}")

    def log_interaction(
        self,
        sender: str,
        content: str,
        msg_type: str = "chat",
        session_id: str = None,
        status: str = None,
        timestamp: datetime = None,
        msg_id: str = None,
    ):
        topic = msg_type if msg_type in self.topic_files else "chat"
        file_path = self.topic_files[topic]
        entry = {
            "id": msg_id if msg_id else str(uuid.uuid4()),
            "timestamp": timestamp.isoformat() if timestamp else datetime.now().isoformat(),
            "sender": sender,
            "content": content,
            "type": msg_type,
            "session_id": session_id,
            "status": status,
        }
        try:
            with open(file_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.error(f"Failed to log to {topic}: {e}")

    def update_message_status(self, message_id: str, status: str, topic: str = None):
        """Update the status of a specific message in the JSONL log. Searches all topics if not found."""
        topics_to_search = []
        if topic and topic in self.topic_files:
            topics_to_search.append(topic)

        # Add all other topics as fallbacks
        for t in self.topic_files:
            if t not in topics_to_search:
                topics_to_search.append(t)

        updated_on_disk = False
        for current_topic in topics_to_search:
            file_path = self.topic_files[current_topic]
            if not file_path.exists():
                continue

            temp_path = file_path.with_suffix(".tmp")
            found_in_file = False
            try:
                with (
                    open(file_path, encoding="utf-8") as f_in,
                    open(temp_path, "w", encoding="utf-8") as f_out,
                ):
                    for line in f_in:
                        try:
                            data = json.loads(line)
                            if data.get("id") == message_id:
                                data["status"] = status
                                found_in_file = True
                                updated_on_disk = True
                            f_out.write(json.dumps(data, ensure_ascii=False) + "\n")
                        except:
                            f_out.write(line)

                if found_in_file:
                    os.replace(temp_path, file_path)
                    break  # Found and updated
                else:
                    if temp_path.exists():
                        os.remove(temp_path)
            except Exception as e:
                logger.error(f"Failed to update message status in {current_topic}: {e}")
                if temp_path.exists():
                    os.remove(temp_path)

        # Update working memory if present
        for msg in self._working_memory:
            if msg.get("id") == message_id:
                msg["status"] = status
                break

    def get_working_context(self) -> list[dict]:
        return self._working_memory

    def get_semantic_context(self) -> str:
        facts = self._semantic_profile.get("facts", [])
        prefs = self._semantic_profile.get("preferences", {})
        context = "### Resident Profile (Semantic Memory)\n"
        if facts:
            context += "Facts:\n" + "\n".join([f"- {f}" for f in facts]) + "\n"
        if prefs:
            context += (
                "Preferences:\n" + "\n".join([f"- {k}: {v}" for k, v in prefs.items()]) + "\n"
            )
        return context

    def get_social_context(self, peer_id: str = None) -> str:
        if not peer_id or peer_id not in self._social_graph:
            return ""
        edge = self._social_graph[peer_id]
        return (
            f"### Social Context for {edge.get('name', 'Peer')}\n"
            f"- Relationship: {edge.get('relationship_type', 'unknown')}\n"
            f"- Trust Level: {edge.get('trust_score', 50.0)}/100\n"
            f"- Total Interactions: {edge.get('interaction_count', 0)}\n"
        )

    def get_vault_context(self) -> str:
        """Fetch private resident secrets."""
        if not self._vault:
            return ""
        items = [f"- {k}: {v}" for k, v in self._vault.items()]
        return "### Private Resident Vault (Private Memory)\n" + "\n".join(items) + "\n"

    def get_procedural_context(self) -> str:
        """Fetch available skills/policies awareness."""
        from .skill_manager import skill_manager

        skills = skill_manager.get_skill_index()
        if not skills:
            return ""
        return "### Internal Skill-Set (Procedural Memory)" + skills

    def get_full_context_text(self, peer_id: str = None, recent_count: int = 10) -> str:
        semantic = self.get_semantic_context()
        social = self.get_social_context(peer_id)
        vault = self.get_vault_context()
        procedural = self.get_procedural_context()
        working = self.get_working_context()

        msg_text = "\n".join([f"{m['sender']}: {m['content']}" for m in working])
        parts = [semantic]
        if social:
            parts.append(social)
        if vault:
            parts.append(vault)
        if procedural:
            parts.append(procedural)

        parts.append(f"### Recent Interaction (Working Memory)\n{msg_text}")
        return "\n".join([p for p in parts if p])

    def get_recent_history(self, limit: int = 50, topic: str = "chat") -> list[dict]:
        file_path = self.topic_files.get(topic, self.topic_files["chat"])
        entries = []
        if not file_path.exists():
            return []
        try:
            with open(file_path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        if data.get("_type") == "metadata":
                            continue
                        entries.append(data)
                    except:
                        continue
            return entries[-limit:]
        except:
            return []

    def get_all_history(self) -> list[dict]:
        all_entries = []
        for path in self.topic_files.values():
            if not path.exists():
                continue
            try:
                with open(path, encoding="utf-8") as f:
                    for line in f:
                        try:
                            data = json.loads(line)
                            if data.get("_type") == "metadata":
                                continue
                            all_entries.append(data)
                        except:
                            continue
            except:
                continue
        all_entries.sort(key=lambda x: x.get("timestamp", ""))
        return all_entries

    def search_history(
        self, query: str = None, date_from: str = None, date_to: str = None
    ) -> list[dict]:
        history = self.get_all_history()
        filtered = []
        q_lower = query.lower() if query else None
        dt_from = datetime.fromisoformat(date_from) if date_from else None
        dt_to = datetime.fromisoformat(date_to) if date_to else None
        for entry in history:
            if q_lower and q_lower not in entry.get("content", "").lower():
                continue
            if dt_from or dt_to:
                try:
                    ts = datetime.fromisoformat(entry.get("timestamp"))
                    if dt_from and ts < dt_from:
                        continue
                    if dt_to and ts > dt_to:
                        continue
                except:
                    continue
            filtered.append(entry)
        return filtered

    # ============================================================
    # Delegate methods to MemoryStore for context_manager compatibility
    # ============================================================

    def read_long_term(self) -> str:
        """Read long-term memory (MEMORY.md). Delegated to MemoryStore."""
        return memory_store.read_long_term()

    def write_long_term(self, content: str) -> None:
        """Write to long-term memory (MEMORY.md). Delegated to MemoryStore."""
        memory_store.write_long_term(content)

    def read_summary(self) -> str:
        """Read the compressed summary of old daily notes. Delegated to MemoryStore."""
        return memory_store.read_summary()

    def write_summary(self, content: str) -> None:
        """Write/update the compressed summary. Delegated to MemoryStore."""
        memory_store.write_summary(content)

    def append_summary(self, content: str) -> None:
        """Append to existing summary with date marker. Delegated to MemoryStore."""
        memory_store.append_summary(content)

    def get_recent_memories(self, days: int = 7) -> str:
        """Get memories from the last N days. Delegated to MemoryStore."""
        return memory_store.get_recent_memories(days=days)

    def get_old_daily_notes(self, before_days: int = 3) -> list:
        """Get daily notes older than specified days. Delegated to MemoryStore."""
        return memory_store.get_old_daily_notes(before_days=before_days)

    def archive_daily_note(self, file_path) -> None:
        """Move a daily note to the archive directory. Delegated to MemoryStore."""
        memory_store.archive_daily_note(file_path)

    def _get_today_date(self) -> str:
        """Get today's date string. Delegated to MemoryStore."""
        return memory_store._get_today_date()


class ResidentReporter:
    def __init__(self, agent_service):
        self.agent = agent_service
        self.message_bus = agent_service.message_bus

    async def generate_community_report(self, consolidation_results: dict[str, Any]) -> str:
        """
        Generate a natural language report for the resident based on memory consolidation results.
        """
        if not self.agent.llm:
            return "Unable to generate report: LLM not initialized."

        public_facts = consolidation_results.get("public_facts", [])
        social_updates = consolidation_results.get("social_updates", [])

        # Build prompt for summary
        prompt = f"""
        You are a helpful AI Agent reporting to your resident. 
        You just finished your daily memory consolidation and need to provide a brief, professional, and friendly summary.
        
        === DATA FROM TODAY'S CONSOLIDATION ===
        - New Facts/Insights: {json.dumps(public_facts, ensure_ascii=False)}
        - Social Changes: {json.dumps(social_updates, ensure_ascii=False)}
        
        Task:
        Provide a concise "Daily Community & State Report" in {self.agent.agent_language}.
        Highlight what you've learned or how your relationships have changed. 
        If there are no significant changes, keep it very brief.
        Format it as a professional update.
        """

        try:
            from langchain_core.messages import HumanMessage, SystemMessage

            messages = [
                SystemMessage(content="You are a clear and concise reporter."),
                HumanMessage(content=prompt),
            ]
            response = await self.agent.llm.ainvoke(messages)
            return response.content.strip()
        except Exception as e:
            logger.error(f"Failed to generate community report: {e}")
            return "I completed my daily memory consolidation, but I encountered an error while drafting the summary report."

    async def send_report_to_resident(self, report_text: str):
        """Send the formatted report to the resident via the message bus."""
        from ..bus.events import OutboundMessage

        # Publish as a 'message' so it's visible in the main feed.
        await self.message_bus.publish_outbound(
            OutboundMessage(
                channel="gateway", session_id="resident", content=report_text, type="message"
            )
        )

        # Log to resident memory as well
        self.agent.resident_memory.log_interaction(
            "agent_report", report_text, "report", session_id="resident", status="sent"
        )
        logger.info("Sent daily community report to resident.")

    async def generate_community_brief(self) -> str:
        """
        Summarize recent community/social changes from Semantic and Social memory.
        """
        mem = self.agent.resident_memory
        facts = mem._semantic_profile.get("facts", [])[-5:]

        # Get active social graph summaries
        social_summaries = []
        for peer_id, edge in mem._social_graph.items():
            if edge.get("interaction_count", 0) > 0:
                social_summaries.append(
                    f"- {edge.get('name', 'Peer')}: Trust {edge.get('trust_score', 50.0)}, Rel: {edge.get('relationship_type')}"
                )

        social_text = "\n".join(social_summaries[:5])
        facts_text = "\n".join([f"- {f}" for f in facts])

        prompt = f"""
        You are an AI Social Observer. Summarize the recent community and social state for the resident.
        
        Recent Facts:
        {facts_text or "No new community facts recently."}
        
        Social Graph Snapshot:
        {social_text or "No active peer relationships recorded yet."}
        
        Task:
        Provide a concise "Community & Social Summary" in {self.agent.agent_language}. Focus on trust changes and key facts. Keep it under 3 sentences.
        """

        try:
            from langchain_core.messages import HumanMessage, SystemMessage

            messages = [
                SystemMessage(content="You are a social dynamics analyzer."),
                HumanMessage(content=prompt),
            ]
            response = await self.agent.llm.ainvoke(messages)
            return response.content.strip()
        except Exception as e:
            logger.error(f"Failed to generate community brief: {e}")
            return "I am monitoring community affairs, but I couldn't summarize them clearly at this moment."

    async def generate_daily_brief(self, interests: list[str]) -> str:
        """
        Generate a unified brief covering both research interests and community state.
        """
        if not self.agent.llm:
            return "LLM not initialized."

        # 1. Generate Research Part
        recent_research = self.agent.resident_memory.get_recent_history(limit=5, topic="research")
        research_text = "\n".join([f"- {r['content']}" for r in recent_research])

        research_prompt = f"""
        Context: Research Brief
        Interests: {", ".join(interests)}
        Recent Research:
        {research_text or "No specific research activity logged today."}
        
        Task: 
        Summarize research progress in {self.agent.agent_language}. (1-2 sentences)
        """

        # 2. Generate Community Part (via internal method)
        community_summary = await self.community_brief_content()

        try:
            from langchain_core.messages import HumanMessage, SystemMessage

            # Combine Research + Community into a single call or sequence
            # For best nuance, we sequence them.
            research_resp = await self.agent.llm.ainvoke(
                [
                    SystemMessage(content="You are a professional research reporter."),
                    HumanMessage(content=research_prompt),
                ]
            )
            research_summary = research_resp.content.strip()

            # Combine into a final readable block
            final_report = (
                f"### 📋 智能体定期汇报 (Periodic Report)\n\n"
                f"#### 🔍 研究动态 (Research Focus: {', '.join(interests)})\n"
                f"{research_summary}\n\n"
                f"#### 🌐 社区事务 (Community Affairs)\n"
                f"{community_summary}"
            )
            return final_report

        except Exception as e:
            logger.error(f"Failed to generate unified brief: {e}")
            return f"I'm keeping track of {', '.join(interests)} and community affairs, but the summary generation failed. Please check my raw logs."

    async def community_brief_content(self) -> str:
        """Helper to generate the community part of the brief."""
        mem = self.agent.resident_memory
        facts = mem._semantic_profile.get("facts", [])[-3:]

        # Social Graph
        social_summaries = []
        for edge in list(mem._social_graph.values())[:3]:
            social_summaries.append(f"- {edge.get('name')}: Trust {edge.get('trust_score')}")

        prompt = f"""
        Summarize community/social state briefly in {self.agent.agent_language}.
        Recent Facts: {json.dumps(facts, ensure_ascii=False)}
        Social Graph: {", ".join(social_summaries)}
        Focus on the most important updates. (1-2 sentences)
        """
        resp = await self.agent.llm.ainvoke([HumanMessage(content=prompt)])
        return resp.content.strip()

    async def generate_daily_report(self):
        """Legacy stub."""
        return await self.generate_daily_brief([self.agent.research_field])
