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

        # Qwen/DashScope Tool-Calling Penalty: Limit is ~200k tokens
        self.tool_mode_limit = 200000
        self.is_tool_mode = True  # Agent always uses tools in this system

        logger.info(
            f"ContextManager initialized. Threshold: {self.threshold_tokens} tokens. "
            f"Tool-mode limit enforced: {self.tool_mode_limit} tokens."
        )

    async def get_optimized_messages(
        self,
        session_id: str,
        query: str,
        lc_history: list[BaseMessage],
        channel: str = "resident",
        force_compact: bool = False,
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

        # 3.5 Context Collapse (Remove duplicate identical adjacent messages)
        collapsed_history = self._apply_context_collapse(lc_history)

        # 4. Iterative Compression Check (with dynamic threshold)
        processed_history = await self._ensure_compact_history(
            collapsed_history, task_id, static_chars, force_compact=force_compact
        )

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
            # 1. MEMORY.md (Long-term memory) - Limit to 20k chars
            long_term = self.resident_memory.read_long_term()
            if long_term:
                total_chars += len(long_term[:20000])

            # 2. Daily Notes Summary (compressed historical notes) - Limit to 20k chars
            summary = self.resident_memory.read_summary()
            if summary:
                total_chars += len(summary[:20000])

            # 3. Recent Daily Notes (last 3 days, uncompressed) - Limit to 30k chars
            recent_memories = self.resident_memory.get_recent_memories(days=3)
            if recent_memories:
                daily_notes_chars = len(recent_memories[:30000])
                total_chars += daily_notes_chars

            # 4. Skills index (approximate) - Limit to 10k chars
            if hasattr(self.agent, "skill_manager"):
                skill_index = self.agent.skill_manager.get_skill_index()
                if skill_index:
                    total_chars += len(skill_index[:10000])

            # 5. Community rules (approximate) - Limit to 20k chars
            from .community_config import community_config
            rules_text = community_config.get_all_rules_text()
            if rules_text:
                total_chars += len(rules_text[:20000])

            # 6. Base system prompt overhead
            total_chars += 5000  # More conservative estimate

            logger.debug(
                f"Static content estimate: {total_chars} chars (~{total_chars / 1.2:.0f} tokens)"
            )

        except Exception as e:
            logger.warning(f"Failed to estimate static content size: {e}")
            # Return cached value or 0 if error
            return self._static_content_chars / 1.2
            
        # Cache the result
        self._static_content_chars = total_chars
        # Use a more conservative ratio for Chinese/Multilingual content (1.2 chars/token)
        return total_chars / 1.2

    def _check_daily_notes_compression_needed(self) -> tuple[bool, int]:
        """
        Check if Daily Notes compression is needed.

        Returns:
            (needs_compression, old_notes_count)
        """
        static_tokens = self._estimate_static_content_size()
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

                logger.info(
                    f"Compressed Daily Notes: {len(old_notes)} files summarized and archived"
                )
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
            fallback = (
                f"### 摘要范围: {notes[0][0]} ~ {notes[-1][0]}\n（LLM 摘要失败，保留原始标题）\n\n"
            )
            for date_str, content, _ in notes:
                # Extract headers (lines starting with #)
                headers = [line for line in content.split("\n") if line.strip().startswith("#")]
                if headers:
                    fallback += f"**{date_str}**:\n" + "\n".join(headers[:5]) + "\n\n"
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
        self,
        history: list[BaseMessage],
        task_id: str | None,
        static_tokens: float = 0,
        force_compact: bool = False,
    ) -> list[BaseMessage]:
        """
        Hermes-style iterative compression logic.
        If history tokens exceed threshold, summarize the middle turns.

        Now accounts for static content (MEMORY.md, Daily Notes, Skills) in threshold calculation.
        """
        # 1. Calculate effective threshold accounting for static content
        # static_tokens is already in tokens from _estimate_static_content_size()
        
        # In tool mode, the absolute limit is 200k. 
        # We must ensure History + Static < 200k * threshold_percent
        absolute_limit = self.tool_mode_limit if self.is_tool_mode else self.threshold_tokens
        effective_threshold = (absolute_limit * self.threshold_percent) - static_tokens

        # Ensure minimum threshold (at least 5k tokens for conversation)
        min_threshold = 5000
        if effective_threshold < min_threshold:
            logger.warning(
                f"Static content ({static_tokens:.0f}t) is very large. Effective threshold for history is small: {effective_threshold:.0f}t"
            )
            effective_threshold = min_threshold

        # 2. Estimate tokens from conversation history
        # Use a more conservative ratio for Chinese/Multilingual content (1.2 chars/token)
        history_chars = sum(len(m.content) for m in history if isinstance(m.content, str))
        approx_tokens = history_chars / 1.2

        # 3. Log context breakdown for debugging
        logger.info(
            f"Context size: History={approx_tokens:.0f}t, Static={static_tokens:.0f}t, "
            f"Total={approx_tokens + static_tokens:.0f}t, Threshold={self.threshold_tokens}t, "
            f"Effective={effective_threshold:.0f}t"
        )

        if approx_tokens < effective_threshold and not force_compact:
            return history
        
        if force_compact:
            logger.warning("Force compression activated due to previous context error.")

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
        
        # 3.5 Emergency Truncation: If summarization failed or total history is still massive, 
        # perform a hard drop of older messages.
        if "[Error generating iterative summary" in summary_text or approx_tokens > (absolute_limit * 1.5):
            logger.error(f"Context compression failed or insufficient. Performing hard truncation. (approx_tokens={approx_tokens:.0f})")
            # Keep only the last 10 messages
            if len(history) > 10:
                truncated_history = history[:2] + [SystemMessage(content="[Earlier conversation dropped due to context limits]")] + history[-8:]
                return truncated_history

        # 4. Log to System Archive (Hash Integrity)
        checkpoint_id = str(os.urandom(4).hex())
        self.resident_memory.log_interaction(
            sender="system",
            content=f"[CONTEXT_CHECKPOINT_{checkpoint_id}] {summary_text}",
            msg_type="checkpoint",
            status="archived",
        )

        # 4.5 Autocompact Re-injection: Rescue the last explicit user request
        last_user_request = None
        for msg in reversed(middle):
            content = getattr(msg, "content", "")
            if isinstance(msg, HumanMessage) and isinstance(content, str):
                # In Bit Politeia, pipeline prepends [sender] to HumanMessages
                if not content.startswith("[system]") and not content.startswith("[event]"):
                    last_user_request = content
                    break

        re_injection_block = ""
        if last_user_request:
            re_injection_block = (
                f"\n\n### [AUTOCOMPACT RE-INJECTION: LAST USER REQUEST]\n"
                f"To prevent context loss, here is the exact text of the last instruction you were given:\n"
                f"{last_user_request[:2000]}\n"
            )

        # 5. Construct Compacted History
        compaction_msg = SystemMessage(
            content=f"### [ITERATIVE CONTEXT SUMMARY - ID: {checkpoint_id}]\n"
            f"Earlier turns in this conversation have been compacted to save space. "
            f"Here is the summary of what has been discussed and achieved so far:\n\n"
            f"{summary_text}\n"
            f"{re_injection_block}\n"
            f"Use this summary and the exact user request to maintain the thread and continue from where we left off."
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
        # Limit total characters to stay well within the summarizer's context window (e.g., 260k tokens)
        # 100k chars is approx 25k-40k tokens, which is very safe.
        MAX_INPUT_CHARS = 100000 
        
        for m in reversed(messages): # Work backwards to keep most recent "middle" context if we hit limit
            role = "Assistant" if isinstance(m, AIMessage) else "User"
            content = m.content if isinstance(m.content, str) else str(m.content)
            
            msg_repr = f"[{role}]: {content[:300]}"
            
            # Include tool calls in the summary input so the LLM knows what was attempted
            if isinstance(m, AIMessage) and hasattr(m, "tool_calls") and m.tool_calls:
                tcs = [tc.get("name", "unknown") for tc in m.tool_calls if isinstance(tc, dict)]
                if tcs:
                    msg_repr += f" (Calls tools: {', '.join(tcs)})"
            
            if isinstance(m, ToolMessage):
                role = f"Tool ({m.name})"
                msg_repr = f"[{role}]: {content[:300]}"

            if len(history_text) + len(msg_repr) > MAX_INPUT_CHARS:
                history_text = "[... Earlier turns in this segment truncated ...]\n" + history_text
                break
            
            history_text = msg_repr + "\n" + history_text

        prompt = f"""
Summarize the following conversation segment for an AI agent. 
Focus on:
- Work completed so far.
- Unresolved problems or errors encountered.
- Important decisions made.
- The current state of Task: "{task_goal}"

Conversation Segment:
{history_text}

Format the summary as a structured Markdown list. Keep it concise but information-dense (max 800 words).
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

    def _apply_context_collapse(self, messages: list[BaseMessage]) -> list[BaseMessage]:
        """
        Collapses consecutive similar messages to save tokens and reduce noise.
        Uses Regex to strip dynamic data (timestamps, UUIDs) and fuzzy matching.
        """
        if not messages:
            return messages
            
        import re
        
        def _strip_dynamic(content: str) -> str:
            # Strip ISO8601 / standard timestamps
            s = re.sub(r'\b\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?Z?\b', '', content)
            # Strip simple time HH:MM:SS
            s = re.sub(r'\b\d{2}:\d{2}:\d{2}\b', '', s)
            # Strip UUIDs and long hex hashes (common in P2P logs)
            s = re.sub(r'\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b', '', s)
            s = re.sub(r'\b[0-9a-fA-F]{8,}\b', '', s)
            return s.strip()

        collapsed_messages = []
        current_msg = messages[0]
        repeat_count = 1
        
        for next_msg in messages[1:]:
            is_ai_with_tools = isinstance(current_msg, AIMessage) and getattr(current_msg, "tool_calls", None)
            
            content_match = False
            if type(current_msg) == type(next_msg) and not is_ai_with_tools:
                c1 = current_msg.content if isinstance(current_msg.content, str) else ""
                c2 = next_msg.content if isinstance(next_msg.content, str) else ""
                
                s1 = _strip_dynamic(c1)
                s2 = _strip_dynamic(c2)
                
                if s1 and s2 and abs(len(s1) - len(s2)) < 20:
                    import difflib
                    ratio = difflib.SequenceMatcher(None, s1, s2).ratio()
                    if ratio > 0.85:
                        content_match = True
                elif s1 == s2:
                    content_match = True
                    
            if content_match:
                repeat_count += 1
                continue
                
            # Flush current
            if repeat_count > 1:
                current_msg.content = f"[Collapsed {repeat_count} identical messages]\n" + str(current_msg.content)
            
            collapsed_messages.append(current_msg)
            current_msg = next_msg
            repeat_count = 1
            
        # Flush last
        if repeat_count > 1:
            current_msg.content = f"[Collapsed {repeat_count} identical messages]\n" + str(current_msg.content)
        collapsed_messages.append(current_msg)
        
        if len(collapsed_messages) < len(messages):
            logger.info(f"Context Collapse: Reduced {len(messages)} messages to {len(collapsed_messages)}.")
            
        return collapsed_messages

    def apply_micro_compaction(self, messages: list[BaseMessage], keep_recent: int = 2) -> None:
        """
        Micro-compact specific high-output tool results in the message list IN-PLACE.
        Replaces the content of older tool executions with a placeholder to save context window.
        """
        compactable_tools = {
            "academic_research",
            "execute_shell_command",
            "read_file",
            "list_dir",
            "search_web"
        }
        
        # 1. Map tool_call_id to tool name by finding them in AIMessages
        call_id_to_name = {}
        for msg in messages:
            if isinstance(msg, AIMessage) and hasattr(msg, "tool_calls"):
                for tc in msg.tool_calls:
                    tc_id = tc.get("id") if isinstance(tc, dict) else getattr(tc, "id", None)
                    tc_name = tc.get("name") if isinstance(tc, dict) else getattr(tc, "name", None)
                    if tc_id and tc_name:
                        call_id_to_name[tc_id] = tc_name

        # 2. Collect all ToolMessages that belong to compactable tools
        compactable_msg_indices = []
        for i, msg in enumerate(messages):
            if isinstance(msg, ToolMessage):
                tool_name = call_id_to_name.get(msg.tool_call_id)
                if tool_name in compactable_tools:
                    compactable_msg_indices.append(i)

        # 3. If there are more than keep_recent, clear the older ones
        if len(compactable_msg_indices) > keep_recent:
            indices_to_clear = compactable_msg_indices[:-keep_recent]
            cleared_count = 0
            for idx in indices_to_clear:
                old_msg = messages[idx]
                if old_msg.content != "[Old tool result content cleared to save memory]":
                    old_msg.content = "[Old tool result content cleared to save memory]"
                    cleared_count += 1
            
            if cleared_count > 0:
                logger.info(f"Micro-compaction triggered: Cleared {cleared_count} old tool results.")
