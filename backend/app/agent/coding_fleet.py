"""
Coding Fleet & Sub-Agent Orchestration Manager (CodeWhale-inspired)
Provides multi-agent concurrency limits, persistent session checkpoints,
and file-level lock management for Bit-Politeia.
"""

import os
import json
import time
import asyncio
import logging
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)


@dataclass
class AgentSession:
    session_id: str
    task_description: str
    target_path: str
    status: str = "running"  # running, completed, failed
    created_files: List[str] = field(default_factory=list)
    messages: List[Dict[str, Any]] = field(default_factory=list)
    checkpoint: str = "initialized"
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class CodingFleet:
    """
    Fleet Orchestrator for managing concurrent Coding Sub-Agents,
    session persistence, and per-file write serialization.
    """

    def __init__(self, max_parallel: int = 3, storage_dir: Optional[str] = None):
        import threading
        self.max_parallel = max_parallel
        self._semaphore = asyncio.Semaphore(max_parallel)
        self._file_locks: Dict[str, asyncio.Lock] = {}
        self._lock_mutex = asyncio.Lock()
        self._session_lock = threading.Lock()
        
        # Session storage path
        if not storage_dir:
            base_dir = Path(__file__).parent.parent.parent
            self.storage_dir = base_dir / "data" / "sessions"
        else:
            self.storage_dir = Path(storage_dir)

        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.sessions_file = self.storage_dir / "coding_sessions.json"
        self._sessions: Dict[str, AgentSession] = {}
        self._load_all_sessions()

    def _load_all_sessions(self):
        """Load session metadata from disk if present."""
        if self.sessions_file.exists():
            try:
                with open(self.sessions_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    with self._session_lock:
                        for sid, s_data in data.items():
                            self._sessions[sid] = AgentSession(**s_data)
            except Exception as e:
                logger.warning(f"[CodingFleet] Failed to load coding_sessions.json: {e}")

    def _save_all_sessions(self):
        """Persist session metadata to disk."""
        try:
            temp_file = self.sessions_file.with_suffix(".tmp")
            with self._session_lock:
                data = {sid: sess.to_dict() for sid, sess in self._sessions.items()}
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(temp_file, self.sessions_file)
        except Exception as e:
            logger.error(f"[CodingFleet] Failed to save coding_sessions.json: {e}")

    def create_session(self, session_id: str, task_description: str, target_path: str) -> AgentSession:
        """Create or initialize a Coding Sub-Agent session."""
        session = AgentSession(
            session_id=session_id,
            task_description=task_description,
            target_path=target_path,
        )
        with self._session_lock:
            self._sessions[session_id] = session
        self._save_all_sessions()

        # Sync to NextGen MongoDB L3 store if available
        try:
            from ..services.next_gen_memory import next_gen_memory
            next_gen_memory.store_task_plan(session_id, session.to_dict())
        except Exception:
            pass

        return session

    def get_session(self, session_id: str) -> Optional[AgentSession]:
        with self._session_lock:
            return self._sessions.get(session_id)

    def update_checkpoint(
        self,
        session_id: str,
        checkpoint: str,
        messages: Optional[List[Dict[str, Any]]] = None,
        created_files: Optional[List[str]] = None,
        status: Optional[str] = None,
    ):
        """Update and persist session checkpoint for state restoration."""
        with self._session_lock:
            session = self._sessions.get(session_id)
            if not session:
                return

            session.checkpoint = checkpoint
            session.updated_at = time.time()
            if messages is not None:
                session.messages = messages
            if created_files is not None:
                session.created_files = created_files
            if status is not None:
                session.status = status

        self._save_all_sessions()

        # Sync to NextGen MongoDB L3 store if available
        try:
            from ..services.next_gen_memory import next_gen_memory
            next_gen_memory.store_task_plan(session_id, session.to_dict())
        except Exception:
            pass

    async def acquire_file_lock(self, target_path: str) -> asyncio.Lock:
        """Acquire per-file lock to serialize write operations on the same target file."""
        abs_path = os.path.abspath(target_path)
        async with self._lock_mutex:
            if abs_path not in self._file_locks:
                self._file_locks[abs_path] = asyncio.Lock()
            return self._file_locks[abs_path]

    def get_semaphore(self) -> asyncio.Semaphore:
        """Get the concurrency semaphore."""
        return self._semaphore


# Global singleton instance
coding_fleet = CodingFleet()
