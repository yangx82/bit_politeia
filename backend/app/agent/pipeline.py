import logging
import uuid
from datetime import datetime
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

from ..models.session import Session

class PipelineContext(BaseModel):
    """Holds state across the 6-stage execution pipeline."""
    session: Session
    input_message: Any  # InboundMessage
    
    # Internal reasoning
    thoughts: List[str] = []
    tool_calls: List[Dict[str, Any]] = []
    tool_results: List[Dict[str, Any]] = []
    
    # Output
    final_answer: Optional[str] = None
    metadata: Dict[str, Any] = {}
    
    # Control flags
    stop_execution: bool = False
    requires_approval: bool = False
    
    # Execution Environment
    _sandbox: Optional[Any] = None # Lazy initialized sandbox

    def get_sandbox(self) -> Any:
        if not self._sandbox:
            from .sandbox import get_default_sandbox
            self._sandbox = get_default_sandbox()
        return self._sandbox
    
class PipelineStage:
    """Base class for pipeline stages."""
    async def run(self, context: PipelineContext, agent: Any):
        raise NotImplementedError()

from ..services.knowledge_base import knowledge_base
from ..services.p2p_service import p2p_service
from ..bus.events import InboundMessage, OutboundMessage
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage, ToolMessage
import json

class SenseStage(PipelineStage):
    """Stage 1: Perception & Context Retrieval."""
    async def run(self, context: PipelineContext, agent: Any):
        logger.info(f"[{context.session.session_id}] Stage: Sense")
        
        # 1. Retrieve Context (Hybrid Search & Web)
        query = context.input_message.content
        agent_query = query
        # If it's a P2P message, it might be nested
        if isinstance(query, dict):
            agent_query = query.get("text", str(query))
            
        rag_context = knowledge_base.search_web_and_context(agent_query)
        context.metadata["rag_context"] = rag_context
        
        # 2. Retrieve P2P Network Context
        my_id = p2p_service.local_node.node_id if p2p_service.local_node else "unknown"
        my_groups = list(p2p_service.local_node.group_ids) if p2p_service.local_node else []
        network_identity = f"- Node ID: {my_id}\n- My Groups: {my_groups}\n- My Monitoring Research Focus: {agent.research_field}"
        context.metadata["network_identity"] = network_identity

        # 3. Build History Slice
        effective_history = agent.history[:]
        while effective_history and effective_history[-1].content == agent_query:
            effective_history.pop()
        
        recent_history = effective_history[-10:] if effective_history else []
        lc_history = []
        for msg in recent_history:
            if msg.sender == "agent":
                lc_history.append(AIMessage(content=msg.content))
            else:
                lc_history.append(HumanMessage(content=f"[{msg.sender}] {msg.content}"))
        
        context.session.history_slice = lc_history
        
        # Build initial messages for Plan stage
        context.metadata["messages"] = agent.context_builder.build_messages(
            history=lc_history, 
            current_message=agent_query,
            rag_context=rag_context,
            network_identity=network_identity,
            source=f"{context.input_message.channel} user {context.input_message.sender_id}"
        )

class PlanStage(PipelineStage):
    """Stage 2: Reasoning & Planning (LLM)."""
    async def run(self, context: PipelineContext, agent: Any):
        logger.info(f"[{context.session.session_id}] Stage: Plan")
        if not agent.llm:
            context.final_answer = "Agent LLM not configured."
            context.stop_execution = True
            return

        messages = context.metadata["messages"]
        
        # One turn of the ReAct loop
        response = await agent.llm.ainvoke(messages)
        context.metadata["last_response"] = response
        
        if agent.verbose_llm:
            print(f"\n[PIPELINE] Planning Response:\n{response.content}\n" + "-"*50)

        # Emit Thought
        if response.content:
            context.thoughts.append(response.content)
            context.session.message_count += 1
            await agent.message_bus.publish_outbound(OutboundMessage(
                channel=context.input_message.channel,
                chat_id=context.input_message.sender_id,
                content=str(response.content),
                type="thought"
            ))

        if response.tool_calls:
            context.tool_calls = response.tool_calls
            messages.append(response) # Add to dialog for next turn
        else:
            context.final_answer = response.content
            context.stop_execution = True

class ExecuteStage(PipelineStage):
    """Stage 3: Action Execution (Tools)."""
    async def run(self, context: PipelineContext, agent: Any):
        logger.info(f"[{context.session.session_id}] Stage: Execute")
        if not context.tool_calls:
            return

        messages = context.metadata["messages"]
        
        for tool_call in context.tool_calls:
            tool_name = tool_call["name"]
            args = tool_call["args"]
            tool_call_id = tool_call["id"]
            
            # Emit Tool Call Event
            await agent.message_bus.publish_outbound(OutboundMessage(
                channel=context.input_message.channel,
                chat_id=context.input_message.sender_id,
                content=f"Invoking {tool_name} with {args}",
                type="tool_call",
                metadata={"tool": tool_name, "args": args}
            ))

            try:
                # Actual Tool Execution
                if tool_name not in agent.tools_map:
                    result = f"Error: Tool {tool_name} not found."
                else:
                    tool_func = agent.tools_map[tool_name]
                    # Pass sandbox if the tool expects it or if we are using sandboxed tools
                    # tools_exec.py already uses get_default_sandbox(), which we should ideally
                    # redirect to this context's sandbox.
                    result = await tool_func.ainvoke(args)
                
                # Record result
                context.tool_results.append({
                    "tool": tool_name,
                    "id": tool_call_id,
                    "output": str(result)
                })
                
                messages.append(ToolMessage(
                    content=str(result),
                    tool_call_id=tool_call_id
                ))
            except Exception as e:
                logger.error(f"Tool {tool_name} failed: {e}")
                messages.append(ToolMessage(
                    content=f"Execution Error: {str(e)}",
                    tool_call_id=tool_call_id
                ))

        # Clear tool calls once executed
        context.tool_calls = []

class ConsolidateStage(PipelineStage):
    """Stage 4: Learning & Memory update."""
    async def run(self, context: PipelineContext, agent: Any):
        logger.info(f"[{context.session.session_id}] Stage: Consolidate")
        # For now, just ingestion handled in Archive or here
        # If any tool result worth consolidating immediately:
        pass

class NotifyStage(PipelineStage):
    """Stage 5: Communication (Sending response)."""
    async def run(self, context: PipelineContext, agent: Any):
        logger.info(f"[{context.session.session_id}] Stage: Notify")
        if context.final_answer:
            await agent.message_bus.publish_outbound(OutboundMessage(
                channel=context.input_message.channel,
                chat_id=context.input_message.sender_id,
                content=context.final_answer
            ))

class ArchiveStage(PipelineStage):
    """Stage 6: Persistence & Cleanup."""
    async def run(self, context: PipelineContext, agent: Any):
        logger.info(f"[{context.session.session_id}] Stage: Archive")
        # 1. Persistence: Session Service handles disk save
        from ..services.session_service import session_manager
        session_manager.save_session(context.session)
        
        # 2. Cleanup Sandbox
        if context._sandbox:
            context._sandbox.cleanup()
            
        logger.info(f"Session {context.session.session_id} archived and cleaned up.")
