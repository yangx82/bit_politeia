"""
Receipt Pipeline Module (WhatsApp / Signal / Telegram Receipts Pattern)

Implements 4-stage message lifecycle receipts:
  1. SENT: Message dispatched to the transport layer.
  2. DELIVERED: Remote node received and validated the message packet.
  3. THINKING: Message has entered the remote Agent's LLM reasoning loop.
  4. REPLIED: Remote Agent has generated and sent a response.

Enables conversational transparency and prevents deadlock / repetitive polling while
an agent is actively reasoning.
"""

import json
import logging
import os
import threading
from datetime import datetime, timezone
UTC = timezone.utc
from enum import Enum
from typing import Any, Callable

logger = logging.getLogger(__name__)


class ReceiptState(Enum):
    SENT = "sent"
    DELIVERED = "delivered"
    THINKING = "thinking"
    REPLIED = "replied"
    FAILED = "failed"


class ReceiptPipeline:
    """
    Tracks and updates message lifecycle states across peers.
    """

    def __init__(self):
        self._lock = threading.Lock()
        # message_id -> {"state": ReceiptState, "updated_at": datetime, "sender_id": str, "recipient_id": str}
        self._message_states: dict[str, dict[str, Any]] = {}
        # peer_id -> {"is_thinking": bool, "active_msg_id": str | None, "since": datetime | None}
        self._peer_thinking_states: dict[str, dict[str, Any]] = {}

    def track_sent(self, message_id: str, sender_id: str, recipient_id: str):
        """Records initial sent state when message leaves this node."""
        with self._lock:
            self._message_states[message_id] = {
                "state": ReceiptState.SENT,
                "updated_at": datetime.now(UTC),
                "sender_id": sender_id,
                "recipient_id": recipient_id,
            }
        logger.debug(f"[ReceiptPipeline] Message {message_id} -> SENT")

    def update_receipt(self, message_id: str, state: ReceiptState | str, peer_id: str | None = None):
        """
        Updates the receipt state of a tracked message.
        """
        if isinstance(state, str):
            try:
                state = ReceiptState(state.lower())
            except ValueError:
                state = ReceiptState.DELIVERED

        with self._lock:
            if message_id in self._message_states:
                self._message_states[message_id]["state"] = state
                self._message_states[message_id]["updated_at"] = datetime.now(UTC)
            else:
                self._message_states[message_id] = {
                    "state": state,
                    "updated_at": datetime.now(UTC),
                    "sender_id": "",
                    "recipient_id": peer_id or "",
                }

            # Update peer thinking indicator
            if peer_id:
                if state == ReceiptState.THINKING:
                    self._peer_thinking_states[peer_id] = {
                        "is_thinking": True,
                        "active_msg_id": message_id,
                        "since": datetime.now(UTC),
                    }
                elif state in (ReceiptState.REPLIED, ReceiptState.FAILED):
                    if self._peer_thinking_states.get(peer_id, {}).get("active_msg_id") == message_id:
                        self._peer_thinking_states[peer_id] = {
                            "is_thinking": False,
                            "active_msg_id": None,
                            "since": None,
                        }

        logger.info(f"[ReceiptPipeline] Message {message_id} -> {state.value.upper()} (peer={peer_id})")

    def is_peer_thinking(self, peer_id: str, timeout_seconds: int = 180) -> bool:
        """
        Checks if a peer is currently reasoning on a task.
        Times out automatically if thinking takes unusually long to prevent permanent blocking.
        """
        with self._lock:
            state = self._peer_thinking_states.get(peer_id)
            if not state or not state.get("is_thinking"):
                return False

            since = state.get("since")
            if since and (datetime.now(UTC) - since).total_seconds() > timeout_seconds:
                # Reset stale thinking state
                self._peer_thinking_states[peer_id]["is_thinking"] = False
                return False

            return True

    def get_message_state(self, message_id: str) -> ReceiptState | None:
        """Returns the current state of a message."""
        with self._lock:
            info = self._message_states.get(message_id)
            return info["state"] if info else None


# Singleton instance
receipt_pipeline = ReceiptPipeline()
