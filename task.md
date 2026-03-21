# Bit Politeia - Group Rules & Governance

- [x] **P2P LAN Connectivity & Messaging Fix**
    - [x] Update `models.py` with `Node.endpoint`
    - [x] Update `schemas.py` with `P2PMessage`
    - [x] Add `POST /p2p/message` endpoint to backend API
    - [x] Implement `AgentService.receive_p2p_message`
    - [x] Update `P2PService.initialize` for dynamic URL
    - [x] Implement `NetworkManager.route_message` with HTTP transport
    - [x] Implement periodic topology sync in `AgentService`
    - [x] Verify message delivery between two independent nodes

- [x] **Contacts Page Implementation**
    - [x] **Backend**: Add `GET /api/v1/p2p/peers` endpoint (return group members)
    - [x] **Backend**: Add `POST /api/v1/p2p/send` endpoint (send message to peer)
    - [x] **Frontend**: Create `src/pages/Contacts.jsx`
    - [x] **Frontend**: Implement `ContactList` component
    - [x] **Frontend**: Add "Send Message" modal/dialog
    - [x] **Frontend**: Update `App.jsx` routing

- [x] **Archive Page Implementation**
    - [x] **Backend**: Add `GET /api/v1/archive/chain` endpoint
    - [x] **Frontend**: Create `src/pages/Archive.jsx`
    - [x] **Frontend**: Implement `BlockList` component
    - [x] **Frontend**: Implement `BlockDetail` modal
    - [x] **Frontend**: Update `App.jsx` routing

- [/] **Backend Agent Skills Support**
    - [x] **Design**: Create `SkillManager` to load skills from `backend/skills`
    - [x] **Tool**: Implement `files_ops` or similar if needed for skills to work (or rely on existing)
    - [x] **Tool**: Implement `use_skill` or expose specific scripts as tools
    - [x] **Migration**: Create `pdf-reader` skill in `backend/skills`
    - [x] **Dependency**: Install necessary libs (e.g. `pypdf`)
    - [x] **Integration**: Register new tools in `agent_service.py`
    - [x] **Refactor**: Implement Progressive Disclosure (Index + Dynamic Loading)
        - [x] Update `SkillManager` to separate Index from Instructions
        - [x] Create `read_skill_guide` tool
        - [x] Update `AgentService` to use Index prompt

- [x] **Debug: PDF Reader File Access**
    - [x] Investigate why agent claims "cannot access local file system" (Confirmed: Prompt Hallucination)
    - [x] Check if `read_pdf.py` execution environment has file access (Verified: Working)
    - [x] Verify `AgentSystemPrompt` doesn't contain restrictive instructions
    - [x] **Fix**: Update `AGENT_SYSTEM_PROMPT` to explicitly allow file access

- [x] **Feature: Message Bus & Channels (Nanobot-inspired)**
    - [x] Create `backend/app/bus/events.py` (Inbound/Outbound classes)
    - [x] Create `backend/app/bus/queue.py` (MessageBus Loop)
    - [x] Create `backend/app/channels/base.py` (BaseChannel Interface)
    - [x] Create `backend/app/channels/telegram.py` (Telegram Adapter)
    - [x] Integrate Bus into `AgentService`
    - [x] Register Channels in `main.py`
    - [x] Verify Telegram connection (Code Logic Verified)

- [x] **Feature: Feishu Channel Support**
    - [x] Create `backend/app/channels/feishu.py` (Lark Adapter)
    - [x] Update `backend/main.py` to register Feishu
    - [x] Create Configuration Guide (FEISHU_GUIDE.md -> docs/CHANNELS.md)
    - [x] Verify Feishu dependency (lark-oapi installed & verified)
    - [x] Update `backend/requirements.txt` with new dependencies
    
- [x] **Feature: Memory System Refactoring**
    - [x] Create `backend/app/services/memory_store.py` (Nanobot port)
    - [x] Refactor `ResidentMemory` to use `jsonl` files
    - [x] Implement `migrate_legacy_json` to `chat.jsonl`
    - [x] Update `AgentService` to integrate `MemoryStore`
    - [x] Verify memory persistence

- [x] **Core Agent Improvements**
    - [x] Implement ReAct Loop in `AgentService._think_and_act` (Fixes single-turn limitation)
    - [x] Verify multi-turn reasoning
    - [x] Enable Python Code Execution (Ported Nanobot `ExecTool`)

- [x] **Chat UI Improvements & History Search**
    - [x] Add `/api/v1/history/search` endpoint to backend
    - [x] Sync `Chat.jsx` improvements from `D:\git`
    - [x] Fix auto-scroll logic to allow manual scrolling
    - [x] Implement toggleable search filter bar in UI
    - [x] Pause polling when search filters are active
    - [x] Verify fix and search functionality

