import logging
import json
import os
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple
from langchain_core.messages import BaseMessage, SystemMessage, HumanMessage, AIMessage, ToolMessage
from langchain_openai import ChatOpenAI

logger = logging.getLogger(__name__)

class BitPoliteiaContextManager:
    """
    Manages task-aware context and iterative compression for Bit Politeia.
    Bridges the gap between short-term conversation and long-term archival.
    """
    
    def __init__(self, agent_service):
        self.agent = agent_service
        self.resident_memory = agent_service.resident_memory
        self.task_manager = agent_service.task_manager
        
        # Load auxiliary model config from env
        self.aux_url = os.getenv("AUX_MODEL_URL", agent_service.base_url)
        self.aux_name = os.getenv("AUX_MODEL_NAME", agent_service.model)
        self.aux_key = os.getenv("AUX_MODEL_KEY", agent_service.api_key)
        self.aux_context_len = int(os.getenv("AUX_CONTEXT_WINDOW", "128000"))
        self.threshold_percent = float(os.getenv("CONTEXT_THRESHOLD_PERCENT", "0.7"))
        
        # Internal LLM client for summarization tasks
        self.summarizer_llm = ChatOpenAI(
            base_url=self.aux_url,
            api_key=self.aux_key,
            model=self.aux_name,
            temperature=0.3,
            max_tokens=2000
        )
        
        self.threshold_tokens = int(self.aux_context_len * self.threshold_percent)
        logger.info(f"ContextManager initialized. Threshold: {self.threshold_tokens} tokens using {self.aux_name}")

    async def get_optimized_messages(self, 
                                   session_id: str, 
                                   query: str, 
                                   lc_history: List[BaseMessage]) -> List[BaseMessage]:
        """
        Main entry point for SenseStage. Orchestrates focus detection and lineage retrieval.
        """
        # 1. Focus Detection
        task_id = await self.detect_focus(session_id, query)
        
        # 2. Lineage Retrieval (Cross-session matching)
        lineage_msg = ""
        if task_id:
            lineage_msg = self._get_task_lineage_context(task_id)
            
        # 3. Iterative Compression Check
        processed_history = await self._ensure_compact_history(lc_history, task_id)
        
        # 4. Tool Integrity (Sanitize orphaned/missing tool pairs)
        sanitized_history = self._sanitize_messages(processed_history)
        
        # 5. Construct Final Message List
        return sanitized_history, task_id, lineage_msg

    async def detect_focus(self, session_id: str, query: str) -> Optional[str]:
        """
        Identify which task this conversation is currently focusing on.
        Explicitly set focus in metadata takes precedence.
        """
        from .session_service import session_manager
        session = session_manager.get_session(session_id)
        
        # A) Explicit Focus
        explicit_id = session.metadata.get("focus_task_id")
        if explicit_id:
            # Verify task still exists and is active
            task = self.task_manager.tasks.get(explicit_id)
            if task and task.status not in ["completed", "failed"]:
                return explicit_id
                
        # B) Automatic Detection
        active_tasks = self.task_manager.get_active_tasks()
        if not active_tasks:
            return None
            
        # If query is short, don't waste energy on detection
        if len(query) < 10:
            return None
            
        try:
            task_list_str = "\n".join([f"- ID: {t.id} | Goal: {t.goal}" for t in active_tasks])
            prompt = f"""
            Identify which task ID the following user query is most likely referring to.
            User Query: "{query}"
            
            Active Tasks:
            {task_list_str}
            - ID: NONE | (Use this if the query is general and doesn't match any specific task)
            
            Return ONLY the ID (e.g., 'NONE' or the UUID). No explanation.
            """
            response = await self.summarizer_llm.ainvoke([HumanMessage(content=prompt)])
            detected_id = response.content.strip()
            
            if detected_id != "NONE" and detected_id in self.task_manager.tasks:
                logger.info(f"Auto-detected task focus: {detected_id}")
                return detected_id
        except Exception as e:
            logger.error(f"Focus detection failed: {e}")
            
        return None

    def _get_task_lineage_context(self, task_id: str) -> str:
        """Fetch all prior checkpoints and progress for a specific task cross-session."""
        task = self.task_manager.tasks.get(task_id)
        if not task:
            return ""
            
        context = f"### [CURRENT MISSION FOCUS]: {task.goal}\n"
        if task.checkpoint:
            context += f"- Last Progress Checkpoint: {task.checkpoint}\n"
        
        if task.subtasks:
            completed = [s.description for s in task.subtasks if s.status == "completed"]
            pending = [s.description for s in task.subtasks if s.status == "pending"]
            if completed: context += f"- Completed steps: {', '.join(completed)}\n"
            if pending: context += f"- Remaining steps: {', '.join(pending)}\n"
            
        return context

    async def _ensure_compact_history(self, history: List[BaseMessage], task_id: Optional[str]) -> List[BaseMessage]:
        """
        Hermes-style iterative compression logic.
        If history tokens exceed threshold, summarize the middle turns.
        """
        # 1. Estimate tokens (rough estimate: 4 chars per token)
        total_chars = sum(len(m.content) for m in history if isinstance(m.content, str))
        approx_tokens = total_chars / 4
        
        if approx_tokens < self.threshold_tokens:
            return history
            
        logger.warning(f"Context threshold hit ({approx_tokens:.0f} > {self.threshold_tokens}). Compressing...")
        
        # 2. Divide History
        # Keep first 2 (system/identity) and last 5 (recent context)
        # Summarize the middle
        if len(history) <= 10:
            return history # Too few messages to effectively compress
            
        head = history[:2]
        middle = history[2:-5]
        tail = history[-5:]
        
        # 3. Generate Summary
        summary_text = await self._summarize_middle_turns(middle, task_id)
        
        # 4. Log to System Archive (Hash Integrity)
        checkpoint_id = str(os.urandom(4).hex())
        self.resident_memory.log_interaction(
            sender="system",
            content=f"[CONTEXT_CHECKPOINT_{checkpoint_id}] {summary_text}",
            msg_type="checkpoint",
            status="archived"
        )
        
        # 5. Construct Compacted History
        compaction_msg = SystemMessage(content=f"### [ITERATIVE CONTEXT SUMMARY - ID: {checkpoint_id}]\n"
                                               f"Earlier turns in this conversation have been compacted to save space. "
                                               f"Here is the summary of what has been discussed and achieved so far:\n\n"
                                               f"{summary_text}\n\n"
                                               f"Use this summary to maintain the thread and continue from where we left off.")
        
        return head + [compaction_msg] + tail

    async def _summarize_middle_turns(self, messages: List[BaseMessage], task_id: Optional[str]) -> str:
        """Use the auxiliary model to condense conversation turns."""
        task_goal = self.task_manager.tasks[task_id].goal if task_id and task_id in self.task_manager.tasks else "Unknown"
        
        history_text = ""
        for m in messages:
            role = "Assistant" if isinstance(m, AIMessage) else "User"
            if isinstance(m, ToolMessage): role = f"Tool ({m.name})"
            history_text += f"[{role}]: {m.content[:500]}\n" # Truncate very long tool outputs in summarizer input
            
        prompt = f"""
        Summarize the following conversation segment for an AI agent. 
        Focus on:
        - Work completed so far.
        - Unresolved problems or errors encountered.
        - Important decisions made.
        - The current state of Task: "{task_goal}"
        
        Conversation Segment:
        {history_text}
        
        Format the summary as a structured Markdown list. Keep it concise but information-dense (max 500 words).
        """
        
        try:
            response = await self.summarizer_llm.ainvoke([HumanMessage(content=prompt)])
            return response.content.strip()
        except Exception as e:
            logger.error(f"Summarization failed: {e}")
            return "[Error generating iterative summary. History preserved as-is.]"

    def _sanitize_messages(self, messages: List[BaseMessage]) -> List[BaseMessage]:
        """
        Ensures that every ToolMessage has a corresponding AIMessage with tool_calls,
        and every tool_call in an AIMessage has a ToolMessage response.
        This prevents 400 errors from strict LLM providers (OpenAI/Anthropic).
        """
        # 1. Identify all tool_call_ids present in the assistant messages
        surviving_call_ids = set()
        for msg in messages:
            if isinstance(msg, AIMessage) and hasattr(msg, "tool_calls"):
                for tc in msg.tool_calls:
                    if "id" in tc:
                        surviving_call_ids.add(tc["id"])
                    elif isinstance(tc, dict) and tc.get("id"):
                         surviving_call_ids.add(tc["id"])

        # 2. Identify all ToolMessage responses present
        result_call_ids = set()
        for msg in messages:
            if isinstance(msg, ToolMessage):
                result_call_ids.add(msg.tool_call_id)

        # 3. Drop ToolMessages with no matching assistant call (Orphans)
        orphaned_results = result_call_ids - surviving_call_ids
        if orphaned_results:
            messages = [
                m for m in messages 
                if not (isinstance(m, ToolMessage) and m.tool_call_id in orphaned_results)
            ]
            logger.info(f"Context Sanitizer: Dropped {len(orphaned_results)} orphaned tool results.")

        # 4. Inject stub ToolMessages for assistant calls with missing results
        missing_results = surviving_call_ids - result_call_ids
        if missing_results:
            patched = []
            for msg in messages:
                patched.append(msg)
                if isinstance(msg, AIMessage) and hasattr(msg, "tool_calls"):
                    for tc in msg.tool_calls:
                        tc_id = tc.get("id") if isinstance(tc, dict) else getattr(tc, "id", None)
                        if tc_id in missing_results:
                            # Add a placeholder ToolMessage to satisfy API requirements
                            stub = ToolMessage(
                                content="[Result unavailable - This tool execution was summarized in the context briefing above]",
                                tool_call_id=tc_id
                            )
                            patched.append(stub)
            messages = patched
            logger.info(f"Context Sanitizer: Added {len(missing_results)} stub tool results.")

        return messages

