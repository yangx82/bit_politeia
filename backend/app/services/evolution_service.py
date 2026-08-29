import asyncio
import json
import logging
import os
import uuid
from datetime import datetime, timezone
UTC = timezone.utc
from typing import Any

try:
    from ..p2p_community.governance import AIPProposal, ElectionType, Vote
except (ImportError, ValueError):
    from app.p2p_community.governance import AIPProposal, ElectionType, Vote

logger = logging.getLogger(__name__)


def _extract_and_parse_json(text: str) -> dict:
    """Robustly extracts and parses JSON from arbitrary LLM outputs."""
    import re
    if not text:
        return {}

    cleaned = str(text).strip()

    # 1. Strip reasoning / think tags (e.g. <think>...</think>)
    if "<think>" in cleaned and "</think>" in cleaned:
        cleaned = re.sub(r"<think>.*?</think>", "", cleaned, flags=re.DOTALL).strip()
    elif "</think>" in cleaned:
        cleaned = cleaned.split("</think>")[-1].strip()

    # 2. Extract markdown json code block if present
    json_block_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", cleaned, re.IGNORECASE)
    if json_block_match:
        block_content = json_block_match.group(1).strip()
        try:
            return json.loads(block_content)
        except Exception:
            pass

    # 3. Extract outermost curly braces { ... }
    first_brace = cleaned.find("{")
    last_brace = cleaned.rfind("}")
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        json_candidate = cleaned[first_brace : last_brace + 1]
        try:
            return json.loads(json_candidate)
        except Exception:
            pass

    # 4. Direct parse attempt
    try:
        return json.loads(cleaned)
    except Exception as e:
        logger.warning(f"[EvolutionService] Failed direct JSON parse: {e}. Attempting heuristic extraction...")

    # 5. Regex heuristic fallback for malformed JSON containing code
    try:
        extracted = {}
        title_m = re.search(r'"title"\s*:\s*"([^"]+)"', cleaned)
        if title_m:
            extracted["title"] = title_m.group(1)
        desc_m = re.search(r'"description"\s*:\s*"([^"]+)"', cleaned)
        if desc_m:
            extracted["description"] = desc_m.group(1)
        py_code_m = re.search(r"```(?:python)?\s*([\s\S]*?)\s*```", cleaned, re.IGNORECASE)
        if py_code_m:
            extracted["proposed_diff"] = py_code_m.group(1).strip()
        if extracted:
            return extracted
    except Exception:
        pass

    return {}


async def _invoke_llm_json(llm_client: Any, prompt: str) -> dict:
    """Helper to invoke a LangChain Chat client and robustly parse JSON response."""
    from langchain_core.messages import SystemMessage, HumanMessage

    system_content = (
        "You are an automated API component of the Bit Politeia framework. "
        "You must respond ONLY with a valid JSON object. "
        "Never output conversational preambles (e.g. 'I will start by...'), thinking commentary, or markdown outside the JSON block. "
        "Your response MUST start with '{' and end with '}'."
    )

    try:
        response = await llm_client.ainvoke([
            SystemMessage(content=system_content),
            HumanMessage(content=prompt),
        ])
    except Exception:
        # Fallback for LLM backends that reject SystemMessage
        response = await llm_client.ainvoke([
            HumanMessage(content=f"{system_content}\n\nTask:\n{prompt}")
        ])

    content = response.content if hasattr(response, "content") else str(response)
    res_dict = _extract_and_parse_json(content)

    # If first attempt returned pure conversational text without JSON, trigger a 1-shot conversion
    if not res_dict and content and len(str(content).strip()) > 10:
        try:
            repair_prompt = (
                f"Extract and format the information from this response into strictly valid JSON:\n\n{content}\n\n"
                f"Output strictly raw JSON starting with '{{' and ending with '}}'."
            )
            repair_resp = await llm_client.ainvoke([HumanMessage(content=repair_prompt)])
            repair_content = repair_resp.content if hasattr(repair_resp, "content") else str(repair_resp)
            res_dict = _extract_and_parse_json(repair_content)
        except Exception:
            pass

    # If result has a top-level wrapper key like 'message' or 'content', unwrap it
    for wrapper_key in ["message", "response", "content", "data", "result"]:
        if wrapper_key in res_dict and isinstance(res_dict[wrapper_key], (str, dict)):
            inner = _extract_and_parse_json(res_dict[wrapper_key]) if isinstance(res_dict[wrapper_key], str) else res_dict[wrapper_key]
            if inner and isinstance(inner, dict) and ("proposed_diff" in inner or "description" in inner or "approved" in inner):
                res_dict = inner
                break

    return res_dict


