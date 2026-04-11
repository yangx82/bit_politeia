import logging
import uuid
from datetime import datetime, timezone
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
    continuation_req: bool = False
    continuation_reason: Optional[str] = None
    
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
            
        rag_context = knowledge_base.retrieve_local_context(agent_query)
        context.metadata["rag_context"] = rag_context
        
        # 2. Retrieve P2P Network Context
        my_id = p2p_service.local_node.node_id if p2p_service.local_node else "unknown"
        my_groups = list(p2p_service.local_node.group_ids) if p2p_service.local_node else []
        
        # PROACTIVE TOPOLOGY INJECTION: Give the agent awareness of OTHER nodes
        network_status = p2p_service.get_network_status()
        peers_info = ""
        if network_status and "nodes" in network_status:
            peer_list = []
            for node_id, node_data in network_status["nodes"].items():
                if node_id != my_id:
                    peer_list.append(f"- {node_data.get('name', 'Unknown')}: {node_id}")
            if peer_list:
                peers_info = "\nAvailable Peers in Network:\n" + "\n".join(peer_list)
        
        network_identity = f"- Node ID: {my_id}\n- My Groups: {my_groups}\n- My Monitoring Research Focus: {agent.research_field}{peers_info}"
        context.metadata["network_identity"] = network_identity

        # 4. Retrieve Live Governance Context (Active Elections/Proposals)
        from ..services.agent_service import agent_service
        elections = await agent_service.get_elections()
        active_elections = [e for e in elections if e.get("is_active")]
        
        # Build governance summary for prompt injection
        gov_summary = ""
        if active_elections:
            gov_summary = "\n### Active Elections:\n"
            for e in active_elections:
                tally = e.get("tally", {})
                gov_summary += f"- [{e.get('election_type', 'Election')}] ID: {e.get('election_id', 'Unknown')} (Ends in {e.get('duration_minutes', '?')} min). Participation: {tally.get('participation_rate', 0)}%\n"
        else:
            gov_summary = "\nNo active elections or proposals currently."
            
        context.metadata["governance_context"] = gov_summary

        # 3. Build Optimized History & Mission Focus (ContextManager)
        effective_history = agent.history[:]
        while effective_history and effective_history[-1].content == agent_query:
            effective_history.pop()
            
        # a) Prepare raw session history for the ContextManager
        session_history = [msg for msg in effective_history if msg.session_id == context.input_message.session_id]
        
        raw_lc_history = []
        for msg in session_history:
            if msg.sender == "agent":
                raw_lc_history.append(AIMessage(content=msg.content))
            else:
                raw_lc_history.append(HumanMessage(content=f"[{msg.sender}] {msg.content}"))
                
        # b) Call the Universal ContextManager
        optimized_history, task_id, lineage_msg = await agent.context_manager.get_optimized_messages(
            session_id=context.input_message.session_id,
            query=agent_query,
            lc_history=raw_lc_history
        )
        
        # Store detected/explicit focus for other stages
        context.metadata["active_task_id"] = task_id
        context.session.history_slice = optimized_history
        
        # 4. Extract Global Peripheral Awareness (The environment)
        # If focusing on a task, ignore raw chat noise from other sessions to save tokens.
        # Otherwise, keep a small window of recent activity for situational awareness.
        if task_id:
            # FOCUS MODE: Filter for high-priority/system events only
            interesting_types = ["system", "checkpoint", "transaction", "governance", "reputation", "event"]
            global_events_raw = [
                msg for msg in effective_history 
                if msg.session_id != context.input_message.session_id 
                and (msg.msg_type in interesting_types or msg.sender == "system")
            ][-3:] # Only take 3 high-priority updates
        else:
            # GENERAL MODE: Keep recent activity slice
            global_events_raw = [msg for msg in effective_history if msg.session_id != context.input_message.session_id][-5:]
            
        recent_global_events = ""
        if global_events_raw:
            events_formatted = []
            for msg in global_events_raw:
                sender_label = "Me" if msg.sender == "agent" else msg.sender
                timestamp_str = msg.timestamp.strftime("%H:%M") # Shorter timestamp
                events_formatted.append(f"[{timestamp_str}] {sender_label} ({msg.msg_type}): {msg.content}")
            recent_global_events = "\n".join(events_formatted)

        # 5. Build Final Prompt
        source_label = f"P2P Peer (Node ID: {context.input_message.sender_id})" if context.input_message.channel == "p2p" else "Resident (Human User)"
        peer_id = context.input_message.sender_id
        
        # Combine base memory with mission-specific lineage
        base_memory = agent.resident_memory.get_full_context_text(peer_id=peer_id)
        full_memory_context = f"{lineage_msg}\n{base_memory}" if lineage_msg else base_memory

        # Resolve Chat Name
        session_id = context.input_message.session_id
        chat_name = "Unknown"
        network_status = p2p_service.get_network_status()
        if network_status and "groups" in network_status:
            if session_id in network_status["groups"]:
                chat_name = network_status["groups"][session_id].get("name", "Unknown Group")

        context.metadata["messages"] = agent.context_builder.build_messages(
            history=optimized_history, 
            current_message=agent_query,
            rag_context=rag_context,
            network_identity=network_identity,
            recent_global_events=recent_global_events,
            resident_memory_context=full_memory_context,
            source=source_label,
            name=agent.name,
            personality=agent.personality,
            agent_language=getattr(agent, 'agent_language', '中文'),
            channel=context.input_message.channel,
            host_info=agent._get_host_info(),
            session_id=session_id,
            chat_name=chat_name,
            governance_context=gov_summary,
            pending_reply=context.session.metadata.get("pending_reply")
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
        # from ..services.agent_service import p2p_logger
        # p2p_logger.info(f"\n[PIPELINE] Sense Messages:\n{messages}\n" + "-"*50)
        # One turn of the ReAct loop
        try:
            response = await agent.llm.ainvoke(messages)
            context.metadata["last_response"] = response
        except Exception as e:
            logger.error(f"LLM API Error during pipeline plan stage: {e}")
            context.final_answer = f"Error communicating with LLM. (Triggered Ralph Wiggum auto-heal if enabled: {str(e)})"
            context.continuation_req = True
            context.continuation_reason = f"API_ERROR: {str(e)}"
            context.stop_execution = True
            return
        
        # Extract Reasoning/Thought Content
        thought_content = ""
        
        # 1. Check for dedicated reasoning fields
        if "reasoning_content" in response.additional_kwargs:
            thought_content = response.additional_kwargs["reasoning_content"]
        elif hasattr(response, "reasoning_content") and response.reasoning_content:
            thought_content = response.reasoning_content
        elif "thought" in response.additional_kwargs:
             thought_content = response.additional_kwargs["thought"]
             
        # 2. Extract from XML-style tags in content (for DeepSeek/R1 models)
        if not thought_content and response.content:
            import re
            tags = [r"<thought>(.*?)</thought>", r"<reasoning>(.*?)</reasoning>", r"\[THOUGHT\](.*?)\[/THOUGHT\]"]
            for tag in tags:
                match = re.search(tag, response.content, re.DOTALL | re.IGNORECASE)
                if match:
                    thought_content = match.group(1).strip()
                    # Clean up the original content to remove the thought block
                    # response.content = re.sub(tag, "", response.content, flags=re.DOTALL | re.IGNORECASE).strip()
                    break

        # If explicitly missing reasoning field, use content as thought if tool_calls are present
        if not thought_content and response.tool_calls and response.content:
            thought_content = response.content

        # Emit Thought
        display_thought = thought_content or response.content
        
        # # DEBUG: User suggested to set a default if still empty to verify UI
        # if not display_thought:
        #     display_thought = "No thought content (Debug)!"

        if display_thought:
            context.thoughts.append(str(display_thought))
            context.session.message_count += 1
            
            # DIMENSION 4: Subject Separation - Log to Agent Journal
            agent.resident_memory.log_interaction(
                sender="agent",
                content=str(display_thought),
                msg_type="agent",
                session_id=context.input_message.session_id,
                status="sent"
            )

            # CRITICAL FIX: Distinguish between internal reasoning and premature intents.
            # If tool calls are present, the non-reasoning content is an 'Intent' (e.g., "I will send it").
            # Label it so the user knows it's currently in progress.
            is_intent_only = len(context.tool_calls) > 0 and not thought_content
            content_to_publish = str(display_thought)
            if is_intent_only:
                content_to_publish = f"**[计划执行中]**: {content_to_publish}"
            
            logger.info(f"Pipeline: Publishing thought to gateway: {content_to_publish[:50]}...")
            out_msg = OutboundMessage(
                channel="gateway", 
                session_id="resident", # ALWAYS route thoughts to resident for privacy
                content=content_to_publish,
                type="thought"
            )
            await agent.message_bus.publish_outbound(out_msg)

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
            # Emit Tool Call Event - Internal Log
            out_msg = OutboundMessage(
                channel="gateway",
                session_id=context.input_message.session_id,
                content=f"Invoking {tool_name} with {args}",
                type="tool_call",
                metadata={"tool": tool_name, "args": args}
            )
            # print(f"[DEBUG-AG] Publishing Tool Call: {tool_name} to {out_msg.channel}")
            await agent.message_bus.publish_outbound(out_msg)

            try:
                # HEARTBEAT: Notify user/network before invoking slow tools
                slow_tools = ["execute_shell_command", "academic_research", "submit_code_fix", "repair_code"]
                if tool_name in slow_tools:
                    heartbeat_msg = f"**[執行中]**: 正在啟動 {tool_name}，這可能需要一點時間..."
                    await agent.message_bus.publish_outbound(OutboundMessage(
                        channel="gateway",
                        session_id=context.input_message.session_id,
                        content=heartbeat_msg,
                        type="thought"
                    ))

                # Actual Tool Execution
                if tool_name not in agent.tools_map:
                    result = f"Error: Tool {tool_name} not found."
                else:
                    tool_func = agent.tools_map[tool_name]
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
        if context.final_answer or context.tool_results:
            # 1. Generate factual confirmation if tools were executed
            confirmation = context.final_answer or ""
            if context.tool_results:
                success_list = [r["tool"] for r in context.tool_results if "error" not in r or not r.get("error")]
                error_list = [f"{r['tool']} ({r.get('error')})" for r in context.tool_results if r.get("error")]
                
                status_suffix = ""
                if success_list:
                    status_suffix += f"\n\n**[✓ 执行成功]**: 已完成 {', '.join(success_list)}"
                if error_list:
                    status_suffix += f"\n\n**[✗ 执行失败]**: {'; '.join(error_list)}"
                
                # Append to agent's final answer if it's too brief or empty
                if not confirmation or len(confirmation) < 10:
                    confirmation = (confirmation + status_suffix).strip()
                else:
                    # Just mirror the status for visibility if the answer is already descriptive
                    pass

            # 1.5 Safety Filter for P2P Privacy: Active Interception & Redirection
            if context.input_message.channel == "p2p" and confirmation:
                sensitive_keywords = ["居民", "指示", "汇报", "请示", "Owner", "Resident", "報告", "請示"]
                if any(kw in confirmation for kw in sensitive_keywords):
                    logger.warning(f"[{context.session.session_id}] Privacy Breach Detected: Intercepting Resident-specific content in P2P channel.")
                    
                    # REROUTE original content to Resident Channel as a private thought
                    await agent.message_bus.publish_outbound(OutboundMessage(
                        channel="gateway",
                        session_id="resident",
                        content=f"[AUTO-REDIRECTED PRIVACY ALERT]: The agent attempted to send the following to a P2P ID {context.session.session_id}:\n\n{confirmation}",
                        type="thought"
                    ))
                    
                    # TAG metadata for visibility
                    context.metadata["privacy_breach_suppressed"] = True
                    
                    # FORCEFULLY TRUNCATE the message sent to the P2P group
                    confirmation = "[SECURITY SUPPRESSION: Internal report misrouted. Please check Resident tab for details.]"

            # 2. Always mirror to Gateway for Observability
            if confirmation:
                await agent.message_bus.publish_outbound(OutboundMessage(
                    channel="gateway",
                    session_id=context.input_message.session_id,
                    content=confirmation,
                    type="agent_message"
                ))

            # 2. Publish to source channel - DISABLED
            # Reason: The caller (agent_service.process_bus_message) already handles the reply.
            # Doing it here causes Duplicate Messages.
            # Also, this logic used sender_id instead of session_id, which was buggy for groups.
            # if context.input_message.channel != "resident":
            #     await agent.message_bus.publish_outbound(OutboundMessage(
            #         channel=context.input_message.channel,
            #         session_id=context.input_message.sender_id,
            #         content=context.final_answer
            #     ))

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

class RetrospectiveStage(PipelineStage):
    """Stage: Review completed/failed tasks and extract lessons."""
    async def run(self, context: PipelineContext, agent: Any):
        logger.info(f"[{context.session.session_id}] Stage: Retrospective")
        
        # Check if any tasks were completed or failed in this session
        # This requires the agent to have tool for marking task status.
        # For now, we scan for tasks that just reached terminal status.
        if not hasattr(agent, 'task_manager') or not agent.task_manager:
            return

        terminal_tasks = []
        now_utc = datetime.now(timezone.utc)
        for t in agent.task_manager.tasks.values():
            if t.status in ["completed", "failed"]:
                t_upd = t.updated_at
                # Add awareness guard for legacy naive timestamps
                if t_upd.tzinfo is None:
                    t_upd = t_upd.replace(tzinfo=timezone.utc)
                if (now_utc - t_upd).total_seconds() < 300:
                    terminal_tasks.append(t)
        
        for task in terminal_tasks:
            if task.lessons_learned:
                continue # Already processed or provided
            
            logger.info(f"Generating retrospective for task: {task.goal}")
            
            # Ask LLM to summarize lessons
            prompt = f"""
            You recently finished a long-term task: "{task.goal}" 
            Status: {task.status.value}
            Checkpoint: {task.checkpoint}
            
            Based on your final answer: "{context.final_answer}"
            
            Extract the core 'Lesson Learned' or 'Retrospective Summary'. 
            If it was a success, what were the key factors? 
            If it failed, what went wrong and how to avoid it?
            
            Format: A clear, concise paragraph (max 100 words).
            """
            
            try:
                from langchain_core.messages import HumanMessage
                resp = await agent.llm.ainvoke([HumanMessage(content=prompt)])
                task.lessons_learned = resp.content
                agent.task_manager.save_tasks()
                
                # Optional: Push to Semantic Memory
                if agent.resident_memory:
                    agent.resident_memory.log_interaction(
                        sender="system",
                        content=f"Retrospective for '{task.goal}': {task.lessons_learned}",
                        msg_type="moderation",
                        status="sent"
                    )
            except Exception as e:
                logger.error(f"Retrospective generation failed: {e}")
