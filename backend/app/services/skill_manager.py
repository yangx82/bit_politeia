import ast
import importlib
import importlib.util
import logging
import os
import subprocess
import sys
from typing import Any

from langchain_core.tools import Tool

logger = logging.getLogger(__name__)

CUSTOM_TOOLS_DIR = "backend/app/agent/custom_tools"


class SkillManager:
    """
    Manages the lifecycle of autonomous skills (custom tools).
    - Validates code for safety (basic AST check).
    - Persists code to disk.
    - Dynamically loads tools into the agent.
    """

    def __init__(self, tools_dir: str = CUSTOM_TOOLS_DIR):
        self.tools_dir = tools_dir
        if not os.path.exists(self.tools_dir):
            os.makedirs(self.tools_dir)

        # In-memory cache of loaded tools
        # Map: tool_name -> Tool object
        self.loaded_tools: dict[str, Tool] = {}

    def validate_code(self, code: str) -> bool:
        """
        Static analysis to reject obviously dangerous code.
        Returns True if safe (to the best of its knowledge), False otherwise.
        """
        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            logger.warning(f"Code syntax error: {e}")
            return False

        for node in ast.walk(tree):
            # 1. Ban imports of high-risk modules
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                # extract module names
                if isinstance(node, ast.Import):
                    names = [n.name for n in node.names]
                else:
                    names = [node.module] if node.module else []

                for name in names:
                    if not name:
                        continue
                    root_pkg = name.split(".")[0]
                    if root_pkg in ["os", "subprocess", "sys", "shutil", "builtins"]:
                        logger.warning(f"Rejected unsafe import: {name}")
                        return False

            # 2. Ban 'exec', 'eval', 'open' (maybe partial)
            # Actually 'open' might be needed for file ops, but let's be strict for now
            # unless we wrap it. For autonomous tool creation, we might want to restrict file I/O
            # to specific directories, but that requires runtime sandboxing.
            # For now, just ban exec/eval.
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    if node.func.id in ["exec", "eval", "globals", "locals"]:
                        logger.warning(f"Rejected unsafe function call: {node.func.id}")
                        return False

        return True

    def _install_dependencies(self, code: str):
        """
        Analyzes code for imports and installs missing packages via pip.
        """
        try:
            tree = ast.parse(code)
        except SyntaxError:
            return  # Should be caught by validate_code anyway, but safe to ignore here

        imports = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for n in node.names:
                    imports.add(n.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imports.add(node.module.split(".")[0])

        # Whitelist of standard libs to skip (incomplete but helpful)
        sys_modules = sys.builtin_module_names
        # We can also check if importlib can find it

        for pkg in imports:
            if pkg in sys_modules:
                continue

            # Check if installed
            if importlib.util.find_spec(pkg):
                continue

            # Attempt install
            logger.info(f"Auto-installing missing dependency: {pkg}")
            try:
                subprocess.check_call([sys.executable, "-m", "pip", "install", pkg])
                logger.info(f"Successfully installed {pkg}")
            except subprocess.CalledProcessError as e:
                logger.error(f"Failed to install {pkg}: {e}")
                # We continue, maybe it's not a package (e.g. local module)

    def create_skill(self, name: str, code: str) -> str:
        """
        Saves the python code to a file, installs dependencies, and tries to load it.
        Returns a success message or raises generic exception.
        """
        if not self.validate_code(code):
            raise ValueError("Code failed security validation (unsafe imports or functions).")

        # Attempt to install dependencies
        self._install_dependencies(code)

        # Sanitize filename
        safe_name = "".join([c for c in name if c.isalnum() or c == "_"])
        if not safe_name:
            raise ValueError("Invalid tool name.")

        file_path = os.path.join(self.tools_dir, f"{safe_name}.py")

        # Write to file
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(code)

        logger.info(f"Skill '{safe_name}' written to {file_path}")

        # Attempt to load immediately to verify syntax and structure
        try:
            self.load_single_tool(safe_name)
            return f"Tool '{safe_name}' created and loaded successfully."
        except Exception as e:
            # If load fails, delete the file to keep state clean?
            # Or keep it for debugging? Let's keep it but rename to .failed maybe?
            # For now just raise.
            logger.error(f"Failed to load new skill '{safe_name}': {e}")
            raise RuntimeError(f"Tool written but failed to load: {e}")

    def load_single_tool(self, module_name: str):
        """
        Dynamically imports a module and looks for a 'tool' object or a function decorated as tool.
        Expectation: The file must define a LangChain Tool object named `tool`
        OR a function that we can wrap.

        Convention: The file should export a variable named `tool` which is an instance of BaseTool/Tool,
        OR a function named `execute`.
        """
        file_path = os.path.join(self.tools_dir, f"{module_name}.py")
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Module {module_name} not found.")

        # Load module
        spec = importlib.util.spec_from_file_location(module_name, file_path)
        if spec is None or spec.loader is None:
            raise ImportError(f"Could not load spec for {module_name}")

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        # Look for 'tool' object
        if hasattr(module, "tool") and isinstance(module.tool, Tool):
            self.loaded_tools[module_name] = module.tool
            logger.info(f"Loaded tool '{module.tool.name}' from {module_name}.py")
            return

        # Look for 'execute' function and metadata
        if hasattr(module, "execute") and callable(module.execute):
            func_name = getattr(module, "name", module_name)
            desc = getattr(module, "description", "Custom tool")

            # Wrap as Tool
            from langchain_core.tools import Tool

            t = Tool(name=func_name, func=module.execute, description=desc)
            self.loaded_tools[module_name] = t
            logger.info(f"Loaded function-tool '{func_name}' from {module_name}.py")
            return

        raise ValueError(
            f"Module {module_name}.py must define 'tool' (LangChain Tool) or 'execute' function."
        )

    def load_skills(self):
        """Scans the directory and loads all valid tools."""
        if not os.path.exists(self.tools_dir):
            return

        for filename in os.listdir(self.tools_dir):
            if filename.endswith(".py") and not filename.startswith("__"):
                module_name = filename[:-3]
                try:
                    self.load_single_tool(module_name)
                except Exception as e:
                    logger.warning(f"Skipping skill {filename}: {e}")

    def get_active_tools(self) -> list[Tool]:
        return list(self.loaded_tools.values())

    # --- Claude Style Skills Support ---

    def _parse_skill_md(self, file_path: str) -> dict[str, Any]:
        """Parse SKILL.md frontmatter and content."""
        with open(file_path, encoding="utf-8") as f:
            content = f.read()

        import yaml

        if content.startswith("---"):
            try:
                parts = content.split("---", 2)
                if len(parts) >= 3:
                    frontmatter_raw = parts[1]
                    body = parts[2]
                    metadata = yaml.safe_load(frontmatter_raw)
                    return {
                        "name": metadata.get("name", "unknown"),
                        "description": metadata.get("description", ""),
                        "instruction": body.strip(),
                    }
            except Exception as e:
                logger.warning(f"Error parsing yaml frontmatter in {file_path}: {e}")

        return {
            "name": os.path.basename(os.path.dirname(file_path)),
            "description": "Custom skill",
            "instruction": content,
        }

    def load_claude_skills(self, skills_root_dir: str):
        """
        Scans a directory for Claude-style skills (folders with SKILL.md).
        """
        if not os.path.exists(skills_root_dir):
            return

        from langchain_core.tools import StructuredTool

        for item in os.listdir(skills_root_dir):
            skill_path = os.path.join(skills_root_dir, item)
            if os.path.isdir(skill_path):
                skill_md_path = os.path.join(skill_path, "SKILL.md")
                if os.path.exists(skill_md_path):
                    try:
                        skill_info = self._parse_skill_md(skill_md_path)
                        skill_name = skill_info["name"]

                        # Load scripts as tools
                        scripts_dir = os.path.join(skill_path, "scripts")
                        if os.path.exists(scripts_dir):
                            for script in os.listdir(scripts_dir):
                                if script.endswith(".py"):
                                    tool_name = f"{skill_name}_{script.replace('.py', '')}"
                                    script_full_path = os.path.join(scripts_dir, script)

                                    # Create Closure for Tool execution
                                    def make_run_func(s_path):
                                        def run_script(arguments: str = "") -> str:
                                            try:
                                                cmd = [sys.executable, s_path, arguments]
                                                result = subprocess.run(
                                                    cmd,
                                                    capture_output=True,
                                                    text=True,
                                                    timeout=60,
                                                    encoding="utf-8",
                                                    errors="replace",
                                                )
                                                if result.returncode != 0:
                                                    return f"Script failed (Exit {result.returncode}):\nSTDOUT: {result.stdout}\nSTDERR: {result.stderr}"
                                                return result.stdout
                                            except Exception as e:
                                                return f"Error executing script: {e!s}"

                                        return run_script

                                    # Create Tool
                                    t = StructuredTool.from_function(
                                        func=make_run_func(script_full_path),
                                        name=tool_name,
                                        description=f"Execute {script} from {skill_name}. {skill_info['description']}",
                                    )
                                    self.loaded_tools[tool_name] = t
                                    logger.info(f"Loaded Claude-style tool '{tool_name}'")

                        # Store Metadata if needed (e.g. for instructions)
                        # We might need a separate registry for instructions if we want to support read_skill_guide
                        if not hasattr(self, "skill_descriptions"):
                            self.skill_descriptions = {}
                        self.skill_descriptions[skill_name] = skill_info["instruction"]

                    except Exception as e:
                        logger.error(f"Failed to load Claude skill at {skill_path}: {e}")

    def get_skill_instruction(self, skill_name: str) -> str:
        if hasattr(self, "skill_descriptions"):
            return self.skill_descriptions.get(skill_name, "No instruction guide found.")
        return "No instruction guide found."

    def get_skill_index(self) -> str:
        """Returns a string description of available skills for the system prompt."""
        if not self.loaded_tools:
            return ""

        index = "\n\n## Custom Skills (Dynamically Loaded)\n"
        for name, tool in self.loaded_tools.items():
            index += f"- {name}: {tool.description}\n"
        return index
        return index


# Global instance
skill_manager = SkillManager()
