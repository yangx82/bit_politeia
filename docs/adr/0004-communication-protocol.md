# 4. Frontend-Backend Communication Protocol

Date: 2026-01-11

## Status

Proposed

## Context

The Android App (Frontend) needs to control and monitor the Python Agent (Backend). The interaction includes:
- Sending instructions ("Vote YES on proposal X").
- Viewing real-time logs ("Agent is chatting with Node B...").
- Receiving alerts ("New Proposal received").
- Onboarding config (Setting API Keys).

## Decision

We will expose a **REST API** and a **WebSocket Endpoint** on the Python Backend.

### API Endpoints (Examples)

- `POST /api/v1/config`: Set LLM Key, Identity.
- `GET /api/v1/status`: Get Agent Status (Reputation, Balance, Group).
- `POST /api/v1/chat/instruction`: User sends message to Agent.
- `GET /api/v1/history/messages`: Get chat history.
- `GET /api/v1/history/logs`: Get event logs.

### WebSocket Events

- `/ws/events`:
    - `{"type": "new_message", "data": {...}}`
    - `{"type": "log_entry", "data": "Connecting to peer Qm..."}`
    - `{"type": "proposal_alert", "data": {...}}`

### Authentication
- **Token-based**: Generated during initial setup. The App generates a token and passes it to the Backend? Or Backend generates a pairing code?
- **Simplification**: API Key header `X-Agent-Auth` generated during first run.

## Consequences

- **Pros**: Standard, debuggable, allows multiple frontends (e.g., Web Dashboard later).
- **Cons**: Real-time sync requires managing connection state.
