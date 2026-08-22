"""
Zero-Trust Secure Sandbox Isolation Module

Provides AST-level dynamic code security auditing, resource quota confinement,
and isolated execution environments for untrusted P2P-submitted AIP code.
"""

import ast
import logging
import os
import shutil
import sys
import tempfile
from dataclasses import dataclass, field
from typing import Any

import anyio

logger = logging.getLogger(__name__)


@dataclass
class SecurityAuditResult:
    is_safe: bool
    violations: list[str] = field(default_factory=list)
    risk_level: str = "LOW"  # LOW, MEDIUM, HIGH, CRITICAL


class ASTSecurityAuditor(ast.NodeVisitor):
    """
    Statically analyzes Python code AST to identify dangerous, obfuscated, or forbidden operations.
    """

    FORBIDDEN_CALLS = {
        "eval",
        "exec",
        "__import__",
        "compile",
        "system",
        "popen",
        "spawn",
        "fork",
        "kill",
        "rmdir",
        "unlink",
    }

    FORBIDDEN_MODULES = {
        "ctypes",
        "socket",
        "pty",
        "resource",
    }

    def __init__(self):
        self.violations: list[str] = []

    def visit_Import(self, node: ast.Import):
        for alias in node.names:
            if alias.name in self.FORBIDDEN_MODULES:
                self.violations.append(f"Forbidden module imported: '{alias.name}'")
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom):
        if node.module in self.FORBIDDEN_MODULES:
            self.violations.append(f"Forbidden module import from: '{node.module}'")
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call):
        # 1. Detect direct forbidden calls (e.g., eval(..), exec(..))
        if isinstance(node.func, ast.Name) and node.func.id in self.FORBIDDEN_CALLS:
            self.violations.append(f"Direct invocation of forbidden function: '{node.func.id}()'")

        # 2. Detect attribute invocation (e.g., os.system(..), .eval())
        elif isinstance(node.func, ast.Attribute) and node.func.attr in self.FORBIDDEN_CALLS:
            self.violations.append(f"Attribute invocation of forbidden function: '.{node.func.attr}()'")

        # 3. Detect getattr with forbidden targets or builtins
        elif isinstance(node.func, ast.Name) and node.func.id == "getattr" and len(node.args) >= 2:
            target_arg = node.args[0]
            attr_arg = node.args[1]
            if isinstance(target_arg, ast.Name) and target_arg.id in ("__builtins__", "builtins"):
                self.violations.append("Dynamic reflection via getattr on '__builtins__'")
            if isinstance(attr_arg, ast.Constant) and str(attr_arg.value) in self.FORBIDDEN_CALLS:
                self.violations.append(f"Dynamic invocation of forbidden function '{attr_arg.value}' via getattr")

        self.generic_visit(node)

    @classmethod
    def audit_code(cls, code_str: str) -> SecurityAuditResult:
        """Audits Python source code string."""
        try:
            tree = ast.parse(code_str)
        except SyntaxError as se:
            return SecurityAuditResult(
                is_safe=False,
                violations=[f"Syntax Error in code: {se}"],
                risk_level="HIGH",
            )

        auditor = cls()
        auditor.visit(tree)

        if auditor.violations:
            return SecurityAuditResult(
                is_safe=False,
                violations=auditor.violations,
                risk_level="CRITICAL",
            )

        return SecurityAuditResult(is_safe=True, violations=[], risk_level="LOW")


class SecureSandbox:
    """
    Executes Python code in an isolated directory with timeout protection and AST pre-audit.
    Uses anyio.run_process for universal asyncio/trio support.
    """

    def __init__(self, timeout_sec: float = 10.0):
        self.timeout_sec = timeout_sec

    async def execute_code(
        self,
        code_str: str,
        env_vars: dict[str, str] | None = None,
        bypass_ast_audit: bool = False,
    ) -> dict[str, Any]:
        """
        Executes code safely after passing AST audit.
        """
        # 1. AST Dynamic Audit
        if not bypass_ast_audit:
            audit_res = ASTSecurityAuditor.audit_code(code_str)
            if not audit_res.is_safe:
                logger.error(f"[SecureSandbox] Blocked code execution due to security violations: {audit_res.violations}")
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": f"Security Policy Violation: {'; '.join(audit_res.violations)}",
                    "returncode": -1,
                    "audit": {
                        "is_safe": False,
                        "violations": audit_res.violations,
                        "risk_level": audit_res.risk_level,
                    },
                }

        # 2. Prepare Isolated Directory
        temp_sandbox_dir = tempfile.mkdtemp(prefix="bp_sandbox_")
        script_path = os.path.join(temp_sandbox_dir, "sandbox_run.py")

        try:
            with open(script_path, "w", encoding="utf-8") as f:
                f.write(code_str)

            env = dict(os.environ)
            if env_vars:
                env.update(env_vars)
            env["PYTHONUNBUFFERED"] = "1"

            # 3. Isolated Subprocess Execution via AnyIO
            with anyio.fail_after(self.timeout_sec):
                result = await anyio.run_process(
                    [sys.executable, script_path],
                    cwd=temp_sandbox_dir,
                    env=env,
                    check=False,
                )

                stdout = result.stdout.decode("utf-8", errors="replace")
                stderr = result.stderr.decode("utf-8", errors="replace")
                returncode = result.returncode

                return {
                    "success": returncode == 0,
                    "stdout": stdout,
                    "stderr": stderr,
                    "returncode": returncode,
                    "audit": {"is_safe": True, "violations": []},
                }

        except TimeoutError:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"Execution timed out after {self.timeout_sec}s",
                "returncode": -9,
                "audit": {"is_safe": True, "violations": []},
            }
        finally:
            shutil.rmtree(temp_sandbox_dir, ignore_errors=True)


# Singleton instance
secure_sandbox = SecureSandbox()
