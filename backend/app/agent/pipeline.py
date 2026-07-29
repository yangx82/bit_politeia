import sys
import site
import os

user_site = site.getusersitepackages()
if user_site and user_site not in sys.path:
    sys.path.insert(0, user_site)

import logging
from datetime import datetime, timezone
UTC = timezone.utc
from typing import Any

try:
    from pydantic import BaseModel
except ImportError:
    class BaseModel:
        def __init__(self, **kwargs):
            for k, v in kwargs.items():
                setattr(self, k, v)

logger = logging.getLogger(__name__)

from ..models.session import Session


class PipelineContext(BaseModel):
    """Holds state across the 6-stage execution pipeline."""

    session: Session
    input_message: Any  # InboundMessage

    # Internal reasoning
    thoughts: list[str] = []
    tool_calls: list[dict[str, Any]] = []
    tool_results: list[dict[str, Any]] = []

    # Output
    final_answer: str | None = None
    metadata: dict[str, Any] = {}

    # Control flags
    stop_execution: bool = False
    requires_approval: bool = False
    continuation_req: bool = False
    continuation_reason: str | None = None

    # In-flight Steering (/steer) support
    steer_instructions: list[str] = []
    steering_flag: bool = False

    # Execution Environment
    _sandbox: Any | None = None  # Lazy initialized sandbox

    def get_sandbox(self) -> Any:
        if not self._sandbox:
            from .sandbox import get_default_sandbox

            self._sandbox = get_default_sandbox()
        return self._sandbox


class PipelineStage:
    """Base class for pipeline stages."""

    async def run(self, context: PipelineContext, agent: Any):
        raise NotImplementedError()


try:
    from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
except ImportError:
    class BaseMessage:
        def __init__(self, content: str = "", **kwargs):
            self.content = content
            for k, v in kwargs.items(): setattr(self, k, v)
    class AIMessage(BaseMessage): pass
    class HumanMessage(BaseMessage): pass
    class SystemMessage(BaseMessage): pass
    class ToolMessage(BaseMessage): pass

from ..bus.events import OutboundMessage
from ..services.knowledge_base import knowledge_base
from ..services.p2p_service import p2p_service


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
        session_history = [
            msg for msg in effective_history if msg.session_id == context.input_message.session_id
        ]

        raw_lc_history = []
        for msg in session_history:
            if msg.sender == "agent":
                raw_lc_history.append(AIMessage(content=msg.content))
            else:
                raw_lc_history.append(HumanMessage(content=f"[{msg.sender}] {msg.content}"))

        # Inject compressed history summary if available (it has session_id='system'
        # so it won't be in session_history, but we want it as leading context)
        for msg in effective_history:
            if msg.id == "compressed-history-summary" and msg.content:
                raw_lc_history.insert(0, HumanMessage(content=msg.content))
                break

        # Hard window limit: prevent sending thousands of messages into context compression.
        # Older messages are preserved on disk (JSONL) and in compressed summaries.
        MAX_HISTORY_WINDOW = 200
        if len(raw_lc_history) > MAX_HISTORY_WINDOW:
            logger.info(
                f"Trimming session history from {len(raw_lc_history)} to last {MAX_HISTORY_WINDOW} messages for context pipeline."
            )
            # Keep first message (might be compressed summary) + recent window
            if raw_lc_history and "[COMPRESSED HISTORY SUMMARY]" in getattr(raw_lc_history[0], 'content', ''):
                raw_lc_history = [raw_lc_history[0]] + raw_lc_history[-(MAX_HISTORY_WINDOW - 1):]
            else:
                raw_lc_history = raw_lc_history[-MAX_HISTORY_WINDOW:]

        # b) Call the Universal ContextManager
        (
            optimized_history,
            task_id,
            lineage_msg,
        ) = await agent.context_manager.get_optimized_messages(
            session_id=context.input_message.session_id,
            query=agent_query,
            lc_history=raw_lc_history,
            channel=context.input_message.channel,
            force_compact=context.input_message.metadata.get("force_compact", False),
        )

        # Store detected/explicit focus for other stages
        context.metadata["active_task_id"] = task_id
        context.session.history_slice = optimized_history

        # 4. Extract Global Peripheral Awareness (The environment)
        # If focusing on a task, ignore raw chat noise from other sessions to save tokens.
        # Otherwise, keep a small window of recent activity for situational awareness.
        if task_id:
            # FOCUS MODE: Filter for high-priority/system events only
            interesting_types = [
                "system",
                "checkpoint",
                "transaction",
                "governance",
                "reputation",
                "event",
            ]
            global_events_raw = [
                msg
                for msg in effective_history
                if msg.session_id != context.input_message.session_id
                and (msg.msg_type in interesting_types or msg.sender == "system")
            ][-3:]  # Only take 3 high-priority updates
        else:
            # GENERAL MODE: Keep recent activity slice
            global_events_raw = [
                msg
                for msg in effective_history
                if msg.session_id != context.input_message.session_id
            ][-5:]

        recent_global_events = ""
        if global_events_raw:
            events_formatted = []
            for msg in global_events_raw:
                sender_label = "Me" if msg.sender == "agent" else msg.sender
                timestamp_str = msg.timestamp.strftime("%H:%M")  # Shorter timestamp
                events_formatted.append(
                    f"[{timestamp_str}] {sender_label} ({msg.msg_type}): {msg.content}"
                )
            recent_global_events = "\n".join(events_formatted)

        # 5. Build Final Prompt
        source_label = (
            f"P2P Peer (Node ID: {context.input_message.sender_id})"
            if context.input_message.channel == "p2p"
            else "Resident (Human User)"
        )
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
            agent_language=getattr(agent, "agent_language", "中文"),
            channel=context.input_message.channel,
            host_info=agent._get_host_info(),
            session_id=session_id,
            chat_name=chat_name,
            governance_context=gov_summary,
            pending_reply=context.session.metadata.get("pending_reply"),
        )


