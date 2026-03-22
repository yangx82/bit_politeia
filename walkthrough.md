# Walkthrough - New Features & Fixes

## 1. Message Bus & Multi-Channel Support (Telegram)
We have implemented a Nanobot-inspired Message Bus to allow the Agent to communicate via external platforms.

### Architecture
- **Message Bus (`backend/app/bus/`)**: Decouples the Agent from specific communication channels.
- **Telegram Channel (`backend/app/channels/telegram.py`)**: A new adapter that connects the Agent to a Telegram Bot.
- **Frontend Sync**: Remote messages from Telegram are synchronized to the web UI history.

### Setup Guide
To enable Telegram integration:
1.  **Get a Bot Token**: Create a new bot via [@BotFather](https://t.me/BotFather) on Telegram.
2.  **Configure Environment**: Add the token to your `.env` file or environment variables:
    ```bash
    TELEGRAM_TOKEN=123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11
    ```
3.  **Restart Backend**: The channel starts automatically if the token is present.

### Verification
Run the verification script:
```powershell
python verify_bus.py
```

## 2. Feishu (Lark) Integration
Implemented WebSocket-based channel for Feishu.

### Setup Guide
1.  **Dependencies**: `pip install lark-oapi` (Installed).
2.  **Configuration**: Set `FEISHU_APP_ID` and `FEISHU_APP_SECRET`.
3.  **Verification**: Validated channel initialization via `verify_bus.py`.

## 3. PDF Reader Access Fix
Fixed an issue where the Agent refused to read local files.
Fixed an issue where the Agent refused to read local files due to a system prompt hallucination.

### Solution
- Updated `AGENT_SYSTEM_PROMPT` to explicitly authorize local file access.
- Restored `pdf-reader` skill files.

### Verification
- Ask the agent: *"Read file D:\path\to\file.pdf"*
- It should now process the file without complaint.

## 4. Memory System Refactoring
Adopted Nanobot's memory architecture for better context management.

### Key Changes
- **Long-term Memory**: `backend/memory/MEMORY.md` stores synthesized facts.
- **Topic-based Logs**: `backend/memory/chat.jsonl` stores all conversation history (Telegram, Feishu, Web) in a unified, topic-based format.
- **Migration**: Existing `resident_memory.json` is automatically migrated to `chat.jsonl`.

### Verification
- Run `verify_memory.py` to confirm creation of memory files.

### 4.1 Fix: Duplicate Message Handling
- Addressed an issue where the agent would parrot the last user message ("What did I just ask?").
- **Solution**: Implemented recursive removal of trailing duplicate messages in `AgentService._think_and_act` history slice.
- **Result**: Agent now correctly looks past repeated meta-questions to find the actual conversational context.
- Modify `ResidentMemory.log_interaction` to handle explicit timestamps.
- Update `process_network_inbox` backwards-compatibility loops to avoid dropping real timestamps during queue un-marshaling.

### Resolution of Perpetual "Pending" UI Status
- **Root Cause**: An earlier architectural change mistakenly routed the Agent's internal "thought" summaries (such as confirming `[NO_RESPONSE_NEEDED]`) to the P2P connection `session_id`, meaning these logs correctly showed up in the frontend's P2P conversation views. However, because they are internal agent thoughts, they lacked a network `status` (such as `sent` or `failed`), appearing as `null` in the payload. The `Chat.jsx` frontend falls back to displaying a spinning pending loader for any `activeSessionId !== 'resident'` message that lacks a `status`.
- **Fix Applied**: 
### Resolution of Stalled Task Monitor
- **Root Cause**: The background task monitor (`check_tasks_monitor`) only parsed tasks with an explicit `active` status. Newly created tasks with a `pending` status were ignored. Additionally, the 30-minute idle threshold meant that even active tasks appeared "stalled" to users who expected immediate action after a reboot. Finally, a race condition occurred during startup where `configure_agent` (called synchronously from `.env`) would start the APScheduler *before* `start_scheduler` could add the background jobs, causing all background tracking loops to be silently discarded. Further debugging revealed a silent `TaskStatus` import error crashing the proxy subroutine, APScheduler's `SQLAlchemyJobStore` incorrectly suppressing fresh boot triggers due to locally-cached SQLite misfire grace time violations, an extreme initialization race condition where the rapid memory job execution aborted silently because `agent.llm` wasn't fully connected yet by the async backend boot sequence, and finally, a conversational loophole where the LLM would acknowledge the internal monitor "system" poke with a text response rather than executing a strict action/tool, causing the pipeline to silently terminate the reasoning branch after outputting a "thought".
- **Fix Applied**: 
  - Updated `check_tasks_monitor` to automatically detect and activate `pending` tasks, triggering an immediate "self-poke" to the agent.
  - Improved logging levels from `DEBUG` to `INFO` for better visibility in the backend console during task monitoring.
  - Fixed a missing python import for `TaskStatus` successfully resolving the sub-process silent crashes.
  - Replaced the persistent `SQLAlchemyJobStore` implementation with the default non-persistent `MemoryJobStore` for APScheduler, ensuring cached schedules are completely purged each reboot to force strict static interval execution bounds.
  - Decoupled `add_job` background task registration from the scheduler's running state in `start_scheduler` to ensure monitor loops are fundamentally registered regardless of which component boot-straps the APScheduler first.
  - Added an LLM initialization guard into `check_tasks_monitor`. If the LLM isn't hooked up yet during the swift boot schedule, it logs the delay and correctly spawns a precise 5-second delayed `date` job to try again.
  - Injected an un-ignorable `[CRITICAL INSTRUCTION]` directly into the monitor's trigger message bounding the LLM to explicitly execute an action framework tool proactively, explicitly forbidding the passive fallback of calling `ask_resident` for permission or instructions unless critically blocked.
  - Rectified a >30-minute idle threshold sub-second race condition by decoupling the APScheduler polling frequency (now 5 minutes) from the evaluation threshold (>1800s), combined with an explicitly injected timestamp bump during dispatch to thwart rapid-fire agent spam.
  - Fortified `update_task_status` tool definitions and global system prompts with strict technical constraints, defining absolute 100% success for `completed` usage to categorically eliminate the LLM 'tried and gave up -> completed' semantic semantic hallucination, rigidly enforcing the adoption of `failed` or `blocked` instead.
  - Fixed a P2P message status persistence mismatch where status updates were being sent to the `agent` topic (mapping to `agent.jsonl`) while original messages were logged to `chat` topic (mapping to `chat.jsonl`). Refactored `ResidentMemory.update_message_status` to be topic-agnostic, ensuring 'sent' status correctly overwrites 'pending' across all JSONL logs.

## 5. Agent Self-Awareness & Maintenance
- **Architecture Mapping**: Created `backend/CODEBASE_MAP.md` as a persistent "Internal Anatomy" reference for the agent.
- **Constitutional Update**: Added `LAYER 4: SELF-AWARENESS` to `AGENT_SYSTEM_PROMPT`, formally authorizing the agent to inspect its own source code.
- **Autonomous Maintenance**: Instructed the agent to use its file tools to diagnose internal logic flaws and propose technical fixes rather than generic apologies.

## 6. Agent ReAct Loop & ContextBuilder
- **ContextBuilder**: Implemented `backend/app/agent/context.py` to centrally manage system prompts, memory injection, and skill definitions, adopting the Nanobot architecture.
- **ReAct Loop**: Refactored `AgentService._think_and_act` to use a `while` loop (max 5 iterations). This allows the agent to:
    - Execute a tool.
    - Observe the output.
    - Decide on the next action (or finish) based on that output.
- **Verification**: Created and ran `verify_react.py`, confirming multi-turn reasoning capabilities.

## 6. Python Code Execution Capability
- **Tool**: Implemented `execute_shell_command` (ported from Nanobot's `ExecTool`).
- **Capability**: Agent can now run shell commands, including `python script.py` or `python -c "..."`.
- **Safety**: Includes basic guardrails against destructive commands (`rm -rf`, `format`, etc.).
- **Verification**: Verified via `test_exec_tool.py`.

### Troubleshooting PDF Capability
If the agent fails to read a PDF, use the diagnostic script:
```powershell
python debug_agent_pdf.py
```
This confirms that:
1. `pypdf` is installed.
2. The `pdf-reader` skill is loaded.
3. The PDF file is accessible.

## 7. Nanobot Tools Ported
We have ported key tools from Nanobot to enhance the agent's autonomy:
- **FileSystem Tools** (`tools_fs.py`):
    - `read_file`, `write_file`, `edit_file`, `list_dir`.
    - Allows the agent to explore and modify the codebase directly.
- **Web Tools** (`tools_web.py`):
    - `fetch_web_page`: Fetches URL content and converts it to Markdown using `readability` for easy consumption by the LLM.
- **Cron Tools** (`tools_cron.py`):
    - `schedule_reminder`, `list_reminders`, `cancel_reminder`.
    - `start_scheduler`, `get_scheduler_status`.
    - Enables the agent to schedule future tasks and reminders.
- **Verification**: Comprehensive verification script `verify_new_tools.py` confirms all new tools are functional.

## 8. P2P NAT Traversal (Phase 2)
Implemented BitTorrent-inspired NAT traversal using UPnP.

### Changes
1.  **Dependency**: Added `upnpy` for pure Python UPnP IGD interaction.
2.  **Module**: Created `backend/app/p2p_community/nat_traversal.py` with `NATManager`.
3.  **Integration**: `NetworkManager` now attempts to map public port 8000 on startup.

### Verification
- **Script**: `verify_upnp.py`
- **Result**: `Failed: No UPnP Gateway found`.
- **Diagnosis**: The current network environment (likely corporate NAT or mobile hotspot) does not broadcast UPnP. The code gracefully handles this by logging a warning and continuing in client-only mode.
- **Action**: No code fix needed. To enable external access, ensure the router has UPnP enabled or manually forward port 8000.

## 9. Configuration Persistence (Phase 3)
Implemented auto-save and auto-load for Agent configuration parameters using `.env` file.

### Changes
1.  **Dependency**: Added `python-dotenv`.
2.  **Auto-Save**: `AgentService.configure_agent` now writes `AGENT_BASE_URL`, `API_KEY` etc. to `.env`.
3.  **Auto-Load**: `main.py` checks `.env` on startup and automatically initializes the Agent if config is found.

### Verification
- **Script**: `verify_config_persistence.py`
- **Result**: `SUCCESS: Configuration persisted and loaded correctly.`
- **Benefit**: You no longer need to re-configure the Agent after every restart.

## 10. New Skill: planning-with-files
Installed the Antigravity-optimized version of the Manus-inspired planning skill.

### Version Details
- **Source**: `D:\git\planning-with-files\.agent\skills\planning-with-files`
- **Optimization**: Specifically tuned for Antigravity IDE (uses `references.md` plural, lighter `SKILL.md`).
- **Location**: Installed at `backend/skills/planning-with-files`.

### Capabilities
- **Strategy**: Uses `task_plan.md`, `findings.md`, and `progress.md` for complex task management.
- **Persistence**: Maintains context across long sessions by writing to disk.
- **Reference**: See `backend/skills/planning-with-files/SKILL.md` for the full guide.

## 11. Maintenance: Script Organization
- **Action**: All test and verification scripts (`test_*.py`, `verify_*.py`, `debug_*.py`) have been moved to `tests/`.
- **Backend Cleanup**: Moved `backend/test_*.py` and `backend/debug_*.py` to `tests/`.
- **Refactoring**: Scripts now use robust relative paths and can be run from the project root or the `tests/` directory.

### Usage
Ask the Agent: *"Start a complex task using planning-with-files"* or simply *"Plan out this big project"*.
