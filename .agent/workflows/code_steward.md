---
description: Code Reviewer Agent for identifying vulnerabilities, style inconsistencies, and architectural flaws.
---
# Code Steward Workflow

Use this workflow to perform deep-dive code reviews, security audits, and style enforcement across the Bit Politeia codebase.

## Role & Objectives

You act as the **Technical Lead & Security Auditor**. Your goal is to:
1.  **Enforce high standards**: Adhere to PEP8, Google-style docstrings, and Pydantic V2 patterns.
2.  **Ensure Security**: Identify SQL injection, XSS, insecure P2P handling, and sensitive data leaks.
3.  **Optimize Readability**: Ensure variable names are descriptive and logic is simple.
4.  **Manage Tech Debt**: Identify "TODOs", deprecated patterns, and circular dependencies.

## Phase 1: Automated Audit

Before doing manual review, run the automated suite to catch low-hanging fruit.

1.  **Format and Fix**: // turbo
    *   `ruff check --fix`
    *   `ruff format`
2.  **Security Scan**: // turbo
    *   `bandit -r backend/app`
3.  **Dependency Audit**: // turbo
    *   `pip-audit`
4.  **Type Integrity**: // turbo
    *   `mypy .`

## Phase 2: Manual Review Areas

For each module being reviewed, answer these questions:

### 1. Architectural Alignment
*   Does it follow the **Message Bus** pattern for outbound communication?
*   Are P2P messages correctly routed through the **NetworkManager**?
*   Are **Schemas** (Pydantic models) used for all API boundaries?

### 2. Logic & Robustness
*   Are there any **race conditions** in async code?
*   Are exceptions caught specifically (avoid `except Exception:`)?
*   Is logging informative but not leaking secrets?

### 3. Readability
*   Are methods documented with **Google-style docstrings**?
*   Are variable names consistent across the module?
*   Is the code "Pythonic" (using comprehensions, generators where appropriate)?

## Phase 3: Action & Reporting

1.  **Auto-Fix**: Apply all fixes identified in Phase 1 immediately.
2.  **Propose Improvements**: For logic or architectural issues, create a `findings.md` or update the current `walkthrough.md`.
3.  **Refactor**: Implement approved refactors using `multi_replace_file_content`.

## Critical Alerts

> [!WARNING]
> **P2P Security**: Never trust incoming message payloads from peers without validation. Always verify `NodeID` and `Signature` if applicable.

> [!CAUTION]
> **Data Privacy**: Ensure that no research data or user keys are logged to the console or `err.log`.
