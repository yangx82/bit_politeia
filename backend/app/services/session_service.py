import logging
import json
import os
from typing import Dict, Optional
from ..models.session import Session
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

class SessionManager:
    """
    Manages active agent sessions and their persistence.
    Maps User (across channels) to active Session objects.
    """
    def __init__(self, data_dir: str = None):
        self.sessions: Dict[str, Session] = {}
        
        # Resolve data_dir to backend/data/sessions
        if data_dir is None:
            # backend/app/services/session_service.py -> backend/app/services -> backend/app -> backend -> data/sessions
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            self.data_dir = os.path.join(base_dir, "data", "sessions")
        else:
            self.data_dir = data_dir
            
        os.makedirs(self.data_dir, exist_ok=True)
        
    def get_session(self, entity_id: str, channel: str) -> Session:
        """
        Retrieve existing session or create a new one.
        Currently simple: one active session per user.
        """
        # Unique key per participant+channel (or just entity if we want cross-channel)
        session_key = entity_id 
        
        if session_key in self.sessions:
            session = self.sessions[session_key]
            session.last_active = datetime.now(timezone.utc)
            return session
        
        # Try loading from disk
        session = self._load_from_disk(session_key)
        if session:
            self.sessions[session_key] = session
            return session
            
        # Create New
        new_session = Session(entity_id=entity_id, channel=channel)
        self.sessions[session_key] = new_session
        logger.info(f"Created new session {new_session.session_id} for entity {entity_id}")
        return new_session

    def save_session(self, session: Session):
        """Persist session state to disk."""
        session.last_active = datetime.now(timezone.utc)
        self.sessions[session.entity_id] = session
        
        filepath = os.path.join(self.data_dir, f"{session.entity_id}.json")
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(session.model_dump(mode='json'), f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save session {session.session_id}: {e}")

    def _load_from_disk(self, entity_id: str) -> Optional[Session]:
        filepath = os.path.join(self.data_dir, f"{entity_id}.json")
        if not os.path.exists(filepath):
            return None
        
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
                session = Session(**data)
                logger.info(f"Loaded session {session.session_id} from disk for entity {entity_id}")
                return session
        except Exception as e:
            logger.error(f"Failed to load session for entity {entity_id}: {e}")
            return None

# Global Singleton
session_manager = SessionManager()
