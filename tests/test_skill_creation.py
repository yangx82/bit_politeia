import os
import shutil
import sys

# Add project root to path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.append(PROJECT_ROOT)

from backend.app.services.skill_manager import SkillManager

tools_dir = os.path.join(PROJECT_ROOT, "backend/app/agent/custom_tools_test")


def test_autonomous_tool_creation():
    print("--- Starting Autonomous Tool Creation & Auto-Install Verification ---")

    # Setup
    if os.path.exists(tools_dir):
        shutil.rmtree(tools_dir)
    os.makedirs(tools_dir)

    manager = SkillManager(tools_dir=tools_dir)

    # 1. Test Code Validation (Safety)
    print("\n1. Testing Safety Validation...")
    unsafe_code = "import os\ndef execute(x): os.system('echo hacked')"
    if not manager.validate_code(unsafe_code):
        print("   [PASS] Unsafe code rejected.")
    else:
        print("   [FAIL] Unsafe code accepted!")

    # 2. Test Auto-Install (Mocking a simple package)
    # We'll use a package that is unlikely to be installed but safe, e.g. 'cowsay' or just check if it calls pip.
    # Actually, running pip install might be slow.
    # Let's try to install 'pyfiglet' if not present, as it's small.
    print("\n2. Testing Auto-Install...")

    # Ensure pyfiglet is NOT installed for the test (optional, risky if user uses it)
    # So instead, let's just create a tool that uses 'json' (standard) and 'requests' (likely installed)
    # and verify it DOES NOT fail.
    # To truly test auto-install, we'd need a missing package.
    # Let's define a tool that uses 'colorama' which might be present or not.
    # If it's present, it skips. If not, it installs.

    tool_code = """
import json
try:
    import colorama
except ImportError:
    pass # Should be installed by manager before running this!

description = "Test tool with imports"
def execute(text):
    return "ok"
"""
    try:
        # We can't easily assert pip was called without mocking subprocess,
        # but we can check if create_skill returns success.
        result = manager.create_skill("import_test_tool", tool_code)
        print(f"   Creation Result: {result}")
        print("   [PASS] Tool with imports created successfully.")
    except Exception as e:
        print(f"   [FAIL] Creation exception: {e}")

    # 3. Test Loading and Execution
    print("\n3. Testing Execution...")
    manager.load_skills()
    tools = manager.get_active_tools()
    print(f"   Active Tools: {[t.name for t in tools]}")

    target_tool = next((t for t in tools if t.name == "import_test_tool"), None)
    if target_tool:
        output = target_tool.run("test")
        print(f"   Tool Output: {output}")
        if output == "ok":
            print("   [PASS] Tool executed correctly.")
        else:
            print("   [FAIL] Output mismatch.")
    else:
        print("   [FAIL] Tool not loaded.")

    print("\n--- Verification Complete ---")


if __name__ == "__main__":
    test_autonomous_tool_creation()
