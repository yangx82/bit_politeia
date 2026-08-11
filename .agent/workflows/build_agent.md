---
description: Build Agent for CI/CD, code quality checks, and build verification for Bit Politeia.
---
# Build Agent

This workflow guides the agent to ensure code quality and build stability before commits, focusing on the Python backend and React frontend.

## Step 1: Code Quality Checks (Backend)

Run these checks from the project root.

1.  **Lint & Format**: Use Ruff for lightning-fast linting and formatting.
    *   Command: `ruff check --fix`
    *   Command: `ruff format`
2.  **Type Check**: Verify Python types with MyPy.
    *   Command: `mypy .`
3.  **Security Scan**: Check for common security issues.
    *   Command: `bandit -r backend/app`

## Step 2: Code Quality Checks (Frontend)

Run these checks within the `frontend_web/` directory.

1.  **Format**: `npm run format`
2.  **Lint**: `npm run lint`

## Step 3: Testing

Validate logic and functionality.

1.  **Python Tests**: Run pytest with coverage.
    *   Command: `pytest`
2.  **Frontend Tests**: (If available)
    *   Command: `npm test`

## Step 4: Security Audit

Audit dependencies for known vulnerabilities.

1.  **Python Audit**: `pip-audit`

## Step 5: Error Handling

If any check fails:

1.  **Analyze**: Read the error output carefully. Use `Select-String` if needed to find specific failures in large logs.
2.  **Fix**: Correct the code causing the error.
3.  **Retry**: Re-run the failing check until it passes.
4.  **Block**: DO NOT proceed to commit if checks are failing.
