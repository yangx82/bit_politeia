from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from datetime import datetime
import uuid

class Session(BaseModel):
    """
    Global Session object to persist state across interactions and channels.
    """
    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    entity_id: str
    channel: str
    
    # State tracking
    created_at: datetime = Field(default_factory=datetime.now)
    last_active: datetime = Field(default_factory=datetime.now)
    
    # Context & Logic
    history_slice: List[Any] = [] # Recent Relevant messages
    current_task: Optional[str] = None
    active_tools: List[str] = []
    
    # Metrics
    token_usage_total: int = 0
    message_count: int = 0
    
    # Dynamic Metadata (Plugins/Skills can store stuff here)
    metadata: Dict[str, Any] = {}
    
    # Task persistence (for multi-step long-running goals)
    pending_goals: List[Dict[str, Any]] = []

    class Config:
        arbitrary_types_allowed = True
