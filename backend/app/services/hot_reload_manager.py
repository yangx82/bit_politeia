"""
Dynamic Hot-Reload & Canary Evolution Module

Enables zero-downtime hot-reloading of agent plugins and AIP patches with
atomic backups, canary shadow validation, and automatic rollback on failure.
"""

import importlib
import inspect
import logging
import sys
from collections.abc import Callable
from datetime import datetime, timezone
UTC = timezone.utc
from typing import Any

logger = logging.getLogger(__name__)


class HotReloadManager:
    """
    Manages dynamic module reload, canary validation, and atomic rollbacks.
    """

    def __init__(self):
        self._module_backups: dict[str, Any] = {}
        self._reload_history: list[dict[str, Any]] = []

    def backup_module_state(self, module_name: str) -> bool:
        """Saves current module state before applying updates."""
        if module_name in sys.modules:
            self._module_backups[module_name] = sys.modules[module_name]
            logger.info(f"[HotReload] Backed up module state: '{module_name}'")
            return True
        return False

    def reload_module(self, module_name: str) -> tuple[bool, str]:
        """
        Dynamically reloads a Python module from disk.
        Returns (success, message).
        """
        if module_name not in sys.modules:
            try:
                mod = importlib.import_module(module_name)
                sys.modules[module_name] = mod
                logger.info(f"[HotReload] Freshly imported module: '{module_name}'")
                return True, f"Imported {module_name}"
            except Exception as e:
                return False, f"Failed to import {module_name}: {e}"

        self.backup_module_state(module_name)

        try:
            old_mod = sys.modules[module_name]
            reloaded_mod = importlib.reload(old_mod)
            sys.modules[module_name] = reloaded_mod
            logger.info(f"[HotReload] Successfully reloaded module: '{module_name}'")
            return True, f"Reloaded {module_name}"
        except Exception as e:
            logger.error(f"[HotReload] Error reloading module '{module_name}': {e}")
            self.rollback_module(module_name)
            return False, str(e)

    def rollback_module(self, module_name: str) -> bool:
        """Restores module from prior backup snapshot."""
        if module_name in self._module_backups:
            sys.modules[module_name] = self._module_backups[module_name]
            logger.warning(f"[HotReload] Rolled back module '{module_name}' to previous snapshot.")
            return True
        return False

    async def apply_canary_patch(
        self,
        module_name: str,
        verification_fn: Callable[[], Any] | None = None,
        canary_timeout_sec: float = 5.0,
    ) -> dict[str, Any]:
        """
        Applies a hot reload under canary observation:
        1. Backs up current module state.
        2. Reloads module.
        3. Executes verification check.
        4. If verification passes, promotes patch; if fails, triggers instant rollback.
        """
        timestamp = datetime.now(UTC).isoformat()
        self.backup_module_state(module_name)

        success, msg = self.reload_module(module_name)
        if not success:
            record = {
                "module": module_name,
                "status": "failed_reload",
                "message": msg,
                "timestamp": timestamp,
            }
            self._reload_history.append(record)
            return record

        # Canary verification
        if verification_fn:
            try:
                import asyncio
                res = verification_fn()
                if inspect.isawaitable(res):
                    res = await asyncio.wait_for(res, timeout=canary_timeout_sec)

                if res is False or (isinstance(res, dict) and not res.get("passed", True)):
                    raise RuntimeError(f"Canary verification failed: {res}")

                logger.info(f"[HotReload] Canary verification passed for '{module_name}'")
            except Exception as e:
                logger.error(f"[HotReload] Canary check failed for '{module_name}': {e}. Initiating auto-rollback...")
                self.rollback_module(module_name)
                record = {
                    "module": module_name,
                    "status": "rolled_back",
                    "reason": str(e),
                    "timestamp": timestamp,
                }
                self._reload_history.append(record)
                return record

        record = {
            "module": module_name,
            "status": "promoted",
            "message": "Canary verification successful. Module promoted.",
            "timestamp": timestamp,
        }
        self._reload_history.append(record)
        return record

    def get_history(self) -> list[dict[str, Any]]:
        return self._reload_history


# Singleton instance
hot_reload_manager = HotReloadManager()
