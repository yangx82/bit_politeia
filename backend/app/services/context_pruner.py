"""
Context Pruning & Compaction Module (DeepSeek Harness dsh-compaction & toolResultPruner Pattern)

Provides two-tier context optimization:
1. ToolResultPruner: Deterministic head/middle/tail pruning of historical tool outputs without LLM calls.
2. CompactionEngine: Structured semantic summarization with lock-guarded boundary replacement.
"""

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


class ToolResultPruner:
    """
    Trims middle content from historical tool outputs while preserving headers and conclusion.
    """

    def __init__(self, budget_per_old_tool: int = 800, keep_recent_steps: int = 2):
        self.budget_per_old_tool = budget_per_old_tool
        self.keep_recent_steps = keep_recent_steps

    def prune_text(self, text: str, max_chars: int | None = None) -> str:
        """
        Replaces middle of text with a pruned indicator if length exceeds max_chars.
        """
        budget = max_chars or self.budget_per_old_tool
        if len(text) <= budget:
            return text

        head_len = budget // 2
        tail_len = budget // 2
        chars_removed = len(text) - (head_len + tail_len)

        head = text[:head_len]
        tail = text[-tail_len:]
        return f"{head}\n\n... [Tool result pruned: {chars_removed} characters removed for context preservation] ...\n\n{tail}"

    def prune_message_history(self, messages: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
        """
        Prunes old tool messages in history, keeping the most recent `keep_recent_steps` intact.
        Returns (pruned_messages, total_chars_saved).
        """
        if not messages:
            return messages, 0

        total_saved = 0
        pruned_list = []
        
        # Count tool messages from the end to spare recent ones
        tool_indices = [i for i, m in enumerate(messages) if m.get("role") in ("tool", "function") or "[Tool result" in str(m.get("content", ""))]
        recent_threshold = set(tool_indices[-self.keep_recent_steps:]) if len(tool_indices) >= self.keep_recent_steps else set(tool_indices)

        for i, msg in enumerate(messages):
            msg_copy = dict(msg)
            content = msg_copy.get("content", "")
            
            if i in tool_indices and i not in recent_threshold and isinstance(content, str):
                orig_len = len(content)
                pruned_content = self.prune_text(content, self.budget_per_old_tool)
                if len(pruned_content) < orig_len:
                    total_saved += (orig_len - len(pruned_content))
                    msg_copy["content"] = pruned_content

            pruned_list.append(msg_copy)

        if total_saved > 0:
            logger.info(f"[ToolResultPruner] Pruned historical tool outputs, saved {total_saved} characters.")

        return pruned_list, total_saved


class CompactionEngine:
    """
    Performs semantic compaction on oversized conversation histories.
    """

    def __init__(self, max_context_chars: int = 32000, keep_recent_turns: int = 3):
        self.max_context_chars = max_context_chars
        self.keep_recent_turns = keep_recent_turns
        self.pruner = ToolResultPruner()

    async def compact_if_needed(
        self,
        messages: list[dict[str, Any]],
        llm_client: Any = None,
    ) -> list[dict[str, Any]]:
        """
        Applies Tier 1 pruning first, and if still over budget, applies Tier 2 semantic compaction.
        """
        # Tier 1: Deterministic Tool Pruning
        messages, chars_saved = self.pruner.prune_message_history(messages)

        total_chars = sum(len(str(m.get("content", ""))) for m in messages)
        if total_chars <= self.max_context_chars or not llm_client:
            return messages

        # Tier 2: Two-Stage Semantic Compaction
        if len(messages) <= self.keep_recent_turns * 2:
            return messages

        split_idx = len(messages) - (self.keep_recent_turns * 2)
        old_slice = messages[:split_idx]
        recent_slice = messages[split_idx:]

        try:
            logger.info(f"[CompactionEngine] Triggering Tier 2 semantic compaction on {len(old_slice)} messages...")
            
            history_text = "\n".join(
                f"{m.get('role', 'user')}: {str(m.get('content', ''))[:400]}"
                for m in old_slice
            )

            prompt = (
                "You are an expert context summarizer. Provide a concise, dense factual summary "
                "of the key decisions, accomplishments, errors encountered, and current objectives from "
                "this conversation history:\n\n"
                f"{history_text}\n\n"
                "Respond with a clear bulleted summary."
            )

            from langchain_core.messages import HumanMessage
            response = await llm_client.ainvoke([HumanMessage(content=prompt)])
            summary_text = response.content.strip()

            compaction_checkpoint = {
                "role": "user",
                "content": f"[SYSTEM COMPACTION CHECKPOINT]\nSummary of earlier conversation:\n{summary_text}",
                "compacted": True,
            }

            compacted_messages = [compaction_checkpoint] + recent_slice
            logger.info(
                f"[CompactionEngine] Compaction completed: reduced from {len(messages)} to {len(compacted_messages)} messages."
            )
            return compacted_messages

        except Exception as e:
            logger.error(f"[CompactionEngine] Semantic compaction failed: {e}")
            return messages


# Singleton instances
tool_result_pruner = ToolResultPruner()
compaction_engine = CompactionEngine()
