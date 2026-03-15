
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
    
    def build_system_prompt(self, name: str = "Agent", personality: str = "Professional and helpful", channel: str = "resident", host_info: str = None) -> str:
        """
        Build the complete system prompt from core identity, memory, and skills.
        """
        parts = []
        
        # 1. Core Identity (From prompts.py)
        parts.append(AGENT_SYSTEM_PROMPT)
        
        # 1.5 Resident-defined Identity
        identity_block = f"""# Your Resident-Defined Identity
You are currently identified as: **{name}**.
Your designated personality and tone: **{personality}**.
Please strictly adhere to this personality in your interactions."""
        parts.append(identity_block)
        
        # 1.55 Role & Channel Awareness
        if channel == "p2p":
            role_block = f"""# CURRENT DOMAIN: Autonomous Peer-to-Peer Network
[URGENT ROLE AWARENESS] You are communicating directly with another machine Node in the network.
- Do NOT report to your human owner (resident).
- Do NOT use a subservient reporting tone.
- Communicate strictly logically, efficiently, and directly to the node on the other side.
- **FINAL ANSWER DESTINATION**: Your 'Final Answer' in this mode is delivered DIRECTLY to the other machine node via the P2P transport. 
- **CRITICAL**: Do NOT address your resident/user in the final answer. If you need to inform or ask the resident something, you MUST use the `ask_resident` tool first, but keep your final answer strictly for the peer node.
- **TERMINATION PROTOCOL**: If the interaction is complete, a task is confirmed, or no further information is needed from the other node (e.g., both parties have acknowledged a plan), you MUST output exactly `[NO_RESPONSE_NEEDED]` as your final answer. This signals the system to stop the loop and avoid redundant 'ACK' messages.
- If you still need a response, provide a brief technical confirmation (e.g., 'Task completed', 'Data synced')."""
            parts.append(role_block)
        else:
            # Everything else (resident, feishu, telegram, cli, gateway) is a Resident-facing interface
            role_block = f"""# CURRENT DOMAIN: Private User Interface
[ROLE AWARENESS] You are communicating directly with your human Resident/Owner.
- Explain your thoughts naturally.
- Confirm actions you take on their behalf.
- **CRITICAL**: If you successfully use a 'send_p2p_message' or 'send_file' tool, do NOT repeat the content of that message in your final response to the human. Just state 'Message sent to [Target Name/ID].' and offer further assistance if needed."""
            parts.append(role_block)
        
        # 1.6 Current Real-World Time
        from datetime import datetime
        current_time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        time_block = f"""# Current System Time
The current real-world local server time is: **{current_time_str}**.
Use this absolute time for any date calculations or temporal awareness. Do not rely on time information mentioned casually in user chats unless explicitly requested."""
        parts.append(time_block)

        # 1.7 Host Information
        if host_info:
            parts.append(host_info)
        
        # 2. Skill Index (Progressive Disclosure)
        skill_index = self.skill_manager.get_skill_index()
        if skill_index:
            parts.append(f"\n\n# Available Skills\n{skill_index}")
            
        # 3. Memory Context
        memory_context = self.memory.get_memory_context()
        if memory_context:
            parts.append(f"\n\n# Memory Context\n{memory_context}")
            
        # 4. Long-term Tasks
        from .agent_service import agent_service
        if agent_service and agent_service.task_manager:
            task_context = agent_service.task_manager.get_task_context()
            if task_context:
                parts.append(task_context)
                
        return "\n\n---\n\n".join(parts)
    
    def build_messages(
        self,
        history: List[Any], # List of BaseMessage or dicts
        current_message: str,
        rag_context: str = None,
        network_identity: str = None,
        recent_global_events: str = None,
        resident_memory_context: str = None,
        source: str = "user",
        name: str = "Agent",
        personality: str = "Professional and helpful",
        agent_language: str = "中文",
        channel: str = "resident",
        host_info: str = None
    ) -> List[BaseMessage]:
        """
        Build the complete message list for an LLM call.
        """
        messages: List[BaseMessage] = []

        # 1. System Prompt
        system_content = self.build_system_prompt(name=name, personality=personality, channel=channel, host_info=host_info)
        
        # Inject dynamic context (RAG + Network Identity) into System Prompt or as separate SystemMessages
        # To keep it clean, we add them as separate SystemMessages immediately after the main prompt
        messages.append(SystemMessage(content=system_content))
        
        # Add Language Instruction overrides
        messages.append(SystemMessage(content=f"IMPORTANT DIRECTIVE: You MUST generate all responses and communicate exclusively in the following language: {agent_language}. (Unless strictly quoting a source in another language)."))
        
        if resident_memory_context:
            messages.append(SystemMessage(content=f"Your Internal Memory (Semantic & Working):\n{resident_memory_context}"))

        if network_identity:
            messages.append(SystemMessage(content=f"Your Network Identity:\n{network_identity}"))
            
        if recent_global_events:
            messages.append(SystemMessage(content=f"Recent Global Events (Background Context outside this session):\n{recent_global_events}"))
            
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

        # 4. Self-Improvement Activator Hook
        activator_prompt = """<self-improvement-reminder>
After completing this task, evaluate if extractable knowledge emerged:
- Non-obvious solution discovered through investigation?
- Workaround for unexpected behavior?
- Project-specific pattern learned?
- Error required debugging to resolve?

If yes: Log to .learnings/ using the self-improvement skill format.
If high-value (recurring, broadly applicable): Consider skill extraction.
</self-improvement-reminder>"""
        messages.append(SystemMessage(content=activator_prompt))

        return messages
