"""
Waterfall Pipeline & Middleware Hook Module (DeepSeek Harness core/agent-loop Pattern)

Implements an onion-style interceptor pipeline for the Agent loop:
- pre_step: Context normalization, steering injection, token budget gating.
- pre_execute: Security policies, dangerous command interception (e.g. rm -rf, eval).
- post_execute: Output spill detection, sensitive data masking, trimming.
- turn_stopping: Dynamic convergence validation, auto-heal trigger.
"""

import inspect
import logging
from collections.abc import Callable
from typing import Any

try:
    from app.services.spill_store import spill_store
except (ImportError, ModuleNotFoundError):
    from backend.app.services.spill_store import spill_store

logger = logging.getLogger(__name__)


class WaterfallPipeline:
    """
    Manages and executes middleware hooks across agent step and tool execution lifecycles.
    """

    def __init__(self):
        self._pre_step_hooks: list[Callable] = []
        self._pre_execute_hooks: list[Callable] = []
        self._post_execute_hooks: list[Callable] = []
        self._turn_stopping_hooks: list[Callable] = []

        # Register default built-in middleware
        self._register_default_hooks()

    def _register_default_hooks(self):
        """Registers essential security and spill middleware."""
        self.add_pre_execute_hook(self._default_security_guard)
        self.add_post_execute_hook(self._default_spill_middleware)

    def add_pre_step_hook(self, hook: Callable):
        self._pre_step_hooks.append(hook)

    def add_pre_execute_hook(self, hook: Callable):
        self._pre_execute_hooks.append(hook)

    def add_post_execute_hook(self, hook: Callable):
        self._post_execute_hooks.append(hook)

    def add_turn_stopping_hook(self, hook: Callable):
        self._turn_stopping_hooks.append(hook)

    # --- Built-in Middleware ---

    async def _default_security_guard(self, tool_name: str, tool_args: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        """
        Blocks potentially destructive or dangerous execution patterns.
        """
        dangerous_shell_patterns = [
            "rm -rf /",
            "rm -rf ~",
            ":(){ :|:& };:",
            "mkfs.",
            "dd if=/dev/zero",
            "> /dev/sda",
        ]
        
        args_str = str(tool_args).lower()
        for pattern in dangerous_shell_patterns:
            if pattern in args_str:
                logger.error(f"[SecurityGuard] Intercepted dangerous command pattern '{pattern}' in tool '{tool_name}'")
                return {
                    "allow": False,
                    "reason": f"Execution blocked by SecurityGuard: contains forbidden pattern '{pattern}'",
                }

        return {"allow": True}

    async def _default_spill_middleware(
        self, tool_name: str, tool_args: dict[str, Any], tool_result: Any, context: dict[str, Any]
    ) -> Any:
        """
        Automatically offloads oversized tool outputs to SpillStore.
        """
        session_id = context.get("session_id", "default_session")
        call_id = context.get("call_id", f"{tool_name}_call")
        return spill_store.process_tool_output(
            session_id=session_id,
            tool_name=tool_name,
            call_id=call_id,
            output=tool_result,
        )

    # --- Pipeline Execution ---

    async def run_pre_step(self, messages: list[Any], context: dict[str, Any]) -> list[Any]:
        """Executes all pre_step hooks in sequence."""
        current_messages = messages
        for hook in self._pre_step_hooks:
            try:
                res = hook(current_messages, context)
                if inspect.isawaitable(res):
                    res = await res
                if res is not None:
                    current_messages = res
            except Exception as e:
                logger.error(f"[Waterfall] Error in pre_step hook {hook.__name__}: {e}")
        return current_messages

    async def run_pre_execute(self, tool_name: str, tool_args: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        """
        Executes pre_execute hooks. If any hook returns allow=False, execution is rejected.
        """
        for hook in self._pre_execute_hooks:
            try:
                res = hook(tool_name, tool_args, context)
                if inspect.isawaitable(res):
                    res = await res
                if isinstance(res, dict) and not res.get("allow", True):
                    return res
            except Exception as e:
                logger.error(f"[Waterfall] Error in pre_execute hook {hook.__name__}: {e}")
        return {"allow": True}

    async def run_post_execute(
        self, tool_name: str, tool_args: dict[str, Any], tool_result: Any, context: dict[str, Any]
    ) -> Any:
        """Executes all post_execute hooks to transform or log tool results."""
        current_result = tool_result
        for hook in self._post_execute_hooks:
            try:
                res = hook(tool_name, tool_args, current_result, context)
                if inspect.isawaitable(res):
                    res = await res
                if res is not None:
                    current_result = res
            except Exception as e:
                logger.error(f"[Waterfall] Error in post_execute hook {hook.__name__}: {e}")
        return current_result

    async def run_turn_stopping(self, turn_info: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        """Evaluates whether turn should stop or continue/auto-heal."""
        decision = {"stop": True, "reason": "normal_completion"}
        for hook in self._turn_stopping_hooks:
            try:
                res = hook(turn_info, context)
                if inspect.isawaitable(res):
                    res = await res
                if isinstance(res, dict):
                    decision = res
            except Exception as e:
                logger.error(f"[Waterfall] Error in turn_stopping hook {hook.__name__}: {e}")
        return decision


# Singleton instance
waterfall_pipeline = WaterfallPipeline()
