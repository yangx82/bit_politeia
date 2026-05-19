"""Context builder for assembling agent prompts."""

import logging
from typing import Any

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from ..services.community_config import community_config
from ..services.memory_store import memory_store
from ..services.skill_manager import skill_manager

logger = logging.getLogger(__name__)


class ContextBuilder:
    """
    Builds the context (system prompt + messages) for the agent.

    Assembles memory, skills, and conversation history into a coherent prompt for the LLM.
    """

    def __init__(self, task_manager=None):
        self.memory = memory_store
        self.skill_manager = skill_manager
        self.task_manager = task_manager

    def build_system_prompt(
        self,
        name: str = "Agent",
        personality: str = "Professional and helpful",
        channel: str = "resident",
        host_info: str = None,
        session_id: str = None,
        chat_name: str = None,
    ) -> str:
        """
        Build the complete system prompt from core identity, memory, and skills.
        """
        parts = []

        # 1.6 Current Real-World Time
        from datetime import datetime

        current_time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        time_block = f"""# Current System Time
The current real-world local server time is: **{current_time_str}**.
Use this absolute time for any date calculations or temporal awareness."""
        parts.append(time_block)

        if host_info:
            parts.append(host_info)

        # 2. Skill Index (Progressive Disclosure) - Limit to 10k chars
        skill_index = self.skill_manager.get_skill_index()
        if skill_index:
            parts.append(f"\n\n# Available Skills\n{skill_index[:10000]}")

        # 3. Memory Context - Limit to 20k chars
        memory_context = self.memory.get_memory_context()
        if memory_context:
            parts.append(f"\n\n# Memory Context\n{memory_context[:20000]}")

        # 4. Long-term Tasks
        if self.task_manager:
            task_context = self.task_manager.get_task_context()
            if task_context:
                parts.append(task_context)

        # 5. Governing Protocol (Constitution) - INHERENT AWARENESS
        rules_text = community_config.get_all_rules_text()
        if rules_text:
            protocol_block = f"""# GOVERNING PROTOCOL (CONSTITUTION)
Below is the current community organization and election protocol. 
Reference these rules for all governance decisions, election proposals, and group management tasks.
```json
{rules_text[:15000]}
```"""
            parts.append(protocol_block)

        # ---------------------------------------------------------------------
        # CRITICAL RECENT INSTRUCTIONS (Placement here for high adherence)
        # ---------------------------------------------------------------------

        # 6. Role & Channel Awareness
        if channel == "p2p":
            role_block = """# CURRENT DOMAIN: Autonomous Peer-to-Peer Network
[URGENT ROLE AWARENESS] You are communicating directly with another machine Node in the network.
- **COMMUNICATION FIREWALL**: Do NOT report to your human owner (resident) in this channel.
- **NO CHINESE POLITE GREETINGS**: Do NOT use greetings like '居民，您好' or '報告居民'. 
- **NO DECORATIVE MARKDOWN**: Do NOT use markdown headers (###), bold headers, or report-style formatting in your 'Final Answer'.
- **FINAL ANSWER DESTINATION**: Your 'Final Answer' is delivered DIRECTLY to the other machine node. It must be technical, objective, and brief.
- **CRITICAL**: If you need instructions/reports from/to the resident, you **MUST MUST MUST** use the `ask_resident` tool. It is the ONLY private channel.
- **TERMINATION**: Output exactly `[NO_RESPONSE_NEEDED]` if the interaction is complete."""
            parts.append(role_block)
        else:
            role_block = """# CURRENT DOMAIN: Private User Interface
[ROLE AWARENESS] You are communicating directly with your human Resident/Owner.
- Explain your thoughts naturally and confirm actions."""
            parts.append(role_block)

        # 7. Conversation Context Awareness (Group vs Direct)
        if channel == "p2p" and session_id:
            chat_name = chat_name or "Unknown"
            is_group = chat_name != "Unknown"
            if is_group:
                group_block = f"""# CONVERSATION CONTEXT: GROUP CHAT ({chat_name})
- To reply to all, use `send_p2p_message` with `id: "{session_id}"` and `type: "GROUP"`."""
                parts.append(group_block)
            else:
                parts.append(f"# CONVERSATION CONTEXT: DIRECT MESSAGE with {session_id}")

        return "\n\n---\n\n".join(parts)

        return "\n\n---\n\n".join(parts)

    def build_messages(
        self,
        history: list[Any],  # List of BaseMessage or dicts
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
        host_info: str = None,
        session_id: str = None,
        chat_name: str = None,
        governance_context: str = None,
        pending_reply: str = None,
    ) -> list[BaseMessage]:
        """
        Build the complete message list for an LLM call.
        """
        # 1. Gather all System Prompt segments
        system_blocks = []

        system_content = self.build_system_prompt(
            name=name,
            personality=personality,
            channel=channel,
            host_info=host_info,
            session_id=session_id,
            chat_name=chat_name,
        )
        system_blocks.append(system_content)

        # Add Language Instruction overrides
        system_blocks.append(
            f"IMPORTANT DIRECTIVE: You MUST generate all responses and communicate exclusively in the following language: {agent_language}. (Unless strictly quoting a source in another language)."
        )

        if resident_memory_context:
            system_blocks.append(
                f"Your Internal Memory (Semantic & Working):\n{resident_memory_context[:10000]}"
            )

        if network_identity:
            system_blocks.append(f"Your Network Identity:\n{network_identity}")

        if recent_global_events:
            system_blocks.append(
                f"Recent Global Events (Background Context outside this session):\n{recent_global_events}"
            )

        if rag_context:
            system_blocks.append(f"Relevant Knowledge Context:\n{rag_context}")

        if governance_context:
            system_blocks.append(
                f"LIVE GOVERNANCE STATE (Active Elections/Proposals):\n{governance_context[:10000]}"
            )

        if pending_reply:
            system_blocks.append(
                f"# [PENDING REPLY INHIBITION]\nYou generated a reply within the last 5 minutes that has NOT been sent yet due to network rate-limiting policy:\n\n\"{pending_reply}\"\n\nYou are now being prompted by a NEW message. You can choose to update your pending reply (overwriting it) or ignore it. If you use 'send_p2p_message' again, the NEW content will be buffered and sent once the 5-minute cooldown expires."
            )

        # Self-Improvement Activator Hook
        activator_prompt = """<self-improvement-reminder>
After completing this task, evaluate if extractable knowledge emerged:
- Non-obvious solution discovered through investigation?
- Workaround for unexpected behavior?
- Project-specific pattern learned?
- Error required debugging to resolve?

If yes: Log to .learnings/ using the self-improvement skill format.
If high-value (recurring, broadly applicable): Consider skill extraction.
</self-improvement-reminder>"""
        system_blocks.append(activator_prompt)

        # Combine all system blocks into a single SystemMessage at the very beginning of the message list
        messages.append(SystemMessage(content="\n\n---\n\n".join(system_blocks)))

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
