from langchain_core.tools import tool
from ..services.skill_manager import SkillManager

# Global instance for simplicity, or inject via AgentService
skill_manager = SkillManager()

@tool
def create_tool(tool_name: str, description: str, python_code: str) -> str:
    """
    Creates a new tool for the agent to use.
    
    Args:
        tool_name: A unique identifier for the tool (e.g., 'count_vowels').
        description: A natural language description of what the tool does.
        python_code: The Python code implementing the tool. 
                     MUST define a function named 'execute' accepting a single argument.
                     MUST NOT use 'import os' or 'subprocess'.
    
    Example code:
    ```python
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

# Export for compatibility with AgentService
create_tool_tool = create_tool
