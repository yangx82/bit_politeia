import logging
import json
from datetime import datetime
from typing import List
from ..services.knowledge_base import knowledge_base
from ..services.memory_store import memory_store

logger = logging.getLogger(__name__)

class ConsolidationService:
    def __init__(self, agent_service):
        self.agent = agent_service

    async def run_daily_consolidation(self):
        """
        Reads today's memory, summarizes it, and stores it in vector DB.
        """
        logger.info("Starting Daily Memory Consolidation...")
        
        # 1. Get today's content
        today_content = memory_store.read_today()
        if not today_content or len(today_content) < 50:
            logger.info("Not enough content to consolidate (size < 50 chars).")
            return

        # 2. Generate Summary/Insights using LLM
        if not self.agent.llm:
            logger.warning("Agent LLM not ready for consolidation.")
            return

        logger.info("Prompting LLM for memory consolidation...")
        prompt = f"""
        You are an AI Kernel responsible for Memory Consolidation.
        Analyze the following interaction log from today:
        
        === START LOG ===
        {today_content}
        === END LOG ===
        
        Extract key facts, user preferences, and important events as distinct bullet points.
        Ignore trivial chitchat.
        
        Return ONLY a JSON list of strings. Example:
        ["User lives in Paris", "User prefers Python over Java"]
        """

        try:
            from langchain_core.messages import HumanMessage, SystemMessage
            
            messages = [
                SystemMessage(content="You are a strict data extraction system. Output JSON only."),
                HumanMessage(content=prompt)
            ]
            
            response = await self.agent.llm.ainvoke(messages)
            content = response.content.strip()
            
            # Remove markdown code blocks if present
            if content.startswith("```json"):
                content = content[7:]
            if content.endswith("```"):
                content = content[:-3]
            content = content.strip()

            insights = json.loads(content)
            
            if not isinstance(insights, list):
                logger.error("LLM returned non-list JSON for consolidation.")
                return

            # 3. Store in KnowledgeBase
            if insights:
                logger.info(f"Consolidating {len(insights)} insights...")
                knowledge_base.ingest_insights(insights)
                
                # Optional: Append to Long-term Memory file
                summary_text = "\n".join([f"- {i}" for i in insights])
                memory_store.append_today(f"\n\n### Consolidated Insights\n{summary_text}")
            else:
                logger.info("No substantial insights found.")

        except Exception as e:
            logger.error(f"Consolidation failed: {e}")