- [x] **Configurable Bootstrap Server Address**
    - [x] Update `ConfigRequest` schema in backend
    - [x] Add `set_server_url` to `BootstrapClient`
    - [x] Update `AgentService` to apply custom bootstrap URL
    - [x] Add "Bootstrap Server URL" field to Onboarding page
    - [x] Add "Bootstrap Server URL" field to Profile settings
    - [x] Verify connectivity from frontend to a custom-port bootstrap server

- [/] **Committing Changes & Governance PR**
    - [ ] Stage all modified governance and server files
    - [ ] Commit with Conventional Commits (feat/chore)
    - [ ] Create Pull Request #2: "Implement tiered group join and reputation-aware elections"

- [x] **Integrating Reputation into Election Candidates**
    - [x] Update `ReputationManager` to support collective group reputation queries
    - [x] Implement `get_top_candidates` logic in `BootstrapService`
    - [x] Allow "write-in" candidates in `GovernanceManager.receive_ballot`
    - [x] Update reputation thresholds in `community_rules.json` (optional)
    - [x] Verify with tests
- [x] **Revising Group Election & Split Rules**
    - [x] Update `GroupInfo` to support node rankings and proxy status
    - [x] Implement election trigger logic at 3, 11, and 19 members
    - [x] Implement "Proxy Core Node" logic for first 2 members
    - [x] Add API for core nodes to submit node rankings
    - [x] Update `_split_group` logic to use odd/even ranking distribution
    - [x] Update `community_rules.json` if necessary to match these numbers
    - [x] Verify revised logic with tests
- [x] **Implementing Group Join Rules**
    - [x] Research current membership and core node logic in `governance.py`
    - [x] Update `BootstrapService` to handle conditional registration
    - [x] Store "Pending Join Requests" in `BootstrapService`
    - [x] Implement Core Node approval API
    - [x] Update `community_rules.json` to reflect new thresholds
    - [x] Verify logic with automated tests
- [x] **Debugging & Synchronization**
    - [x] Fixed Balance 0.0 Issue (Node ID Identity Mismatch)
    - [x] Fixed Balance Discrepancy (1000 vs 1250) - Removed hardcoded UI values.
    - [x] Implemented Dynamic Profile Balance (Real-time API fetch)
    - [x] Silenced APScheduler Job Execution Logs
    - [x] Synchronized `D:\git` and `D:\BaiduSyncdisk` core files
    - [x] Added Scheduler robustness (misfire_grace_time=60)
- [x] **Code Submission & PR**
    - [x] Staged and committed changes with Conventional Commits
    - [x] Verified environmental tests (Fixed pytest-asyncio environment)
    - [x] Pushed branch `fix/balance-sync-and-logging` to remote
    - [x] Created Pull Request #1: "resolve Node ID mismatch and dynamic balance fetch"
    - [x] **Created Pull Request #2**: "feat(agent): enhance monitoring capabilities and memory persistence"
        - Covers Memory Fix, Message Bus, and Long Doc Skill.
        - Target: `feature/p2p-lan-connectivity`
- [x] **Project Infrastructure**
    - [x] Initialized GitHub Repo `yangx82/bit_politeia`
    - [x] Cleaned repository history (Purged sensitive/redundant files)
    - [x] Migrated 5 Agent Skills (git-commit, etc.)

- [x] **Porting Nanobot Tools**
    - [x] **FileSystem Tools**: Create `backend/app/agent/tools_fs.py` (Read, Write, List)
    - [x] **Web Tools**: Create `backend/app/agent/tools_web.py` (WebFetch with Readability)
    - [x] **Cron Tools**: Create `backend/app/agent/tools_cron.py` (Schedule tasks via APScheduler)
    - [x] **Integration**: Register new tools in `agent/tools.py`
    - [x] **Dependencies**: Install `readability-lxml`, `httpx`
    - [x] **Verification**: Create `verify_new_tools.py`
- [x] **Debugging PDF Capability**
    - [x] **Verify Permissions**: Check `tools_exec.py` for `pip` access.
    - [x] **Verify Skill**: Check `backend/skills/pdf-reader` content.
    - [x] **Diagnostic Script**: Create and run `debug_agent_pdf.py` (Confirmed Success).
    - [x] **Cleanup**: Remove temporary files.
    - [x] **Bug Fix**: truncated output in `read_pdf.py` to 50k chars to avoid LLM 400 error.
    - [x] **Feature**: Added page range support (`--start`, ` --end`) to `read_pdf.py`.
    
