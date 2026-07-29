import json
import logging
from datetime import datetime, timedelta, timezone
UTC = timezone.utc

from ..services.knowledge_base import knowledge_base
from ..services.memory_store import memory_store

logger = logging.getLogger(__name__)


class ConsolidationService:
    def __init__(self, agent_service):
        self.agent = agent_service

    async def run_daily_consolidation(self):
        """
        Reads memory from the last run time to now, distills it into Semantic Memory,
        Social Graph, and the Private User Vault.
        """
        logger.info("Starting Cognitive Memory Consolidation (Precision Range)...")
        mem = self.agent.resident_memory

        # 1. Determine Time Range
        now = datetime.now(UTC)
        last_run_str = mem._semantic_profile.get("last_consolidation_time")

        if last_run_str:
            last_run = datetime.fromisoformat(last_run_str)
        else:
            # Default to last 7 days if never run
            last_run = now - timedelta(days=7)

        logger.info(f"Consolidating memory from {last_run.isoformat()} to {now.isoformat()}")

        # 2. Aggregate Episodic Memory (JSONL Logs)
        # We use msg_type=None to get all topics (chat, research, agent thoughts)
        logs = mem.search_history(date_from=last_run.isoformat(), date_to=now.isoformat())
        log_text = "\n".join([f"[{l['timestamp']}] {l['sender']}: {l['content']}" for l in logs])

        # 3. Aggregate Manual Notes (Markdown)
        days_diff = max(1, (now - last_run).days)
        notes_text = memory_store.get_recent_memories(days=days_diff)

        combined_content = (
            f"--- INTERACTION LOGS ---\n{log_text}\n\n--- MANUAL NOTES ---\n{notes_text}"
        )

        if len(combined_content.strip()) < 100:
            logger.info("Not enough new content to consolidate.")
            # Still update the time so we don't keep checking empty windows if that's desired,
            # but usually better to wait for real content. Let's update anyway to keep the window moving.
            mem._semantic_profile["last_consolidation_time"] = now.isoformat()
            mem.save_semantic_profile()
            return

        # 4. Generate Summary/Insights using LLM
        if not self.agent.llm:
            logger.warning("Agent LLM not ready for consolidation.")
            return

        logger.info("Prompting LLM for composite semantization (Public/Private/Social)...")
        prompt = """
        You are an AI Kernel responsible for Memory Semantization and Subject Separation.
        Analyze the interaction logs and manual notes from the specified time range and transform them into structured data.
        
        === COMBINED MEMORY INPUT ===
        {content}
        === END INPUT ===
        
        Task:
        1. [PUBLIC SEMANTICS] Extract general facts about the resident, world, or project.
        2. [PRIVATE SECRETS] Identify sensitive data (API keys, credentials, private secrets) intended for the Private User Vault.
        3. [SOCIAL ANALYSIS] Identify peers interacted with and rate trust impact (-10 to +10).
        4. [RESEARCH PREFERENCES] Identify resident feedback or preferences on literature/research topics (positive keywords to focus on, negative keywords to exclude/reduce, and brief preference summary).
        
        Return a JSON object:
        {{
          "public_facts": ["fact 1"],
          "private_secrets": {{"key": "value"}},
          "social_updates": [
            {{"peer_id": "uuid", "trust_diff": 5.0, "rel_type": "ally", "name": "Name"}}
          ],
          "research_preferences": {{
            "positive_keywords": ["keyword1"],
            "negative_keywords": ["keyword2"],
            "feedback_summary": "summary string"
          }}
        }}
        """

        try:
            from langchain_core.messages import HumanMessage, SystemMessage

            messages = [
                SystemMessage(content="You are a strict data scientist. Output valid JSON only."),
                HumanMessage(content=prompt.format(content=combined_content)),
            ]

            response = await self.agent.llm.ainvoke(messages)
            content = response.content.strip()

            if "```" in content:
                content = content.split("```")[1].replace("json", "").strip()

            result = json.loads(content)

            # 5. Update Layers
            for f in result.get("public_facts", []):
                mem.update_semantic_fact(f)
                # Sink to Next-Gen L4 Temporal Knowledge Graph (Neo4j)
                try:
                    from .next_gen_memory import next_gen_memory
                    next_gen_memory.add_temporal_fact(
                        subject=mem._semantic_profile.get("persona", "Resident"),
                        relation="KNOWS_FACT",
                        target=f,
                        valid_from=now.isoformat()
                    )
                except Exception:
                    pass

            vault_items = result.get("private_secrets", {})
            for k, v in vault_items.items():
                mem.update_vault_item(k, v)

            social_updates = result.get("social_updates", [])
            for update in social_updates:
                p_id = update.get("peer_id")
                if p_id:
                    mem.update_social_edge(
                        peer_id=p_id,
                        trust_diff=update.get("trust_diff", 0),
                        rel_type=update.get("rel_type"),
                        name=update.get("name"),
                    )

            res_prefs = result.get("research_preferences", {})
            if res_prefs:
                mem.update_research_preferences(
                    positive_keywords=res_prefs.get("positive_keywords"),
                    negative_keywords=res_prefs.get("negative_keywords"),
                    feedback_summary=res_prefs.get("feedback_summary"),
                )

            # 6. Update Metadata & Persist
            mem._semantic_profile["last_consolidation_time"] = now.isoformat()
            mem.save_semantic_profile()

            logger.info(
                f"Consolidation complete: {len(vault_items)} secrets and {len(social_updates)} social updates processed."
            )

            # 7. Ingest into vector store (Public only)
            all_insights = result.get("public_facts", [])
            if all_insights:
                knowledge_base.ingest_insights(all_insights)

            # 8. Trigger Resident Report
            if self.agent.reporter:
                report = await self.agent.reporter.generate_community_report(result)
                await self.agent.reporter.send_report_to_resident(report)

        except Exception as e:
            logger.error(f"Memory Consolidation failed: {e}")
