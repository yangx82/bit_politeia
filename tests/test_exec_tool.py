
import asyncio
import sys
import os

# Add backend to path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.join(project_root, 'backend'))

from app.agent.tools_exec import execute_shell_command

async def test():
    print("Testing execute_shell_command...")
    
    # 1. Simple Echo
    result = await execute_shell_command.ainvoke("echo Hello World")
    print(f"Echo Result: {result.strip()}")
    assert "Hello World" in result
    
    # 2. Python Execution
    result = await execute_shell_command.ainvoke("python -c \"print('Python Execution Works')\"")
    print(f"Python Result: {result.strip()}")
    assert "Python Execution Works" in result
    
    print(">>> Execution Tool Verification PASSED")

if __name__ == "__main__":
    asyncio.run(test())
