import logging
import json
import os
from typing import Dict, Optional
from ..models.session import Session
from datetime import datetime

logger = logging.getLogger(__name__)

class SessionManager:
    """
    Manages active agent sessions and their persistence.
    Maps User (across channels) to active Session objects.
    """
    def __init__(self, data_dir: str = "data/sessions"):
        self.sessions: Dict[str, Session] = {}
        self.data_dir = data_dir
        os.makedirs(data_dir, exist_ok=True)
        
    def get_session(self, user_id: str, channel: str) -> Session:
        """
        Retrieve existing session or create a new one.
        Currently simple: one active session per user.
        """
        # Unique key per user+channel (or just user if we want cross-channel)
        # To support cross-channel, we might use user_id as only key
        session_key = user_id 
        
        if session_key in self.sessions:
            session = self.sessions[session_key]
            session.last_active = datetime.now()
            return session
        
        # Try loading from disk
        session = self._load_from_disk(session_key)
        if session:
            self.sessions[session_key] = session
            return session
            
        # Create New
        new_session = Session(user_id=user_id, channel=channel)
        self.sessions[session_key] = new_session
        logger.info(f"Created new session {new_session.session_id} for user {user_id}")
        return new_session

    def save_session(self, session: Session):
        """Persist session state to disk."""
        session.last_active = datetime.now()
        self.sessions[session.user_id] = session
        
        filepath = os.path.join(self.data_dir, f"{session.user_id}.json")
        try:
            # Use model_dump(mode='json') to ensure all fields are serializable
            # This handles datetime and other pydantic-supported types correctly.
            # For complex mixed types (like history_slice containing LangChain objects),
            # pydantic's mode='json' is generally safer than model_dump_json for raw writing.
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(session.model_dump(mode='json'), f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save session {session.session_id}: {e}")

    def _load_from_disk(self, user_id: str) -> Optional[Session]:
        filepath = os.path.join(self.data_dir, f"{user_id}.json")
        if not os.path.exists(filepath):
            return None
        
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
                session = Session(**data)
                logger.info(f"Loaded session {session.session_id} from disk for user {user_id}")
                return session
        except Exception as e:
            logger.error(f"Failed to load session for user {user_id}: {e}")
            return None

# Global Singleton
session_manager = SessionManager()
