
"""Context builder for assembling agent prompts."""

import base64
import mimetypes
from pathlib import Path
from typing import Any, List, Optional
import logging

from langchain_core.messages import SystemMessage, HumanMessage, ToolMessage, AIMessage, BaseMessage

from ..services.memory_store import memory_store
from ..services.skill_manager import skill_manager
from ..agent.prompts import AGENT_SYSTEM_PROMPT

logger = logging.getLogger(__name__)

class ContextBuilder:
    """
    Builds the context (system prompt + messages) for the agent.
    
    Assembles memory, skills, and conversation history into a coherent prompt for the LLM.
    """
    
    def __init__(self):
        self.memory = memory_store
        self.skill_manager = skill_manager
    
    def build_system_prompt(self) -> str:
        """
        Build the complete system prompt from core identity, memory, and skills.
        """
        parts = []
        
        # 1. Core Identity (From prompts.py)
        parts.append(AGENT_SYSTEM_PROMPT)
        
        # 2. Skill Index (Progressive Disclosure)
        skill_index = self.skill_manager.get_skill_index()
        if skill_index:
            parts.append(f"\n\n# Available Skills\n{skill_index}")
            
        # 3. Memory Context
        memory_context = self.memory.get_memory_context()
        if memory_context:
            parts.append(f"\n\n# Memory Context\n{memory_context}")
            
        return "\n\n---\n\n".join(parts)
    
    def build_messages(
        self,
        history: List[Any], # List of BaseMessage or dicts
        current_message: str,
        rag_context: str = None,
        network_identity: str = None,
        source: str = "user"
    ) -> List[BaseMessage]:
        """
        Build the complete message list for an LLM call.
        """
        messages: List[BaseMessage] = []

        # 1. System Prompt
        system_content = self.build_system_prompt()
        
        # Inject dynamic context (RAG + Network Identity) into System Prompt or as separate SystemMessages
        # To keep it clean, we add them as separate SystemMessages immediately after the main prompt
        messages.append(SystemMessage(content=system_content))
        
        if network_identity:
            messages.append(SystemMessage(content=f"Your Network Identity:\n{network_identity}"))
            
        if rag_context:
            messages.append(SystemMessage(content=f"Relevant Knowledge Context:\n{rag_context}"))

        # 2. History (Existing conversation)
        # Assuming history is already a list of LangChain BaseMessage objects 
        # (Message objects from schemas.py need conversion if they are passed here directly)
        # In AgentService, self.history is list[schemas.Message], but for the LLM we need LangChain messages.
        # But AgentService._think_and_act logic usually builds a fresh context for the *current* turn.
        # If we want to include past history, we should convert it. 
        # For now, AgentService._think_and_act was Stateless (only RAG + System + Current User Message).
        # We will keep it stateless regarding *chat history* for now (relying on RAG), 
        # or we can pass a few recent messages if needed. 
        # The user request "nanobot通过ContextBuilder可以给智能体加载历史信息" implies we SHOULD support it.
        
        if history:
            # History is expected to be a list of LangChain BaseMessage objects (HumanMessage, AIMessage, etc.)
            # If they are dicts or other formats, they should be converted before calling this method.
             messages.extend(history)

        # 3. Current User Message
        messages.append(HumanMessage(content=f"Message from {source}: {current_message}"))

        return messages
