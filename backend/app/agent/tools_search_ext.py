import logging
from typing import Any

from langchain_core.messages import HumanMessage
from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field, PrivateAttr

logger = logging.getLogger(__name__)


class CrossTaskSearchInput(BaseModel):
    query: str = Field(
        description="The scientific or transactional query to search for across all historical logs."
    )
    limit: int = Field(
        default=5,
        description="Maximum number of memory fragments to retrieve before summarization.",
    )


class CrossTaskSearchTool(BaseTool):
    name: str = "cross_task_search"
    description: str = (
        "Search your entire long-term memory (Chat, Research, System, Governance) for relevant past information. "
        "Use this when you need to recall a conclusion, a decision, or a specific technical detail from a previous session or mission."
    )
    args_schema: type[BaseModel] = CrossTaskSearchInput

    # Private attribute to hold the service reference
    _agent: Any = PrivateAttr()

    def _run(self, query: str, limit: int = 5) -> str:
        # Syncing is handled in the async version for performance
        return "Please use the async version of this tool."

    async def _arun(self, query: str, limit: int = 5) -> str:
        try:
            # 1. Ensure logs are synchronized
            logger.info(f"CrossTaskSearch: Syncing logs for query '{query}'...")
            self._agent.knowledge_base.sync_all_topics()

            # 2. Perform Hybrid Search (Chroma + FTS5)
            logger.info("CrossTaskSearch: Executing hybrid retrieval...")
            raw_context = self._agent.knowledge_base.retrieve_hybrid(query, limit=limit)

            if not raw_context or "No relevant memory found" in raw_context:
                return "No matching historical records found for this query."

            # 3. Use ContextManager's Auxiliary LLM to synthesize a High-Level Report
            summarizer = self._agent.context_manager.summarizer_llm

            prompt = f"""
            You are reviewing historical memory fragments retrieved from a hybrid search engine (Chroma + SQLite FTS5).
            Your goal is to provide a HIGH-LEVEL CONCLUSION SUMMARY for the primary agent.
            
            Search Query: "{query}"
            
            Memory Fragments:
            {raw_context}
            
            Instructions:
            1. Synthesize the bits of information into a coherent summary of what happened or what was concluded.
            2. Focus on final outcomes, key decisions, and technical constants.
            3. Do NOT just list the fragments; write a narrative report.
            4. If different sources conflict, highlight the discrepancy.
            
            Format: Markdown Report.
            """

            response = await summarizer.ainvoke([HumanMessage(content=prompt)])
            summary = response.content.strip()

            return f"### [UNIVERSAL MEMORY RECALL REPORT]\n\n{summary}\n\n*Source: Hybrid Search (Semantic + Keyword)*"

        except Exception as e:
            logger.error(f"CrossTaskSearch Tool error: {e}")
            return f"Search failed due to an internal error: {e}"


def create_search_tools(agent_service):
    tool = CrossTaskSearchTool()
    tool._agent = agent_service
    return [tool]
