
from langchain_core.tools import Tool
from ..services.skill_manager import SkillManager

# Global instance for simplicity, or inject via AgentService
skill_manager = SkillManager()

def _create_tool_impl(tool_name: str, description: str, python_code: str) -> str:
    """
    Creates a new tool for the agent to use.
    
    Args:
        tool_name: A unique identifier for the tool (e.g., 'count_vowels').
        description: A natural language description of what the tool does.
        python_code: The Python code implementing the tool. 
                     MUST define a function named 'execute' accepting a single string argument.
                     MUST NOT use 'import os' or 'subprocess'.
    
    Example code:
    ```python
    description = "Counts vowels in a string"
    def execute(text):
        return str(sum(1 for c in text.lower() if c in 'aeiou'))
    ```
    """
    # Prepend description var if missing, to conform to SkillManager loading convention
    if "description =" not in python_code:
        python_code = f'description = "{description}"\n\n' + python_code
    
    try:
        return skill_manager.create_skill(tool_name, python_code)
    except Exception as e:
        return f"Failed to create tool: {str(e)}"

# Define the meta-tool
create_tool_tool = Tool(
    name="create_tool",
    func=_create_tool_impl,
    description=(
        "Use this tool to create NEW tools (Python scripts) for yourself. "
        "Input must include 'tool_name', 'description', and 'python_code'. "
        "The python code must define an 'execute(input_str)' function. "
        "Useful when you lack a specific capability (e.g., 'hash_text', 'parse_log')."
    )
)