def _compact_messages_in_flight(messages: list[BaseMessage], aggressiveness: int = 1) -> list[BaseMessage]:
    """
    Emergency in-flight context compression when an LLM context token limit error is caught.
    - aggressiveness=1: Truncate large tool/human payloads (>1500 chars) and drop middle turns if history > 8 msgs.
    - aggressiveness=2: Ultra-aggressive truncation (>500 chars) and keep only SystemMessage + last 4 msgs.
    """
    if not messages:
        return messages

    sys_msg = messages[0] if isinstance(messages[0], SystemMessage) else None
    rest = messages[1:] if sys_msg else messages[:]

    char_limit = 1500 if aggressiveness == 1 else 500
    keep_recent = 8 if aggressiveness == 1 else 4

    pruned_rest = []
    for m in rest:
        content_str = str(getattr(m, "content", ""))
        if len(content_str) > char_limit:
            half = char_limit // 2
            truncated = (
                content_str[:half]
                + f"\n... [Payload truncated ({len(content_str)} chars -> {char_limit} chars) to fit token limit] ...\n"
                + content_str[-half:]
            )
            m_copy = m.model_copy() if hasattr(m, "model_copy") else m
            m_copy.content = truncated
            pruned_rest.append(m_copy)
        else:
            pruned_rest.append(m)

    if len(pruned_rest) > keep_recent:
        pruned_rest = [pruned_rest[0]] + pruned_rest[-(keep_recent - 1):]

    final_msgs = [sys_msg] + pruned_rest if sys_msg else pruned_rest
    return final_msgs