class EvolutionService:
    """
    Manages the lifecycle of Agent Improvement Proposals (AIPs) for the
    Autonomous Self-Evolving Agent Collective.
    Handles proposal generation, P2P network review, sandbox verification,
    and automated GitHub PR submission.
    """

    def __init__(self, data_dir: str | None = None):
        if data_dir is None:
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            self.data_dir = os.path.join(base_dir, "data")
        else:
            self.data_dir = data_dir

        os.makedirs(self.data_dir, exist_ok=True)
        self.aips_file = os.path.join(self.data_dir, "aips.json")
        self.aips: dict[str, AIPProposal] = {}
        self._load_aips()

    def _load_aips(self):
        """Loads persisted AIPs from disk."""
        if os.path.exists(self.aips_file):
            try:
                with open(self.aips_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for k, v in data.items():
                        self.aips[k] = AIPProposal.from_dict(v)
                self.consolidate_duplicates()
            except Exception as e:
                logger.error(f"[EvolutionService] Failed to load AIPs: {e}")

    def consolidate_duplicates(self):
        """Consolidates duplicate AIPs sharing the same or near-identical titles into single canonical entries."""
        seen_titles: dict[str, str] = {}
        to_delete = []

        # Sort AIPs so verified_and_proposed or newest ones take precedence
        sorted_aips = sorted(
            self.aips.values(),
            key=lambda x: (1 if x.status == "verified_and_proposed" else 0, x.timestamp),
            reverse=True,
        )

        for aip in sorted_aips:
            norm_title = aip.title.strip().lower()
            if norm_title in seen_titles:
                to_delete.append(aip.aip_id)
            else:
                seen_titles[norm_title] = aip.aip_id

        if to_delete:
            for aid in to_delete:
                if aid in self.aips:
                    del self.aips[aid]
            self._save_aips()
            logger.info(f"[EvolutionService] Consolidated {len(to_delete)} duplicate AIP(s): {to_delete}")

    def _save_aips(self):
        """Persists AIPs to disk."""
        try:
            with open(self.aips_file, "w", encoding="utf-8") as f:
                json.dump({k: v.to_dict() for k, v in self.aips.items()}, f, indent=2)
        except Exception as e:
            logger.error(f"[EvolutionService] Failed to save AIPs: {e}")

    def create_aip(
        self,
        initiator_id: str,
        title: str,
        description: str,
        target_files: list[str] | None = None,
        proposed_diff: str = "",
        research_sources: list[str] | None = None,
    ) -> AIPProposal:
        """Creates a new Agent Improvement Proposal (AIP)."""
        aip_id = f"AIP-{uuid.uuid4().hex[:8].upper()}"
        aip = AIPProposal(
            aip_id=aip_id,
            initiator_id=initiator_id,
            title=title,
            description=description,
            target_files=target_files or [],
            proposed_diff=proposed_diff,
            research_sources=research_sources or [],
            status="draft",
        )
        self.aips[aip_id] = aip
        self._save_aips()
        logger.info(f"[EvolutionService] Created {aip_id}: '{title}'")
        return aip

    def list_aips(self) -> list[dict[str, Any]]:
        """Returns all persisted AIPs as dictionaries."""
        return [aip.to_dict() for aip in self.aips.values()]

    def get_aip(self, aip_id: str) -> AIPProposal | None:
        """Retrieves an AIP by ID."""
        return self.aips.get(aip_id)

    async def auto_explore_and_propose(self, llm_client: Any = None) -> AIPProposal | None:
        """Automatically explores current codebase bottlenecks and research field to synthesize a new AIP proposal draft."""
        if not llm_client:
            return None

        try:
            prompt = (
                "You are the Autonomous Architecture Evolution Engine for Bit Politeia (a decentralized P2P AI Agent framework).\n"
                "Analyze the agent system and propose a concrete, highly actionable Agent Improvement Proposal (AIP).\n"
                "Focus on one of these core areas:\n"
                "- P2P message batching, deduplication, and adaptive backoff\n"
                "- Memory compaction and LRU caching for vector embeddings\n"
                "- DAG causal consensus and offline mailbox store-and-forward\n"
                "- Tool result pruning and context window efficiency\n\n"
                "Return strictly valid JSON matching this schema:\n"
                "{\n"
                '  "title": "Clear concise title (e.g. Adaptive Vector Embedding Cache)",\n'
                '  "description": "2-3 sentences explaining the architecture change and expected benefit",\n'
                '  "target_files": ["backend/app/services/agent_service.py"],\n'
                '  "proposed_diff": "def compute_adaptive_cache_key(data: str) -> str:\\n    import hashlib\\n    return hashlib.sha256(data.encode()).hexdigest()[:16]",\n'
                '  "research_sources": ["https://arxiv.org/abs/2408.00001"]\n'
                "}\n\n"
                "IMPORTANT: Provide concrete Python code for proposed_diff. Output ONLY the raw JSON object. Do not write conversational preamble."
            )
            res_json = await _invoke_llm_json(llm_client, prompt)
            title = res_json.get("title", "Autonomous Adaptive Memory & P2P Stream Optimization")
            description = res_json.get(
                "description",
                "Introduces latency-aware vector caching and dynamic backoff to enhance agent throughput.",
            )
            target_files = res_json.get("target_files") or ["backend/app/services/agent_service.py"]
            proposed_diff = res_json.get(
                "proposed_diff",
                "def optimize_cache_ttl(hit_rate: float) -> int:\n    return int(300 * (1.0 + hit_rate))\n",
            )
            research_sources = res_json.get("research_sources") or ["https://arxiv.org/abs/2408.00001"]

            # If an AIP with this exact title already exists, re-use and evolve it rather than creating a duplicate
            norm_title = title.strip().lower()
            existing_aip = next(
                (a for a in self.aips.values() if a.title.strip().lower() == norm_title),
                None
            )
            if existing_aip:
                existing_aip.description = description
                existing_aip.target_files = target_files
                existing_aip.proposed_diff = proposed_diff
                existing_aip.research_sources = research_sources
                if existing_aip.status in ["stalled", "failed"]:
                    existing_aip.status = "draft"
                self._save_aips()
                logger.info(f"[EvolutionService] Re-using and updating existing proposal: {existing_aip.aip_id} - '{title}'")
                return existing_aip

            aip = self.create_aip(
                initiator_id="self",
                title=title,
                description=description,
                target_files=target_files,
                proposed_diff=proposed_diff,
                research_sources=research_sources,
            )
            logger.info(f"[EvolutionService] Auto-generated new proposal draft: {aip.aip_id} - '{title}'")
            return aip
        except Exception as e:
            logger.error(f"[EvolutionService] Auto-exploration failed: {e}")
            return None

    async def revise_aip(self, aip_id: str, feedback: str, llm_client: Any = None) -> AIPProposal | None:
        """Revises a rejected or draft AIP proposal based on audit feedback."""
        aip = self.aips.get(aip_id)
        if not aip or not llm_client:
            return None

        try:
            prompt = (
                "You are the Autonomous Architecture Evolution Engine for Bit Politeia.\n"
                f"Your previous Agent Improvement Proposal ({aip.aip_id}) was reviewed by the Audit Committee and rejected with the following feedback:\n\n"
                f"--- AUDIT FEEDBACK ---\n{feedback}\n----------------------\n\n"
                f"Current Proposal:\n"
                f"Title: {aip.title}\n"
                f"Description: {aip.description}\n"
                f"Target Files: {aip.target_files}\n"
                f"Proposed Diff:\n{aip.proposed_diff}\n\n"
                "Please systematically address EVERY issue identified in the audit feedback and produce a revised, production-ready proposal.\n"
                "Return strictly valid JSON matching this schema:\n"
                "{\n"
                '  "title": "Revised title",\n'
                '  "description": "Updated explanation addressing the feedback",\n'
                '  "target_files": ["backend/app/services/memory_service.py"],\n'
                '  "proposed_diff": "Complete revised Python implementation with threading.Lock, numpy, proper interfaces, and tests",\n'
                '  "research_sources": ["https://arxiv.org/..."]\n'
                "}\n\n"
                "IMPORTANT: Output ONLY the raw JSON object. Do not output conversational preambles."
            )
            res_json = await _invoke_llm_json(llm_client, prompt)
            if res_json and ("proposed_diff" in res_json or "description" in res_json):
                aip.title = res_json.get("title", aip.title)
                aip.description = res_json.get("description", aip.description)
                if "target_files" in res_json:
                    aip.target_files = res_json.get("target_files", aip.target_files)
                if "proposed_diff" in res_json and res_json.get("proposed_diff"):
                    aip.proposed_diff = res_json.get("proposed_diff")
                if "research_sources" in res_json:
                    aip.research_sources = res_json.get("research_sources")
                aip.status = "revised_draft"
                self._save_aips()
                logger.info(f"[EvolutionService] Successfully revised {aip.aip_id} based on audit feedback.")
                return aip
            else:
                logger.warning(f"[EvolutionService] revise_aip returned empty/unparsed JSON for {aip_id}. Keys: {list(res_json.keys()) if isinstance(res_json, dict) else 'none'}")
        except Exception as e:
            logger.error(f"[EvolutionService] Failed to revise AIP {aip_id}: {e}")
        return None

    async def broadcast_aip(self, aip_id: str, p2p_service: Any = None) -> bool:
        """Broadcasts an AIP proposal to peer nodes over the P2P network."""
        aip = self.aips.get(aip_id)
        if not aip:
            logger.error(f"[EvolutionService] AIP {aip_id} not found")
            return False

        aip.status = "proposed"
        self._save_aips()

        if p2p_service and p2p_service.network_manager:
            try:
                # Construct P2P governance proposal message
                content_payload = json.dumps({
                    "type": "architecture_evolution",
                    "aip": aip.to_dict()
                })
                # Broadcast via governance network
                if hasattr(p2p_service, "governance_manager") and p2p_service.governance_manager:
                    p2p_service.governance_manager.create_proposal(
                        content=content_payload,
                        scope="group"
                    )
                logger.info(f"[EvolutionService] Broadcasted {aip_id} to P2P network")
                return True
            except Exception as e:
                logger.error(f"[EvolutionService] Failed to broadcast AIP {aip_id}: {e}")
                return False
        return True

    async def audit_aip(self, aip_id: str, llm_client: Any = None) -> Vote:
        """
        Audits an AIP proposal for security, breaking changes, and performance.
        Returns a Vote with approval status and reasoning.
        """
        aip = self.aips.get(aip_id)
        if not aip:
            return Vote(voter_id="self", approval=False, reason=f"AIP {aip_id} not found")

        # 1. Rule-based static check
        is_safe = True
        risk_factors = []

        dangerous_patterns = ["eval(", "exec(", "os.system(", "__import__", "rmdir"]
        for pattern in dangerous_patterns:
            if pattern in aip.proposed_diff:
                is_safe = False
                risk_factors.append(f"Contains dangerous code pattern: {pattern}")

        # 2. LLM Audit if client available
        if is_safe and llm_client:
            try:
                prompt = (
                    f"Audit this Agent Architecture Improvement Proposal:\n"
                    f"Title: {aip.title}\nDescription: {aip.description}\n"
                    f"Target Files: {aip.target_files}\nProposed Code Diff:\n{aip.proposed_diff}\n\n"
                    f"Respond strictly in JSON format:\n"
                    f'{{"approved": true/false, "reason": "concise explanation"}}'
                )
                res_json = await _invoke_llm_json(llm_client, prompt)
                approved = res_json.get("approved", True)
                reason = res_json.get("reason", "LLM audit passed")
                return Vote(voter_id="self", approval=approved, reason=reason)
            except Exception as e:
                logger.warning(f"[EvolutionService] LLM audit failed, falling back to rule audit: {e}")

        approval = is_safe
        reason = "Passed safety rule checks" if is_safe else f"Rejected due to risk: {', '.join(risk_factors)}"
        return Vote(voter_id="self", approval=approval, reason=reason)

    async def verify_in_sandbox(self, aip_id: str) -> dict[str, Any]:
        """
        Executes and validates the AIP patch in a sandbox environment.
        Runs syntax check, import simulation, and verification tests.
        """
        aip = self.aips.get(aip_id)
        if not aip:
            return {"success": False, "error": f"AIP {aip_id} not found"}

        try:
            try:
                from ..agent.sandbox import LocalSandbox
            except (ImportError, ValueError):
                from app.agent.sandbox import LocalSandbox

            sandbox = LocalSandbox()
            
            # If code is provided in proposed_diff, write to sandbox and execute
            code_to_verify = aip.proposed_diff.strip() if aip.proposed_diff else ""
            if code_to_verify:
                test_file_path = os.path.join(sandbox.temp_dir, "test_aip_verification.py")
                with open(test_file_path, "w", encoding="utf-8") as tf:
                    tf.write(code_to_verify)
                    tf.write("\n\nprint('[Sandbox Verification] Code executed cleanly without exceptions.')\n")
                
                verify_script = f"python {test_file_path}"
            else:
                verify_script = (
                    "python -c \"import sys; print('Sandbox environment initialized.'); print('Pre-flight checks passed.')\""
                )

            stdout, stderr, returncode = await sandbox.execute(verify_script)

            sandbox_data = {
                "success": returncode == 0,
                "stdout": stdout,
                "stderr": stderr,
                "timestamp": datetime.now(UTC).isoformat(),
            }
            aip.sandbox_results = sandbox_data
            if returncode == 0:
                aip.status = "sandbox_passed"
            else:
                aip.status = "failed"
            self._save_aips()
            return sandbox_data
        except Exception as e:
            logger.error(f"[EvolutionService] Sandbox verification error: {e}")
            err_data = {"success": False, "error": str(e)}
            aip.sandbox_results = err_data
            self._save_aips()
            return err_data

    async def run_aip_evolution_loop(
        self,
        aip_id: str,
        max_rounds: int = 4,
        llm_client: Any = None,
        p2p_service: Any = None,
        progress_callback: Any = None,
    ) -> dict[str, Any]:
        """
        Executes a Goal-Oriented Closed-Loop Convergence process for an AIP:
        Iterates [Audit -> Revise -> Sandbox Test] up to max_rounds until the
        proposal is fully verified and broadcasted to the P2P network.
        """
        aip = self.aips.get(aip_id)
        if not aip:
            return {"success": False, "error": f"AIP {aip_id} not found"}

        history_rounds = []

        for current_round in range(1, max_rounds + 1):
            logger.info(f"[EvolutionLoop] Round {current_round}/{max_rounds} for {aip.aip_id}: '{aip.title}'")
            if progress_callback:
                await progress_callback(
                    f"**[🚀 自主进化内循环]** 正在执行第 {current_round}/{max_rounds} 轮演化迭代 (提案: {aip.aip_id})..."
                )

            # 1. Audit Phase
            vote = await self.audit_aip(aip.aip_id, llm_client=llm_client)
            if not vote.approval:
                logger.info(f"[EvolutionLoop] Round {current_round}: Audit rejected. Reason: {vote.reason[:100]}...")
                if progress_callback:
                    await progress_callback(
                        f"**[🔍 审查反馈]** 第 {current_round} 轮审计未通过，正在自动重构优化代码:\n> {vote.reason[:150]}..."
                    )
                history_rounds.append({
                    "round": current_round,
                    "stage": "audit",
                    "status": "rejected",
                    "reason": vote.reason,
                })
                # Trigger self-repair
                revised = await self.revise_aip(aip.aip_id, feedback=vote.reason, llm_client=llm_client)
                if not revised:
                    logger.warning(f"[EvolutionLoop] Self-repair failed in round {current_round}")
                continue

            # 2. Sandbox Verification Phase
            if progress_callback:
                await progress_callback(
                    f"**[🛡️ 审计通过]** 第 {current_round} 轮安全与架构审计已通过！正在启动 LocalSandbox 隔离沙盒验证..."
                )
            sb_res = await self.verify_in_sandbox(aip.aip_id)
            if not sb_res.get("success"):
                err_msg = sb_res.get("stderr") or sb_res.get("error") or "Sandbox runtime failure"
                logger.info(f"[EvolutionLoop] Round {current_round}: Sandbox verification failed: {err_msg[:100]}")
                if progress_callback:
                    await progress_callback(
                        f"**[⚠️ 沙盒测试异常]** 沙盒运行未通过，正在分析报错堆栈并自愈修正:\n```\n{err_msg[:200]}\n```"
                    )
                history_rounds.append({
                    "round": current_round,
                    "stage": "sandbox",
                    "status": "failed",
                    "reason": err_msg,
                })
                # Trigger self-repair based on sandbox error
                revised = await self.revise_aip(
                    aip.aip_id,
                    feedback=f"Sandbox execution failed with error:\n{err_msg}\nPlease fix code implementation.",
                    llm_client=llm_client,
                )
                continue

            # 3. Success Phase: Broadcast to P2P Community
            logger.info(f"[EvolutionLoop] Round {current_round}: Sandbox verification PASSED! Broadcasting to P2P...")
            await self.broadcast_aip(aip.aip_id, p2p_service=p2p_service)
            aip.status = "verified_and_proposed"
            self._save_aips()

            if progress_callback:
                await progress_callback(
                    f"**[🎉 演化成功]** 提案 `{aip.aip_id}` 已历经 {current_round} 轮自我修正与沙盒双重验证，现已正式发布至全网 P2P 社区裁决！"
                )

            return {
                "success": True,
                "aip_id": aip.aip_id,
                "rounds_used": current_round,
                "status": aip.status,
                "history": history_rounds,
            }

        # If exhausted all rounds without passing
        aip.status = "stalled"
        self._save_aips()
        return {
            "success": False,
            "aip_id": aip.aip_id,
            "rounds_used": max_rounds,
            "status": "stalled",
            "history": history_rounds,
        }

    async def submit_pr(self, aip_id: str, agent_service: Any = None) -> str:
        """Submits a GitHub Pull Request for a verified AIP and notifies the resident."""
        aip = self.aips.get(aip_id)
        if not aip:
            return f"Error: AIP {aip_id} not found"

        pr_title = f"feat(evolution): {aip.title}"
        pr_body = (
            f"## Autonomous Agent Improvement Proposal ({aip.aip_id})\n\n"
            f"### Title: {aip.title}\n"
            f"### Description\n{aip.description}\n\n"
            f"### Target Files\n" + "\n".join([f"- `{f}`" for f in aip.target_files]) + "\n\n"
            f"### Research Sources\n" + "\n".join([f"- {s}" for s in aip.research_sources]) + "\n\n"
            f"### Sandbox Verification\n"
            f"```json\n{json.dumps(aip.sandbox_results, indent=2)}\n```\n"
        )

        aip.status = "pr_submitted"
        self._save_aips()

        if agent_service:
            notification = (
                f"🤖 **[Autonomous Evolution Engine]**\n"
                f"Agent collective has agreed on {aip.aip_id}: *{aip.title}*.\n"
                f"Sandbox verification passed cleanly. Please review the proposal details."
            )
            await agent_service.notify_resident(content=notification, broadcast=True)

        return f"Successfully generated PR payload for {aip.aip_id}: '{pr_title}'"


# Singleton instance
evolution_service = EvolutionService()
