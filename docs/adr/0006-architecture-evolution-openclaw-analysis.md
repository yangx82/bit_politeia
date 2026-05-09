# ADR 0006: Architecture Evolution - OpenClaw Analysis & The "Neural Gateway"

## Status
Proposed

## Context
We examined the [OpenClaw](https://github.com/openclaw/openclaw) architecture to identify improvements for Bit Politeia's agent system (Nanobot). OpenClaw is a sophisticated local-first AI assistant with a modular "Gateway" architecture.

### OpenClaw Architecture Highlights
1.  **WebSocket Gateway**: A central control plane (`ws://...`) that connects all components (Agent Runtime, UI, Mobile Nodes). It is the "nervous system."
2.  **Node Abstraction**: External devices (phones, desktops) pair as "Nodes" that expose capabilities (Tools) to the agent.
3.  **Sandboxing**: Application of Docker for isolating untrusted sessions.
4.  **Session Management**: Explicit session objects for managing state across different interaction modes.

### Current Bit Politeia (Nanobot) Architecture
1.  **In-Process MessageBus**: `backend/app/bus/queue.py` handles decoupling, but is limited to the local process.
2.  **Embedded Agent**: `AgentService` is tightly coupled to the FastAPI app lifecycle.
3.  **Local Tooling**: Tools are executed locally; no standardized way to invoke tools on remote "nodes" (peers).

## Proposal: The "Neural Gateway" Pattern

To evolve Bit Politeia into a true P2P Intelligent Agent network, we propose adopting a **Neural Gateway** pattern.

### 1. WebSocket Gateway Endpoint
**Change**: Expose the internal `MessageBus` via a WebSocket endpoint (`/ws/gateway`).
**Benefit**: 
- Enables a separated Frontend (React) to interface directly with the Agent's event stream.
- allows "Remote Control" of the agent.
- Mirrors OpenClaw's flexibility where the "Brain" (Agent) can be decoupled from the "Body" (Gateway).

### 2. P2P Nodes as Tool Providers
**Change**: Extend the P2P protocol to treat connected peers as "Nodes" that advertise capabilities.
**Benefit**: 
- Instead of just routing messages, the Agent can *use* a peer's tools (e.g., "Ask Peer A to validate transaction X").
- Maps OpenClaw's "Device Nodes" concept to "P2P Resident Nodes".

### 3. Asynchronous Agent Runtime
**Change**: Refactor `AgentService` to run as an independent consumer loop, unrelated to HTTP request/response cycles.
**Benefit**: 
- The agent persists and "thinks" even without active web requests.
- Better resilience and state management.

### 4. Context-Aware Sandboxing
**Change**: Implement a sandbox (Docker or tailored environment) for executing P2P-derived code or tools.
**Benefit**: Security for the collaborative P2P environment.

## Comparison Table

| Component | OpenClaw | Bit Politeia (Current) | Bit Politeia (Proposed) |
| :--- | :--- | :--- | :--- |
| **Control Plane** | WS Gateway (Standalone) | In-Process MessageBus | **Hybrid**: Internal Bus + WS Bridge |
| **Agent Runtime** | RPC Client | Embedded Service | **Async Worker** (Bus Consumer) |
| **Remote Capability** | Paired Device Nodes | None (Local only) | **P2P Resident Nodes** |
| **UI** | Decoupled (Web/App) | Mixed (FastAPI/Jinja/React) | **Decoupled** (React via WS) |

## Consequences
- **Positive**: significantly more modular; enables complex P2P agent interactions; "future-proofs" the architecture.
- **Negative**: Increases complexity (WS management, Async loops). Requires careful error handling for disconnected nodes.