class PlanStage(PipelineStage):
    """Stage 2: Reasoning & Planning (LLM)."""

    async def run(self, context: PipelineContext, agent: Any):
        logger.info(f"[{context.session.session_id}] Stage: Plan")
        if not agent.llm:
            context.final_answer = "Agent LLM not configured."
            context.stop_execution = True
            return

        messages = context.metadata["messages"]

        response = None
        for attempt in range(3):
            try:
                response = await agent.llm.ainvoke(messages)
                context.metadata["last_response"] = response
                context.metadata["messages"] = messages
                break
            except Exception as e:
                err_msg = str(e)
                logger.error(f"LLM API Error during pipeline plan stage (attempt {attempt+1}/3): {err_msg}")

                is_context_limit_err = (
                    "202745" in err_msg
                    or "260096" in err_msg
                    or "range of input length" in err_msg.lower()
                    or "context_length_exceeded" in err_msg.lower()
                    or "too many tokens" in err_msg.lower()
                    or "maximum context length" in err_msg.lower()
                    or ("invalidparameter" in err_msg.lower() and "length" in err_msg.lower())
                )

                if is_context_limit_err and attempt < 2:
                    logger.warning(
                        f"[{context.session.session_id}] Context limit hit. "
                        f"Performing in-flight emergency compression (pass {attempt+1})..."
                    )
                    messages = _compact_messages_in_flight(messages, aggressiveness=attempt + 1)
                    continue

                if ("connection error" in err_msg.lower() or "connect" in err_msg.lower() or "timeout" in err_msg.lower()) and attempt < 2:
                    logger.warning(
                        f"[{context.session.session_id}] Transient LLM network error on attempt {attempt+1}/3: {err_msg}. Retrying in 2s..."
                    )
                    await asyncio.sleep(2)
                    continue

                if is_context_limit_err:
                    user_friendly_err = "LLM 限制提示：单次请求输入内容过长，超出模型 token 上限。系统已自动进行紧急压缩但仍超限，建议清理会话历史或分割长文本请求。"
                    context.continuation_req = False
                    context.continuation_reason = f"TOKEN_LENGTH_EXCEEDED: {err_msg}"
                elif "no models loaded" in err_msg.lower() or "lms load" in err_msg.lower():
                    user_friendly_err = "LLM 服务提示：当前 LM Studio 未加载任何模型。请在 LM Studio 软件的开发者页面加载模型，或使用 'lms load' 命令加载后重试。"
                    context.continuation_req = False
                    context.continuation_reason = "FATAL_NO_MODEL_LOADED"
                elif "failed to parse fc" in err_msg.lower() or "fc related info" in err_msg.lower():
                    user_friendly_err = "LLM 服务提示：SGLang 部署的模型解析工具调用失败（Failed to parse fc related info）。请确保启动 SGLang 服务时指定了正确的工具调用解析器参数（例如：--tool-call-parser qwen25 或 --tool-call-parser llama3）。"
                    context.continuation_req = False
                    context.continuation_reason = "FATAL_SGLANG_FC_PARSER_ERROR"
                elif "parallel_tool_calls" in err_msg.lower() or "parallel tool calls" in err_msg.lower():
                    user_friendly_err = "LLM 服务提示：当前部署的模型/服务端不支持并行工具调用（parallel_tool_calls）。请尝试关闭并行工具调用功能或检查服务端参数配置。"
                    context.continuation_req = False
                    context.continuation_reason = "FATAL_PARALLEL_TOOL_CALLS_UNSUPPORTED"
                elif "400" in err_msg and ("validation error" in err_msg.lower() or "bad request" in err_msg.lower()):
                    user_friendly_err = f"LLM 服务提示：请求参数验证失败（400 Bad Request）。若您使用的是 SGLang 部署的模型，请检查：1. 启动服务时是否指定了 --tool-call-parser 解析器；2. 当前模型是否支持工具调用（Function Calling）；3. 检查 SGLang 服务端的日志以获取具体参数报错信息。具体错误: {err_msg}"
                    context.continuation_req = False
                    context.continuation_reason = "FATAL_LLM_REQUEST_VALIDATION_ERROR"
                else:
                    user_friendly_err = f"Error communicating with LLM. (Triggered Ralph Wiggum auto-heal if enabled: {err_msg})"
                    context.continuation_req = True
                    context.continuation_reason = f"API_ERROR: {err_msg}"

                context.final_answer = user_friendly_err
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

            tags = [
                r"<thought>(.*?)</thought>",
                r"<reasoning>(.*?)</reasoning>",
                r"\[THOUGHT\](.*?)\[/THOUGHT\]",
            ]
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
                status="sent",
            )

            # CRITICAL FIX: Route thoughts to the active session so the user sees progress on their platform (Feishu, etc.)
            # Always mirror to gateway too for monitoring.
            is_intent_only = len(context.tool_calls) > 0 and not thought_content
            content_to_publish = str(display_thought)
            if is_intent_only:
                content_to_publish = f"**[计划执行中]**: {content_to_publish}"

            logger.info(f"Pipeline: Publishing thought to gateway & session {context.input_message.session_id}: {content_to_publish[:50]}...")
            
            # 1. Send to Gateway (for resident monitoring)
            await agent.message_bus.publish_outbound(OutboundMessage(
                channel="gateway",
                session_id="resident",
                content=content_to_publish,
                type="thought",
            ))

            # 2. ALSO send to current channel if it's not the resident (e.g. Feishu)
            # This ensures cross-channel users see the 'Agent is thinking' bubbles.
            if context.input_message.channel != "resident":
                await agent.message_bus.publish_outbound(OutboundMessage(
                    channel=context.input_message.channel,
                    session_id=context.input_message.session_id,
                    content=content_to_publish,
                    type="thought",
                ))

        if response.tool_calls:
            context.tool_calls = response.tool_calls
            messages.append(response)  # Add to dialog for next turn
        else:
            # Check for promised action without tool call (false completion)
            content_str = str(response.content or "").strip()
            action_promise_keywords = [
                "现在我来向", "现在我来", "马上向", "我来发送", "准备发送",
                "我来向它发送", "正在为您发送", "正在为您创建", "现在为您", "马上为您",
                "我来为您", "正在执行", "现在启动", "让我使用python", "让我读取",
                "让我查看", "让我先查看", "使用python读取", "编写完整的分析程序",
                "查看csv文件", "读取csv文件", "编写python程序", "我将使用", "准备为您编写",
                "下面开始", "让我们查看", "我将编写", "为您生成", "为您编写", "接下来我",
                "看我来", "写一个", "写一套", "代码如下", "程序如下", "现在开始"
            ]
            
            has_colon_end = content_str.endswith("：") or content_str.endswith(":")
            has_promised_action = any(kw in content_str.lower() for kw in action_promise_keywords) or has_colon_end
            retry_count = context.metadata.get("missing_tool_retry_count", 0)

            # Universal channel interception: Apply to ALL channels (Feishu, Resident, P2P, etc.)
            if has_promised_action and retry_count < 3:
                logger.warning(f"[{context.input_message.channel}] Detected promised action in LLM response without tool_calls: '{content_str[:60]}'. Re-prompting for tool invocation (attempt {retry_count+1}/3).")
                context.metadata["missing_tool_retry_count"] = retry_count + 1

                clean_response = AIMessage(
                    content=response.content,
                    additional_kwargs={k: v for k, v in response.additional_kwargs.items() if k != "tool_calls"},
                )
                reprompt_msg = HumanMessage(content="[System Directive: You stated in your text response that you would write code/perform an action (e.g. '现在我来编写...'), but you did not output any tool_call (e.g. delegate_coding_task, write_file, execute_shell_command, read_file). Please invoke the required tool or delegate_coding_task now immediately. Save any resident files under 'data/resident/'.]")

                clean_messages = list(messages)
                clean_messages.append(clean_response)
                clean_messages.append(reprompt_msg)

                try:
                    retry_response = await agent.llm.ainvoke(clean_messages)
                    if retry_response.tool_calls:
                        context.tool_calls = retry_response.tool_calls
                        context.metadata["messages"].append(clean_response)
                        context.metadata["messages"].append(reprompt_msg)
                        context.metadata["messages"].append(retry_response)
                        return
                except Exception as retry_err:
                    logger.error(f"Error during missing tool re-prompting: {retry_err}")
                    if "JSON format" in str(retry_err) or "400" in str(retry_err):
                        try:
                            logger.info("Attempting fallback tool call prompt with stripped context...")
                            fallback_messages = [
                                clean_messages[0],  # System message
                                HumanMessage(content=f"The user wants you to fulfill their request. You previously stated an intention to act: '{content_str[:100]}'. Please invoke the required tool (delegate_coding_task, write_file, execute_shell_command, read_file, etc.) now to execute this action. Save resident files under data/resident/.")
                            ]
                            fallback_resp = await agent.llm.ainvoke(fallback_messages)
                            if fallback_resp.tool_calls:
                                context.tool_calls = fallback_resp.tool_calls
                                context.metadata["messages"].append(fallback_resp)
                                return
                        except Exception as fb_err:
                            logger.error(f"Fallback missing tool prompt also failed: {fb_err}")

            # Verify-on-Stop Gate: Check if resident code was modified or mentioned but unverified
            verify_stop_retry_count = context.metadata.get("verify_stop_retry_count", 0)
            user_query = str(context.input_message.content or "").lower()
            code_task_keywords = ["编写", "修改", "脚本", "代码", "程序", "metabolic", "cage", "analysis", ".py", "python", ".m", "matlab"]
            is_code_related_task = any(kw in user_query for kw in code_task_keywords)

            if is_code_related_task and verify_stop_retry_count < 1:
                # Inspect recent messages for verification tools
                recent_tool_names = []
                for m in messages[-10:]:
                    if isinstance(m, AIMessage) and getattr(m, "tool_calls", None):
                        for tc in m.tool_calls:
                            recent_tool_names.append(tc.get("name") if isinstance(tc, dict) else getattr(tc, "name", ""))
                
                has_verified = (
                    "check_python_syntax" in recent_tool_names 
                    or "verify_file_exists" in recent_tool_names 
                    or "delegate_coding_task" in recent_tool_names
                    or "read_file" in recent_tool_names
                    or "write_file" in recent_tool_names
                    or "execute_shell_command" in recent_tool_names
                )
                if not has_verified:
                    logger.warning(f"Verify-on-Stop: Code-related task detected without syntax/file verification in recent turns. Issuing verification prompt.")
                    context.metadata["verify_stop_retry_count"] = verify_stop_retry_count + 1
                    
                    verify_prompt_msg = HumanMessage(
                        content="[System Verification Gate: You are completing a coding/script task. Please run 'verify_file_exists' or 'check_python_syntax' on the target file under 'data/resident/' now (or delegate_coding_task) to verify file existence and syntax before concluding.]"
                    )
                    clean_messages = list(messages)
                    clean_messages.append(verify_prompt_msg)
                    try:
                        v_response = await agent.llm.ainvoke(clean_messages)
                        if v_response.tool_calls:
                            context.tool_calls = v_response.tool_calls
                            context.metadata["messages"].append(verify_prompt_msg)
                            context.metadata["messages"].append(v_response)
                            return
                        elif v_response.content:
                            # Use LLM's verification response content if no tool calls were generated
                            context.final_answer = str(v_response.content).strip()
                            context.stop_execution = True
                            return
                    except Exception as v_err:
                        logger.error(f"Error during verify-on-stop prompting: {v_err}")

            # Ensure final_answer is never empty if response content exists
            final_text = str(response.content or "").strip()
            if not final_text and context.thoughts:
                final_text = context.thoughts[-1]
            context.final_answer = final_text
            context.stop_execution = True


