# 2. Application Architecture Strategy (Split)

Date: 2026-01-11

## Status

Proposed

## Context

The application logic is moved to a Python Backend. The Android App becomes a "Remote Control" and "Viewer".

## Decision

We will adopt a **Clean Architecture** on both sides, connected by an API Layer.

### Backend (Python Node)
- **Controller Layer**: FastAPI Routes.
- **Service Layer**:
    - `AgentService`: Orchestrates the AI loop (Perceive -> Think -> Act).
    - `P2PService`: Manages Libp2p Host, GossipSub.
    - `ConsensusService`: Manages Blockchain state and verification.
- **Repository Layer**: SQLite (SQLAlchemy) for persistence.

### Frontend (Android App)
- **UI Layer**: Composable Screens (4 Tabs).
- **ViewModel Layer**: Maps API DTOs to UI State.
- **Repository Layer**: `AgentRepository` (Retrofit calls).
- **Data Source**: Remote API + Local Cache (Room, optional for offline viewing).

### Data Flow (Example: User instructs Agent)
1.  **User**: Enters "Check proposal #10" in Android UI.
2.  **App**: POST `/api/v1/chat/instruction` -> Python Backend.
3.  **Backend (FastAPI)**: Enqueues instruction to `AgentService`.
4.  **Backend (Agent)**: Wakes up, uses LLM to interpret instruction.
5.  **Backend (P2P)**: Broadcasts/Requests data from network.
6.  **Backend (WS)**: Pushes "Thinking..." log to Android.
7.  **App**: Updates UI with log.

## Consequences

- **Pros**: 
    - Agent can run 24/7 on a server without killing Android battery.
    - Python backend allows complex logic updates without App Store review.
- **Cons**: 
    - User needs connectivity to their Agent Node.
