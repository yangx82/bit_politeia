import logging
import os
from pathlib import Path

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
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
            max_tokens=2000,
        )

        self.threshold_tokens = int(self.aux_context_len * self.threshold_percent)
        
        # Cache for static content size (updated when memory changes)
        self._static_content_chars = 0
        self._static_content_last_update = None
        
        logger.info(
            f"ContextManager initialized. Threshold: {self.threshold_tokens} tokens using {self.aux_name}"
        )

    async def get_optimized_messages(
        self, session_id: str, query: str, lc_history: list[BaseMessage], channel: str = "resident"
    ) -> list[BaseMessage]:
        """
        Main entry point for SenseStage. Orchestrates focus detection and lineage retrieval.
        """
        # 1. Focus Detection
        task_id = await self.detect_focus(session_id, query, channel)

        # 2. Lineage Retrieval (Cross-session matching)
        lineage_msg = ""
        if task_id:
            lineage_msg = self._get_task_lineage_context(task_id)

        # 3. Check if Daily Notes compression is needed (async)
        needs_compression, old_notes_count = self._check_daily_notes_compression_needed()
        if needs_compression:
            logger.info(f"Daily Notes compression needed: {old_notes_count} old notes found")
            await self._compress_daily_notes(target_days=3)
            # Re-estimate static content after compression
            static_chars = self._estimate_static_content_size()
        else:
            static_chars = self._estimate_static_content_size()
        
        # 4. Iterative Compression Check (with dynamic threshold)
        processed_history = await self._ensure_compact_history(lc_history, task_id, static_chars)

        # 5. Tool Integrity (Sanitize orphaned/missing tool pairs)
        sanitized_history = self._sanitize_messages(processed_history)

        # 6. Construct Final Message List
        return sanitized_history, task_id, lineage_msg
    
    def _estimate_static_content_size(self) -> int:
        """
        Estimate the size of static content that will be embedded in system prompt.
        Includes: MEMORY.md, Daily Notes (recent + summary), Skills, and other fixed content.
        Returns size in characters.
        
        Note: Compression is now handled asynchronously in get_optimized_messages().
        """
        total_chars = 0
        daily_notes_chars = 0
        
        try:
            # 1. MEMORY.md (Long-term memory)
            long_term = self.resident_memory.read_long_term()
            if long_term:
                total_chars += len(long_term)
            
            # 2. Daily Notes Summary (compressed historical notes)
            summary = self.resident_memory.read_summary()
            if summary:
                total_chars += len(summary)
            
            # 3. Recent Daily Notes (last 3 days, uncompressed)
            recent_memories = self.resident_memory.get_recent_memories(days=3)
            if recent_memories:
                daily_notes_chars = len(recent_memories)
                total_chars += daily_notes_chars
            
            # 4. Skills index (approximate - get from skill manager if available)
            if hasattr(self.agent, 'skill_manager'):
                skill_index = self.agent.skill_manager.get_skill_index()
                if skill_index:
                    total_chars += len(skill_index)
            
            # 5. Community rules (approximate)
            from .community_config import community_config
            rules_text = community_config.get_all_rules_text()
            if rules_text:
                total_chars += len(rules_text)
            
            # 6. Base system prompt overhead (approximate)
            # Includes role blocks, time, host info, etc.
            total_chars += 2000  # Conservative estimate for base overhead
            
            logger.debug(f"Static content estimate: {total_chars} chars (~{total_chars // 4} tokens)")
            
        except Exception as e:
            logger.warning(f"Failed to estimate static content size: {e}")
            # Return cached value or 0 if error
            return self._static_content_chars
        
        # Cache the result
        self._static_content_chars = total_chars
        return total_chars
    
    def _check_daily_notes_compression_needed(self) -> tuple[bool, int]:
        """
        Check if Daily Notes compression is needed.
        
        Returns:
            (needs_compression, old_notes_count)
        """
        static_chars = self._estimate_static_content_size()
        static_tokens = static_chars / 4
        compression_threshold = self.threshold_tokens * 0.5  # 50% of threshold
        
        # Check if compression is needed
        if static_tokens > compression_threshold:
            old_notes = self.resident_memory.get_old_daily_notes(before_days=3)
            if len(old_notes) > 0:
                return True, len(old_notes)
        
        return False, 0
    
    async def _compress_daily_notes(self, target_days: int = 3) -> None:
        """
        Compress Daily Notes by summarizing old notes and archiving originals.
        
        This is TRUE compression:
        1. Read all daily notes older than target_days
        2. Use LLM to generate a structured summary
        3. Append summary to daily_notes_summary.md
        4. Archive original files to archive/
        
        Args:
            target_days: Number of recent days to keep uncompressed (default: 3)
        """
        try:
            # Get old daily notes
            old_notes = self.resident_memory.get_old_daily_notes(before_days=target_days)
            
            if not old_notes:
                logger.info("No Daily Notes to compress.")
                return
            
            logger.info(f"Compressing {len(old_notes)} old daily notes...")
            
            # Generate summary using LLM
            summary = await self._summarize_daily_notes(old_notes)
            
            if summary:
                # Append to summary file
                self.resident_memory.append_summary(summary)
                
                # Archive original files
                for date_str, content, file_path in old_notes:
                    self.resident_memory.archive_daily_note(file_path)
                
                logger.info(f"Compressed Daily Notes: {len(old_notes)} files summarized and archived")
            else:
                logger.warning("Summarization returned empty result, skipping compression")
            
        except Exception as e:
            logger.error(f"Failed to compress Daily Notes: {e}")
    
    async def _summarize_daily_notes(self, notes: list[tuple[str, str, Path]]) -> str:
        """
        Use LLM to generate a structured summary of daily notes.
        
        Args:
            notes: List of (date_str, content, file_path) tuples
            
        Returns:
            Structured markdown summary
        """
        if not notes:
            return ""
        
        # Combine all notes with date headers
        notes_text = ""
        total_chars = 0
        max_chars = 50000  # Limit input size for summarizer
        
        for date_str, content, _ in notes:
            section = f"\n## {date_str}\n{content}\n"
            if total_chars + len(section) > max_chars:
                # Truncate if too long, keep most recent notes
                notes_text += f"\n## {date_str}\n[内容过长已截断...]\n"
                break
            notes_text += section
            total_chars += len(section)
        
        prompt = f"""
请对以下历史 Daily Notes 进行结构化压缩摘要。

要求：
1. **提取关键信息**：重要决策、经验教训、未完成任务
2. **保留具体细节**：如错误信息、配置参数、文件路径等
3. **按主题归类**：相同主题的内容合并
4. **标注时间**：保留原始日期信息

输出格式（Markdown）：
```
### [主题/日期范围]

**关键决策**:
- ...

**经验教训**:
- ...

**未完成任务**:
- ...

**技术细节**:
- ...
```

---

{notes_text}

---
请生成压缩摘要：
"""

        try:
            response = await self.summarizer_llm.ainvoke([HumanMessage(content=prompt)])
            summary = response.content.strip()
            
            # Add metadata header
            date_range = f"{notes[0][0]} ~ {notes[-1][0]}" if len(notes) > 1 else notes[0][0]
            metadata = f"### 摘要范围: {date_range}\n压缩日期: {self.resident_memory._get_today_date()}\n原始文件数: {len(notes)}\n\n"
            
            return metadata + summary
            
        except Exception as e:
            logger.error(f"Daily notes summarization failed: {e}")
            # Fallback: simple extraction of headers and key points
            fallback = f"### 摘要范围: {notes[0][0]} ~ {notes[-1][0]}\n（LLM 摘要失败，保留原始标题）\n\n"
            for date_str, content, _ in notes:
                # Extract headers (lines starting with #)
                headers = [line for line in content.split('\n') if line.strip().startswith('#')]
                if headers:
                    fallback += f"**{date_str}**:\n" + '\n'.join(headers[:5]) + "\n\n"
            return fallback

    async def detect_focus(
        self, session_id: str, query: str, channel: str = "resident"
    ) -> str | None:
        """
        Identify which task this conversation is currently focusing on.
        Explicitly set focus in metadata takes precedence.
        """
        from .session_service import session_manager

        session = session_manager.get_session(session_id, channel)

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
            if completed:
                context += f"- Completed steps: {', '.join(completed)}\n"
            if pending:
                context += f"- Remaining steps: {', '.join(pending)}\n"

        return context

    async def _ensure_compact_history(
        self, history: list[BaseMessage], task_id: str | None, static_chars: int = 0
    ) -> list[BaseMessage]:
        """
        Hermes-style iterative compression logic.
        If history tokens exceed threshold, summarize the middle turns.
        
        Now accounts for static content (MEMORY.md, Daily Notes, Skills) in threshold calculation.
        """
        # 1. Calculate effective threshold accounting for static content
        static_tokens = static_chars / 4
        effective_threshold = self.threshold_tokens - static_tokens
        
        # Ensure minimum threshold (at least 10k tokens for conversation)
        min_threshold = 10000
        if effective_threshold < min_threshold:
            logger.warning(
                f"Static content ({static_tokens:.0f} tokens) exceeds {(self.threshold_tokens - min_threshold):.0f} tokens. "
                f"Consider compressing MEMORY.md or Daily Notes. Using minimum threshold: {min_threshold}"
            )
            effective_threshold = min_threshold
        
        # 2. Estimate tokens from conversation history (rough estimate: 4 chars per token)
        history_chars = sum(len(m.content) for m in history if isinstance(m.content, str))
        approx_tokens = history_chars / 4

        # 3. Log context breakdown for debugging
        logger.info(
            f"Context size: History={approx_tokens:.0f}t, Static={static_tokens:.0f}t, "
            f"Total={approx_tokens + static_tokens:.0f}t, Threshold={self.threshold_tokens}t, "
            f"Effective={effective_threshold:.0f}t"
        )

        if approx_tokens < effective_threshold:
            return history

        logger.warning(
            f"Context threshold hit ({approx_tokens:.0f} + {static_tokens:.0f} = {approx_tokens + static_tokens:.0f} > {self.threshold_tokens}). "
            f"Compressing history..."
        )

        # 2. Divide History
        # Keep first 2 (system/identity) and last 5 (recent context)
        # Summarize the middle
        if len(history) <= 10:
            return history  # Too few messages to effectively compress

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
            status="archived",
        )

        # 5. Construct Compacted History
        compaction_msg = SystemMessage(
            content=f"### [ITERATIVE CONTEXT SUMMARY - ID: {checkpoint_id}]\n"
            f"Earlier turns in this conversation have been compacted to save space. "
            f"Here is the summary of what has been discussed and achieved so far:\n\n"
            f"{summary_text}\n\n"
            f"Use this summary to maintain the thread and continue from where we left off."
        )

        return head + [compaction_msg] + tail

    async def _summarize_middle_turns(
        self, messages: list[BaseMessage], task_id: str | None
    ) -> str:
        """Use the auxiliary model to condense conversation turns."""
        task_goal = (
            self.task_manager.tasks[task_id].goal
            if task_id and task_id in self.task_manager.tasks
            else "Unknown"
        )

        history_text = ""
        for m in messages:
            role = "Assistant" if isinstance(m, AIMessage) else "User"
            if isinstance(m, ToolMessage):
                role = f"Tool ({m.name})"
            history_text += f"[{role}]: {m.content[:500]}\n"  # Truncate very long tool outputs in summarizer input

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

    def _sanitize_messages(self, messages: list[BaseMessage]) -> list[BaseMessage]:
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
                    if "id" in tc or (isinstance(tc, dict) and tc.get("id")):
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
                m
                for m in messages
                if not (isinstance(m, ToolMessage) and m.tool_call_id in orphaned_results)
            ]
            logger.info(
                f"Context Sanitizer: Dropped {len(orphaned_results)} orphaned tool results."
            )

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
                                tool_call_id=tc_id,
                            )
                            patched.append(stub)
            messages = patched
            logger.info(f"Context Sanitizer: Added {len(missing_results)} stub tool results.")

        return messages