class ExecuteStage(PipelineStage):
    """Stage 3: Action Execution (Tools)."""

    async def run(self, context: PipelineContext, agent: Any):
        logger.info(f"[{context.session.session_id}] Stage: Execute")
        if not context.tool_calls:
            return

        messages = context.metadata["messages"]

        for tool_call in context.tool_calls:
            # In-flight Steering Check Point
            if context.stop_execution:
                logger.info(f"[{context.session.session_id}] Pipeline execution stopped by user interrupt.")
                break

            if context.steer_instructions:
                steer_text = "\n".join(context.steer_instructions)
                context.steer_instructions = []
                context.steering_flag = False

                logger.info(f"[{context.session.session_id}] In-flight Steering Intercepted: {steer_text}")

                steer_notice = f"**[✋ 接收到行中纠偏指令]**: {steer_text}\n已中断后续工具链，正在重新规划方案..."
                await agent.message_bus.publish_outbound(
                    OutboundMessage(
                        channel="gateway",
                        session_id=context.input_message.session_id,
                        content=steer_notice,
                        type="thought",
                    )
                )

                # Inject steering directive into messages history
                steer_msg = HumanMessage(content=f"[居民行中纠偏指令]: {steer_text}")
                messages.append(steer_msg)

                # Clear remaining tool calls & re-trigger PlanStage with updated context
                context.tool_calls = []
                await PlanStage().run(context, agent)
                return

            tool_name = tool_call["name"]
            args = tool_call["args"]
            tool_call_id = tool_call["id"]

            # Emit Tool Call Event
            # Emit Tool Call Event - Unified Log
            # We send to the current session so the specific channel sees the tool invoking bubble
            tool_msg = OutboundMessage(
                channel="gateway",
                session_id=context.input_message.session_id,
                content=f"Invoking {tool_name} with {args}",
                type="tool_call",
                metadata={"tool": tool_name, "args": args},
            )
            await agent.message_bus.publish_outbound(tool_msg)

            if context.input_message.channel != "resident":
                await agent.message_bus.publish_outbound(OutboundMessage(
                    channel=context.input_message.channel,
                    session_id=context.input_message.session_id,
                    content=f"Invoking {tool_name}...",
                    type="tool_call",
                    metadata={"tool": tool_name, "args": args},
                ))

            try:
                # HEARTBEAT: Notify user/network before invoking slow tools
                slow_tools = [
                    "execute_shell_command",
                    "academic_research",
                    "submit_code_fix",
                    "repair_code",
                ]
                if tool_name in slow_tools:
                    heartbeat_msg = f"**[執行中]**: 正在啟動 {tool_name}，這可能需要一點時間..."
                    await agent.message_bus.publish_outbound(
                        OutboundMessage(
                            channel="gateway",
                            session_id=context.input_message.session_id,
                            content=heartbeat_msg,
                            type="thought",
                        )
                    )

                # Actual Tool Execution
                if tool_name not in agent.tools_map:
                    result = f"Error: Tool {tool_name} not found."
                else:
                    tool_func = agent.tools_map[tool_name]
                    result = await tool_func.ainvoke(args)

                # Record result
                context.tool_results.append(
                    {"tool": tool_name, "id": tool_call_id, "output": str(result)}
                )

                messages.append(ToolMessage(content=str(result), tool_call_id=tool_call_id))
            except Exception as e:
                logger.error(f"Tool {tool_name} failed: {e}")
                messages.append(
                    ToolMessage(content=f"Execution Error: {e!s}", tool_call_id=tool_call_id)
                )

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
                success_list = [
                    r["tool"]
                    for r in context.tool_results
                    if "error" not in r or not r.get("error")
                ]
                error_list = [
                    f"{r['tool']} ({r.get('error')})"
                    for r in context.tool_results
                    if r.get("error")
                ]

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
                sensitive_keywords = [
                    "居民",
                    "指示",
                    "汇报",
                    "请示",
                    "Owner",
                    "Resident",
                    "報告",
                    "請示",
                ]
                if any(kw in confirmation for kw in sensitive_keywords):
                    logger.warning(
                        f"[{context.session.session_id}] Privacy Breach Detected: Intercepting Resident-specific content in P2P channel."
                    )

                    # REROUTE original content to Resident Channel as a private thought
                    await agent.message_bus.publish_outbound(
                        OutboundMessage(
                            channel="gateway",
                            session_id="resident",
                            content=f"[AUTO-REDIRECTED PRIVACY ALERT]: The agent attempted to send the following to a P2P ID {context.session.session_id}:\n\n{confirmation}",
                            type="thought",
                        )
                    )

                    # TAG metadata for visibility
                    context.metadata["privacy_breach_suppressed"] = True

                    # FORCEFULLY TRUNCATE the message sent to the P2P group
                    confirmation = "[SECURITY SUPPRESSION: Internal report misrouted. Please check Resident tab for details.]"

            # 1.6 P2P Outbound Fallback Delivery: Ensure peer receives message if tool call was omitted
            if context.input_message.channel == "p2p" and confirmation and "[NO_RESPONSE_NEEDED]" not in confirmation:
                p2p_tool_called = any(r.get("tool") == "send_p2p_message" for r in context.tool_results)
                if not p2p_tool_called and hasattr(agent, "send_p2p_message"):
                    logger.info(f"[{context.session.session_id}] P2P Fallback Delivery: Auto-routing final answer via send_p2p_message.")
                    target_id = context.input_message.session_id or context.input_message.sender_id
                    try:
                        msg_kind = "group" if context.input_message.session_id and "group" in context.input_message.session_id.lower() else "direct"
                        await agent.send_p2p_message(
                            recipient_id=target_id,
                            content=confirmation,
                            msg_type=msg_kind
                        )
                    except Exception as err:
                        logger.error(f"P2P Fallback Delivery failed: {err}")

            # 2. Always mirror to Gateway for Observability
            if confirmation:
                await agent.message_bus.publish_outbound(
                    OutboundMessage(
                        channel="gateway",
                        session_id=context.input_message.session_id,
                        content=confirmation,
                        type="agent_message",
                    )
                )

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
        if not hasattr(agent, "task_manager") or not agent.task_manager:
            return

        terminal_tasks = []
        now_utc = datetime.now(UTC)
        for t in agent.task_manager.tasks.values():
            if t.status in ["completed", "failed"]:
                t_upd = t.updated_at
                # Add awareness guard for legacy naive timestamps
                if t_upd.tzinfo is None:
                    t_upd = t_upd.replace(tzinfo=UTC)
                if (now_utc - t_upd).total_seconds() < 300:
                    terminal_tasks.append(t)

        for task in terminal_tasks:
            if task.lessons_learned:
                continue  # Already processed or provided

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
                lesson_msg = await agent.llm.ainvoke([HumanMessage(content=prompt)])
                task.lessons_learned = lesson_msg.content
                logger.info(f"Retrospective for task '{task.goal}': {task.lessons_learned}")

                # Push task retrospective to Semantic Memory
                if agent.resident_memory and hasattr(task, 'lessons_learned'):
                    agent.resident_memory.log_interaction(
                        sender="system",
                        content=f"Retrospective for '{task.goal}': {task.lessons_learned}",
                        msg_type="moderation",
                        status="sent",
                    )
            except Exception as e:
                logger.error(f"Failed to generate task retrospective: {e}")

        # 2. Self-Healing Skill Subsystem: Check if complex code/repair task succeeded and auto-learn
        user_content = str(context.input_message.content or "").lower()
        if any(kw in user_content for kw in ["报错", "修改", "调试", "程序", "代码", ".py", ".m", "script"]):
            if context.tool_results and any(r.get("tool") in ["write_file", "edit_file", "execute_shell_command", "check_python_syntax"] for r in context.tool_results):
                try:
                    from pathlib import Path
                    auto_skills_dir = Path("backend/skills/auto_learned")
                    auto_skills_dir.mkdir(parents=True, exist_ok=True)
                    timestamp_slug = datetime.now().strftime("%Y%m%d_%H%M%S")
                    skill_file = auto_skills_dir / f"learned_experience_{timestamp_slug}.md"

                    tool_names = ", ".join([r.get("tool", "") for r in context.tool_results])
                    skill_card = f"""# Learned Experience Card ({datetime.now().strftime("%Y-%m-%d")})

## 🎯 Target Task / Request
{context.input_message.content[:300]}

## 🛠️ Actions & Tools Executed
{tool_names}

## 💡 Outcome & Summary
{context.final_answer[:500] if context.final_answer else "Task executed and verified."}
"""
                    skill_file.write_text(skill_card, encoding="utf-8")
                    logger.info(f"RetrospectiveStage: Generated self-healing skill card at {skill_file}")

                    # Push self-healing experience summary to Semantic Memory
                    if agent.resident_memory:
                        agent.resident_memory.log_interaction(
                            sender="system",
                            content=f"Self-Healing Experience Learned: {context.input_message.content[:200]} (Tools: {tool_names})",
                            msg_type="moderation",
                            status="sent",
                        )
                except Exception as e:
                    logger.error(f"Failed to generate self-healing skill card: {e}")
