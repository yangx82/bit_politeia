import os
import sys
import pytest

project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
backend_path = os.path.join(project_root, "backend")
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)

from app.agent.tools import check_python_syntax, verify_file_exists

@pytest.mark.anyio
async def test_check_python_syntax_valid(tmp_path):
    test_file = tmp_path / "valid_script.py"
    test_file.write_text("def hello():\n    print('Hello World')\n\nif __name__ == '__main__':\n    hello()\n")

    result = await check_python_syntax.coroutine(file_path=str(test_file))
    assert "PASSED" in result
    assert "checks cleanly" in result

@pytest.mark.anyio
async def test_check_python_syntax_invalid(tmp_path):
    test_file = tmp_path / "invalid_script.py"
    test_file.write_text("def broken_func(\n    print('Missing closing parenthesis')\n")

    result = await check_python_syntax.coroutine(file_path=str(test_file))
    assert "SYNTAX_ERROR" in result or "COMPILE_ERROR" in result

@pytest.mark.anyio
async def test_verify_file_exists(tmp_path):
    # Non-existent file
    res1 = await verify_file_exists.coroutine(file_path=str(tmp_path / "missing.py"))
    assert "VERIFICATION_FAILED" in res1
    assert "does not exist" in res1

    # Empty file
    empty_file = tmp_path / "empty.py"
    empty_file.write_text("")
    res2 = await verify_file_exists.coroutine(file_path=str(empty_file))
    assert "VERIFICATION_FAILED" in res2
    assert "0 bytes" in res2

    # Non-empty valid file
    valid_file = tmp_path / "valid.py"
    valid_file.write_text("print(1)")
    res3 = await verify_file_exists.coroutine(file_path=str(valid_file))
    assert "VERIFICATION_PASSED" in res3
