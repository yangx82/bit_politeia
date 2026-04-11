---
name: research-claw
description: Autonomous academic research pipeline. Use when the user wants to conduct deep research on a topic, generate a full academic paper, or perform iterative simulations in a sandbox.
---

# ResearchClaw

Autonomous academic research powered by [AutoResearchClaw](https://github.com/aiming-lab/AutoResearchClaw).

## Capabilities
- **Autonomous Scoping**: Decomposes a research topic into structured questions.
- **Deep Literature Discovery**: Connects to OpenAlex, Semantic Scholar, and arXiv for real papers.
- **Experiment Design & Execution**: Generates and runs Python experiments in isolated Docker sandboxes.
- **Academic Writing**: Produces conference-ready LaTeX/PDF papers with verified references.
- **Human-in-the-Loop (HITL)**: Allows the agent to pause and ask for guidance.

## Usage Guide
This skill runs in the background. You must launch a research task, then check its status periodically.

### 1. Launch Research
Call `research-claw_start_research` with the research topic. This will return a `Task ID`.
Example: `research-claw_start_research(arguments="Research the impact of random matrix theory on neural network initialization")`

### 2. Check Status
Call `research-claw_check_status` with the Task ID to get the current stage (1-23) and progress updates.
Example: `research-claw_check_status(arguments="[TASK_ID]")`

### 3. Retrieve Results
Once the status is `COMPLETED`, call `research-claw_get_paper` to retrieve the final paper's content or file path.
Example: `research-claw_get_paper(arguments="[TASK_ID]")`
