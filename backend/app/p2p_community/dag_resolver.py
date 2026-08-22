"""
Event DAG Resolver Module (Matrix.org Spec Pattern)

Maintains causal relationships between asynchronous multi-agent messages using
a Directed Acyclic Graph (Event DAG). Uses topological sorting (Kahn's algorithm)
with timestamp tie-breaking to linearize branched or out-of-order group discussions
into a coherent, causally consistent conversation history for LLM consumption.
"""

import collections
import logging
from typing import Any

from app.p2p_community.message_protocol import SignedMessage

logger = logging.getLogger(__name__)


class EventDAGResolver:
    """
    Resolves causal DAG order for asynchronous multi-agent group messages.
    """

    def __init__(self):
        self._event_cache: dict[str, SignedMessage] = {}

    def record_event(self, message: SignedMessage):
        """Records an event into the live DAG cache."""
        self._event_cache[message.message_id] = message
        # Keep cache bounded
        if len(self._event_cache) > 500:
            oldest_key = next(iter(self._event_cache))
            self._event_cache.pop(oldest_key, None)

    def get_all_events(self, limit: int = 50) -> list[SignedMessage]:
        """Returns the most recent events recorded in the DAG cache."""
        events = list(self._event_cache.values())
        return events[-limit:]

    @staticmethod
    def linearize_messages(messages: list[SignedMessage]) -> list[SignedMessage]:
        """
        Performs topological sort on a collection of messages linked by `parents`.
        Falls back to timestamp ordering for disconnected nodes or cycles.
        """
        if not messages:
            return []

        # Deduplicate and index by message_id
        msg_map: dict[str, SignedMessage] = {m.message_id: m for m in messages}
        all_ids = set(msg_map.keys())

        # Build adjacency graph: parent -> set of child messages
        # in_degree: number of parents that exist within this message set
        adj: dict[str, list[str]] = {mid: [] for mid in all_ids}
        in_degree: dict[str, int] = {mid: 0 for mid in all_ids}

        for mid, msg in msg_map.items():
            valid_parents = [p for p in (msg.parents or []) if p in all_ids]
            in_degree[mid] = len(valid_parents)
            for p in valid_parents:
                adj[p].append(mid)

        # Priority queue / sorted ready queue by timestamp
        ready = [mid for mid, deg in in_degree.items() if deg == 0]
        ready.sort(key=lambda mid: msg_map[mid].timestamp)

        sorted_ids: list[str] = []

        while ready:
            curr_id = ready.pop(0)
            sorted_ids.append(curr_id)

            for child_id in adj[curr_id]:
                in_degree[child_id] -= 1
                if in_degree[child_id] == 0:
                    ready.append(child_id)
                    ready.sort(key=lambda mid: msg_map[mid].timestamp)

        # If cycles or unresolvable dependencies exist, append remaining by timestamp
        if len(sorted_ids) < len(all_ids):
            remaining = [mid for mid in all_ids if mid not in set(sorted_ids)]
            remaining.sort(key=lambda mid: msg_map[mid].timestamp)
            sorted_ids.extend(remaining)

        linearized = [msg_map[mid] for mid in sorted_ids]
        return linearized

    @staticmethod
    def format_for_llm_context(messages: list[SignedMessage]) -> list[dict[str, str]]:
        """
        Converts DAG-linearized SignedMessages into LLM standard chat messages format.
        """
        linearized = EventDAGResolver.linearize_messages(messages)
        formatted = []
        for msg in linearized:
            sender_label = msg.sender_id[:12] if msg.sender_id else "unknown"
            text_content = ""
            if isinstance(msg.content, dict):
                text_content = msg.content.get("text") or msg.content.get("message") or str(msg.content)
            else:
                text_content = str(msg.content)

            formatted.append({
                "role": "user",
                "name": f"agent_{sender_label}",
                "content": text_content,
                "message_id": msg.message_id,
            })
        return formatted


# Singleton instance
dag_resolver = EventDAGResolver()
