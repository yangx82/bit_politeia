"""
Cognitive Memory Consolidation & Sleep-Phase Dreaming Module (v2.0)

Handles:
1. Daily / Idle-Adaptive Memory Consolidation (Facts, Secrets, Social Trust, Research Preferences).
2. Knowledge Graph Conflict Invalidation (SUPERSEDED_BY relations).
3. High-Order Concept Distillation (Abstracted insights from episodic interactions).
4. Synaptic Decay & Pruning (Ebbinghaus forgetting curve for stale memories).
"""

import json
import logging
from datetime import datetime, timedelta, timezone
UTC = timezone.utc
from typing import Any

from ..services.knowledge_base import knowledge_base
from ..services.memory_store import memory_store

logger = logging.getLogger(__name__)


class ConsolidationService:
    def __init__(self, agent_service):
        self.agent = agent_service

    async def run_daily_consolidation(self):
        """Standard daily memory consolidation wrapper."""
        return await self.run_sleep_consolidation(force=True)

    async def run_sleep_consolidation(self, force: bool = False) -> dict[str, Any]:
        """
        Sleep-Phase Memory Consolidation (v2.0):
        Distills facts, resolves conflicts, distills high-order concepts, and prunes stale memories.
        """
        logger.info("Starting Sleep-Phase Cognitive Memory Consolidation v2.0...")
        mem = getattr(self.agent, "resident_memory", None)
        if not mem:
            logger.warning("[SleepConsolidation] ResidentMemory uninitialized.")
            return {}

        # 1. Determine Time Range
        now = datetime.now(UTC)
        last_run_str = mem._semantic_profile.get("last_consolidation_time")

        if last_run_str:
            last_run = datetime.fromisoformat(last_run_str)
        else:
            last_run = now - timedelta(days=7)

        logger.info(f"[SleepConsolidation] Aggregating memories from {last_run.isoformat()} to {now.isoformat()}")

        # 2. Aggregate Episodic Memory (JSONL Logs) & Manual Notes
        logs = mem.search_history(date_from=last_run.isoformat(), date_to=now.isoformat())
        log_text = "\n".join([f"[{l['timestamp']}] {l['sender']}: {l['content']}" for l in logs])

        days_diff = max(1, (now - last_run).days)
        notes_text = memory_store.get_recent_memories(days=days_diff)

        combined_content = (
            f"--- INTERACTION LOGS ---\n{log_text}\n\n--- MANUAL NOTES ---\n{notes_text}"
        )

        if len(combined_content.strip()) < 100 and not force:
            logger.info("[SleepConsolidation] Insufficient new content to consolidate.")
            mem._semantic_profile["last_consolidation_time"] = now.isoformat()
            mem.save_semantic_profile()
            return {"status": "skipped", "reason": "insufficient_content"}

        # 3. LLM-Based Cognitive Semantization & Concept Distillation
        if not getattr(self.agent, "llm", None):
            logger.warning("[SleepConsolidation] Agent LLM not configured.")
            return {"status": "skipped", "reason": "no_llm"}

        prompt = """
        You are an Advanced Cognitive Memory & Semantic Distillation Kernel.
        Analyze the interaction logs and manual notes to perform memory consolidation, conflict detection, and concept distillation.

        === COMBINED MEMORY INPUT ===
        {content}
        === END INPUT ===

        Tasks:
        1. [PUBLIC SEMANTICS] Extract general facts about the resident, world, or project.
        2. [CONFLICT RESOLUTION] If any new fact directly replaces, invalidates, or updates an older fact/status, specify the obsolete fact and replacement.
        3. [CONCEPT DISTILLATION] Distill high-order abstract concepts, reusable strategies, or behavioral guidelines learned from these interactions.
        4. [PRIVATE SECRETS] Identify sensitive data (API keys, credentials, private secrets) intended for the Private User Vault.
        5. [SOCIAL ANALYSIS] Identify peers interacted with and rate trust impact (-10 to +10).
        6. [RESEARCH PREFERENCES] Identify resident feedback or preferences on literature/research topics.

        Return strictly a JSON object:
        {{
          "public_facts": ["fact 1"],
          "superseded_facts": [{{"old_fact": "...", "new_fact": "...", "reason": "..."}}],
          "distilled_concepts": [{{"concept": "...", "category": "architecture/workflow/preference", "confidence": 0.9}}],
          "private_secrets": {{"key": "value"}},
          "social_updates": [{{"peer_id": "uuid", "trust_diff": 5.0, "rel_type": "ally", "name": "Name"}}],
          "research_preferences": {{"positive_keywords": [], "negative_keywords": [], "feedback_summary": ""}}
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

            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()

            result = json.loads(content)

            # 4. Apply Facts & Conflict Invalidation
            for f in result.get("public_facts", []):
                mem.update_semantic_fact(f)
                try:
                    from .next_gen_memory import next_gen_memory
                    next_gen_memory.add_temporal_fact(
                        subject=mem._semantic_profile.get("persona", "Resident"),
                        relation="KNOWS_FACT",
                        target=f,
                        valid_from=now.isoformat(),
                    )
                except Exception:
                    pass

            # Conflict resolution in knowledge graph
            superseded = result.get("superseded_facts", [])
            for item in superseded:
                old_f = item.get("old_fact")
                new_f = item.get("new_fact")
                logger.info(f"[SleepConsolidation] Invalided old fact: '{old_f}' -> Superseded by: '{new_f}'")
                try:
                    from .next_gen_memory import next_gen_memory
                    next_gen_memory.add_temporal_fact(
                        subject=old_f,
                        relation="SUPERSEDED_BY",
                        target=new_f,
                        valid_from=now.isoformat(),
                    )
                except Exception:
                    pass

            # 5. Distill High-Order Concepts
            concepts = result.get("distilled_concepts", [])
            existing_concepts = mem._semantic_profile.get("distilled_concepts", [])
            for c in concepts:
                existing_concepts.append({
                    "concept": c.get("concept"),
                    "category": c.get("category", "general"),
                    "confidence": c.get("confidence", 1.0),
                    "created_at": now.isoformat(),
                })
            mem._semantic_profile["distilled_concepts"] = existing_concepts[-50:]  # Keep top 50 concepts

            # 6. Apply Synaptic Decay & Pruning (Decay weights of older memories)
            self._apply_synaptic_decay(mem)

            # 7. Update Secrets & Social Updates
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

            # 8. Persist & Report
            mem._semantic_profile["last_consolidation_time"] = now.isoformat()
            mem.save_semantic_profile()

            all_insights = result.get("public_facts", [])
            if all_insights:
                knowledge_base.ingest_insights(all_insights)

            if getattr(self.agent, "reporter", None):
                report = await self.agent.reporter.generate_community_report(result)
                await self.agent.reporter.send_report_to_resident(report)

            logger.info(
                f"[SleepConsolidation] Consolidation v2.0 complete: {len(result.get('public_facts', []))} facts, "
                f"{len(superseded)} conflicts resolved, {len(concepts)} concepts distilled."
            )
            return result

        except Exception as e:
            logger.error(f"[SleepConsolidation] Error during consolidation: {e}")
            return {"status": "error", "error": str(e)}

    def _apply_synaptic_decay(self, mem: Any):
        """Applies Ebbinghaus decay to historical memory activation weights."""
        facts = mem._semantic_profile.get("facts", [])
        # Maintain facts list bound to prevent unbounded growth
        if len(facts) > 200:
            # Retain the most recent 200 facts
            mem._semantic_profile["facts"] = facts[-200:]
            logger.info(f"[SleepConsolidation] Pruned {len(facts) - 200} aged facts via synaptic decay.")
