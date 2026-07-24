"""Context builder for assembling agent prompts."""

import logging
from typing import Any

try:
    from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
except ImportError:
    class BaseMessage:
        def __init__(self, content: str): self.content = content
    class HumanMessage(BaseMessage): pass
    class SystemMessage(BaseMessage): pass

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
        agent_language: str = "中文",
    ) -> tuple[str, str, str]:
        """
        Build system prompt segments structured in 3 distinct layers for Prefix Caching:
        Returns: (static_head, semi_static_mid, dynamic_tail)
        """
        # --- LAYER 1: ABSOLUTE STATIC HEAD (99%+ Prefix Cache Parity) ---
        static_parts = []

        # 1. CORE IDENTITY & PERSONA
        static_parts.append(
            f"# AGENT NODE IDENTITY\n- **Name**: {name}\n- **Personality**: {personality}"
        )

        # 2. Language Directive
        static_parts.append(
            f"IMPORTANT DIRECTIVE: You MUST generate all responses and communicate exclusively in the following language: {agent_language}. (Unless strictly quoting a source in another language)."
        )

        # 3. Governing Protocol (Constitution)
        rules_text = community_config.get_all_rules_text()
        if rules_text:
            protocol_block = f"""# GOVERNING PROTOCOL (CONSTITUTION)
Below is the current community organization and election protocol. 
Reference these rules for all governance decisions, election proposals, and group management tasks.
```json
{rules_text[:15000]}
```"""
            static_parts.append(protocol_block)

        # 4. Skill Index (Sorted Keys for Deterministic Prefix)
        skill_index = self.skill_manager.get_skill_index()
        if skill_index:
            static_parts.append(f"# Available Skills\n{skill_index[:10000]}")

        # 5. Role & Channel Rules
        if channel == "p2p":
            role_block = """# CURRENT DOMAIN: Autonomous Peer-to-Peer Network
[URGENT ROLE AWARENESS] You are communicating directly with another machine Node in the network.
- **COMMUNICATION FIREWALL**: Do NOT report to your human owner (resident) in this channel.
- **NO CHINESE POLITE GREETINGS**: Do NOT use greetings like '居民，您好' or '報告居民'. 
- **NO DECORATIVE MARKDOWN**: Do NOT use markdown headers (###), bold headers, or report-style formatting in your 'Final Answer'.
- **RESPONSE MANDATE**: If the peer node asks a question or query (e.g., capability checks, search capabilities, node status), you MUST provide a concise technical answer and invoke `send_p2p_message` or return a non-empty final answer.
- **FINAL ANSWER DESTINATION**: Your 'Final Answer' is delivered DIRECTLY to the other machine node. It must be technical, objective, and brief.
- **TERMINATION**: ONLY output `[NO_RESPONSE_NEEDED]` if the incoming message is a pure system acknowledgment (e.g. 'ACK', 'OK', 'Received') that requires ZERO further response.
- **CRITICAL**: If you need instructions/reports from/to the resident, you **MUST MUST MUST** use the `ask_resident` tool. It is the ONLY private channel."""
            static_parts.append(role_block)
        else:
            role_block = """# CURRENT DOMAIN: Private User Interface
[ROLE AWARENESS] You are communicating directly with your human Resident/Owner.
- **ACTION MANDATE**: If you inform the resident that you are going to perform an action (e.g. sending a P2P message, creating a group, querying network topology, searching literature, writing code, reading files), you MUST invoke the corresponding tool (e.g., `read_file`, `write_file`, `execute_shell_command`, `send_p2p_message`) in the exact same turn.
- **CODING & FILE TASKS**: When tasked with writing Python programs or analyzing data files (such as CSV/metabolic data), use `list_dir`, `read_file`, `write_file`, `edit_file`, or `execute_shell_command` IMMEDIATELY to inspect files, write Python scripts, and run analysis. Do NOT just say "让我查看" or "现在为您编写" without attaching the tool call.
- **NO PLACEHOLDER PROMISES**: NEVER output text like "现在我来发送..." or "让我使用Python读取..." without actually attaching the tool call in the response."""
            static_parts.append(role_block)

        # 6. Conversation Context Awareness
        if channel == "p2p" and session_id:
            chat_name = chat_name or "Unknown"
            is_group = chat_name != "Unknown"
            if is_group:
                group_block = f"""# CONVERSATION CONTEXT: GROUP CHAT ({chat_name})
- To reply to all, use `send_p2p_message` with `id: "{session_id}"` and `type: "GROUP"`."""
                static_parts.append(group_block)
            else:
                static_parts.append(f"# CONVERSATION CONTEXT: DIRECT MESSAGE with {session_id}")

        # 7. Self-Improvement Activator (Static Reminder)
        activator_prompt = """<self-improvement-reminder>
After completing this task, evaluate if extractable knowledge emerged:
- Non-obvious solution discovered through investigation?
- Workaround for unexpected behavior?
- Project-specific pattern learned?
- Error required debugging to resolve?

If yes: Log to .learnings/ using the self-improvement skill format.
If high-value (recurring, broadly applicable): Consider skill extraction.
</self-improvement-reminder>"""
        static_parts.append(activator_prompt)

        static_head = "\n\n---\n\n".join(static_parts)

        # --- LAYER 2: SEMI-STATIC MID (Memory & Task Snapshots) ---
        semi_static_parts = []

        # 1. Memory Context Snapshot (MEMORY.md + USER.md)
        memory_context = self.memory.get_memory_context()
        if memory_context:
            semi_static_parts.append(f"# Memory Context (MEMORY.md & USER.md)\n{memory_context[:20000]}")

        # 2. Long-term Tasks
        if self.task_manager:
            task_context = self.task_manager.get_task_context()
            if task_context:
                semi_static_parts.append(task_context)

        semi_static_mid = "\n\n---\n\n".join(semi_static_parts) if semi_static_parts else ""

        # --- LAYER 3: DYNAMIC TAIL (Time & Host Info) ---
        dynamic_parts = []
        from datetime import datetime

        current_time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        time_block = f"""# Current System Time
The current real-world local server time is: **{current_time_str}**.
Use this absolute time for any date calculations or temporal awareness."""
        dynamic_parts.append(time_block)

        if host_info:
            dynamic_parts.append(host_info)

        dynamic_tail = "\n\n---\n\n".join(dynamic_parts)

        return static_head, semi_static_mid, dynamic_tail

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
        Build complete message list with strict 3-layer prefix caching layout.
        """
        messages: list[BaseMessage] = []

        # 1. Obtain system prompt layers
        static_head, semi_static_mid, dynamic_tail = self.build_system_prompt(
            name=name,
            personality=personality,
            channel=channel,
            host_info=host_info,
            session_id=session_id,
            chat_name=chat_name,
            agent_language=agent_language,
        )

        system_blocks = [static_head]

        if semi_static_mid:
            system_blocks.append(semi_static_mid)

        if resident_memory_context:
            system_blocks.append(
                f"Your Internal Memory (Semantic & Working):\n{resident_memory_context[:10000]}"
            )

        if network_identity:
            system_blocks.append(f"Your Network Identity:\n{network_identity}")

        # Dynamic Tail Blocks (RAG, Governance, Time, Pending Reply)
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

        system_blocks.append(dynamic_tail)

        # Single compiled SystemMessage placed at index 0
        messages.append(SystemMessage(content="\n\n---\n\n".join(system_blocks)))

        # 2. History (Conversation flow)
        if history:
            messages.extend(history)

        # 3. Current User Message
        messages.append(HumanMessage(content=f"Message from {source}: {current_message}"))

        return messages