- [x] **Skill Creation: Long Document Analyzer**
    - [x] Create `backend/skills/long-doc-analyzer/SKILL.md`
    - [x] Implement `summarize_classic.py` (Map-Reduce with overlap)
    - [x] Support PDF and Text input
    - [x] Verify with a long document (Note: Requires valid API Key at runtime)

- [x] **Bug Fix: Agent Memory Persistence**
    - [x] Update `AgentService._think_and_act` to inject recent history.
    - [x] Verify agent recalls previous turn in same session.

- [x] **Enhancement: Verbose LLM Output**
    - [x] **Service Layer**: Add `verbose_llm` flag to `AgentService`.
    - [x] **API Layer**: Expose `verbose_llm` in `ConfigRequest`.
    - [x] **Frontend**: Add Toggle to `Onboarding.jsx` and `Profile.jsx`.
    - [x] **Service**: Update `store.js` to persist preference.
    - [x] **Verification**: Verified via `test_verbose_flag.py`.
    
- [x] **Bug Fix: Memory Persistence Duplicate Messages**
    - [x] **Diagnosis**: Agent was interpreting the most recent message too literally due to context duplication.
    - [x] **Fix**: Updated `AgentService._think_and_act` to recursively remove trailing duplicate messages from history slice.
    - [x] **Verification**: Confirmed with user that agent now correctly answers "What did I just ask?".

- [x] **Phase 2: Mesh Networking & NAT Traversal (BitTorrent-inspired)**
    - [x] **Dependency**: Add `upnpy` to `requirements.txt` and install.
    - [x] **Feature**: Implement `NATManager` in `backend/app/p2p_community/nat_traversal.py`.
    - [x] **Integration**: Update `NetworkManager` to use `NATManager` for auto-port mapping.
    - [x] **Verification**: Create and run `verify_upnp.py` to test router compatibility.

- [x] **Phase 3: Configuration Persistence**
    - [x] **Feature**: Update `AgentService.configure_agent` to write to `.env`.
    - [x] **Feature**: Update `AgentService.__init__` (or main) to auto-load config from `.env`.
    - [x] **Verification**: Verify backend restart functionality.

- [x] **Install Skill: planning-with-files**
    - [x] **Selection**: Selected Antigravity-optimized version from `.agent/skills/planning-with-files` (v2.15.0+).
    - [x] **Installation**: Installed to `backend/skills/planning-with-files`.
    - [x] **Verification**: Verified files exist and `SKILL.md` is correct size (~3.6KB).

- [x] **Cleanup: Remove root skills directory**
    - [x] **Verification**: Confirmed `peer-review` exists in `backend/skills`.
    - [x] **Action**: Deleted `d:\BaiduSyncdisk\SIAT\coding\bit_politeia\skills`.

- [x] **Organize: Move test scripts to `tests/`**
    - [x] **Action**: Move `test_*.py`, `verify_*.py`, `debug_*.py` to `tests/`.
    - [x] **Refactor**: Update `sys.path` and file paths in scripts to be location-independent.
    - [x] **Action**: Move `backend/test_*.py`, `backend/debug_*.py` to `tests/`.

- [x] **Security: Upgrade Bootstrap to HTTPS**
    - [x] **Tool**: Create `generate_cert.py` to generate self-signed SSL certificates.
    - [x] **Server**: Update `run_bootstrap.py` to use `uvicorn` SSL parameters.
    - [x] **Client**: Update `BootstrapClient` to support HTTPS and custom CA/verify selection.
    - [x] **Verify**: Create `tests/verify_https.py` to test secure connection.

- [x] **Phase 14: Debuging Status Indicator Regression**
    - [x] Trace agent message handling through `agent_service.process_bus_message`
    - [x] Uncover session ID pollution allowing internal summary thoughts into P2P histories with missing statuses
    - [x] Fix `agent_service.py` to restrict `[NO_RESPONSE_NEEDED]` to the `"resident"` session
    - [x] Assign correct `status="sent"` defaults for natively replied P2P bus message returns
    - [x] Re-tag historically erroneous `pending` instances in `chat.jsonl`

- [x] **Phase 15: Fix Task Monitor and Scheduler Registration**
    - [x] Update `check_tasks_monitor` to parse `pending` tasks and poke the agent immediately.
    - [x] Increase visibility by changing debug logging to `INFO` for idle task status updates.
    - [x] Resolve a race condition where `configure_agent` booting the scheduler preemptively caused `start_scheduler` to abandon adding background jobs.
