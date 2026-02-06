import os
import yaml
import logging
import subprocess
import json
from typing import List, Dict, Any, Optional
from langchain_core.tools import StructuredTool

logger = logging.getLogger(__name__)

class SkillManager:
    """
    Manages loading and execution of Agent Skills (Claude Code style).
    Skills are expected to be in a directory with a SKILL.md file and optional scripts/.
    """

    def __init__(self, skills_dir: str):
        self.skills_dir = skills_dir
        self.loaded_skills: Dict[str, Dict] = {}
        # Ensure skills directory exists
        if not os.path.exists(skills_dir):
            try:
                os.makedirs(skills_dir)
                logger.info(f"Created skills directory at {skills_dir}")
            except Exception as e:
                logger.error(f"Failed to create skills directory: {e}")

    def load_skills(self):
        """
        Scan skills directory and load valid skills.
        """
        self.loaded_skills = {}
        if not os.path.exists(self.skills_dir):
            return

        for item in os.listdir(self.skills_dir):
            skill_path = os.path.join(self.skills_dir, item)
            if os.path.isdir(skill_path):
                skill_md_path = os.path.join(skill_path, "SKILL.md")
                if os.path.exists(skill_md_path):
                    try:
                        skill_info = self._parse_skill_md(skill_md_path)
                        # Add path info
                        skill_info["path"] = skill_path
                        skill_info["scripts_path"] = os.path.join(skill_path, "scripts")
                        self.loaded_skills[skill_info["name"]] = skill_info
                        logger.info(f"Loaded skill: {skill_info['name']}")
                    except Exception as e:
                        logger.error(f"Failed to load skill at {skill_path}: {e}")

    def _parse_skill_md(self, file_path: str) -> Dict[str, Any]:
        """
        Parse SKILL.md frontmatter and content.
        """
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Simple frontmatter parsing (assuming standard format)
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
                        "instruction": body.strip()
                    }
            except Exception as e:
                logger.warning(f"Error parsing yaml frontmatter in {file_path}: {e}")
        
        # Fallback if no valid frontmatter
        return {
            "name": os.path.basename(os.path.dirname(file_path)),
            "description": "Custom skill",
            "instruction": content
        }

    def get_skill_prompts(self) -> str:
        """
        Combine all skill instructions into a system prompt addition.
        """
        prompts = []
        for name, info in self.loaded_skills.items():
            prompts.append(f"### Skill: {name}\n{info['description']}\n\nINSTRUCTIONS:\n{info['instruction']}")
        
        if not prompts:
            return ""
            
        return "\n\n## ENABLED AGENT SKILLS\nThe following external skills are available for use:\n\n" + "\n\n".join(prompts)

    def get_skill_tools(self) -> List[StructuredTool]:
        """
        Generate LangChain tools for each script in the loaded skills.
        Assumes scripts in scripts/ directory.
        """
        tools = []
        for name, info in self.loaded_skills.items():
            scripts_dir = info.get("scripts_path")
            if not scripts_dir or not os.path.exists(scripts_dir):
                continue
            
            for script in os.listdir(scripts_dir):
                if script.endswith(".py"):
                    tool_name = f"{name}_{script.replace('.py', '')}"
                    script_path = os.path.join(scripts_dir, script)
                    
                    # Create a tool for this script
                    # We wrap it in a closure to capture script_path
                    def create_tool_func(path_to_script):
                        def run_script(arguments: str = "") -> str:
                            """
                            Run the skill script.
                            Args:
                                arguments: JSON string or arguments to pass to the script via stdin or args.
                            """
                            try:
                                # Run python script
                                # We pass arguments as string argument to the script
                                # But standard Claude skills usually take input via stdin or simple args
                                # Let's try passing as first argument
                                cmd = ["python", path_to_script, arguments]
                                result = subprocess.run(
                                    cmd, 
                                    capture_output=True, 
                                    text=True, 
                                    timeout=60,
                                    encoding='utf-8',
                                    errors='replace' # Handle encoding issues gracefully
                                )
                                if result.returncode != 0:
                                    return f"Script failed (Exit {result.returncode}):\nSTDOUT: {result.stdout}\nSTDERR: {result.stderr}"
                                return result.stdout
                            except Exception as e:
                                return f"Error executing script: {str(e)}"
                        return run_script

                    tool = StructuredTool.from_function(
                        func=create_tool_func(script_path),
                        name=tool_name,
                        description=f"Execute {script} from {name} skill. Use this when the skill instructions mention running this script."
                    )
                    tools.append(tool)
        return tools

skill_manager = SkillManager(os.path.join(os.getcwd(), "backend", "skills"))
