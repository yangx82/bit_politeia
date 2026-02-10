# Bit Politeia Android App Architecture Plan

## Goal Description
Design a P2P Android application "Bit Politeia" (比特理想国), a scientific research community where "Residents" (users) are represented by "AI Agents" (Nodes). The system relies on reputation, virtual currency (Stater), and blockchain-based evidence.

## User Review Required
- [ ] **Architecture**: Confirm the "Agent-First" P2P architecture.
- [ ] **Tech Stack**: Confirm usage of Kotlin/Compose and Libp2p for mobile P2P.
- [ ] **AI Model**: Confirm BYO-Key (Bring Your Own Key) approach for Agent LLMs (GPT, DeepSeek, etc.).

## Proposed Changes

### Documentation (Docs)
#### [NEW] [ADR 001 - Technology Stack](docs/adr/0001-technology-stack.md)
- **Frontend**: Android Native (Kotlin, Jetpack Compose).
- **Network**: Libp2p (for P2P inter-node communication).
- **AI Integration**: HTTP Clients for LLM APIs (OpenAI format).
- **Database**: Room (Local SQLite).
- **Ledger**: Minimal Block structure stored locally + consolidated via P2P consensus (Mock implementation for initial phase).

#### [NEW] [ADR 002 - Application Architecture](docs/adr/0002-application-architecture.md)
- **Pattern**: MVVM + Clean Architecture.
- **Core Component**: `AgentService` - A background service that manages the AI Agent's lifecycle, handles P2P messages independently of UI, and interacts with LLMs.
- **Data Flow**: Network Events -> Agent Service -> Repository -> Local DB -> UI (Flow).

### Project Structure (Preliminary)
- `app/src/main/java/com/bitpoliteia/`
    - `core/`: Base classes, DI (Hilt), Network logic.
    - `agent/`: AI Logic, Prompt Engineering, Decision Engine.
    - `p2p/`: Libp2p wrapper and node management.
    - `data/`: Room Database, Repositories.
    - `ui/`: Jetpack Compose Screens (Chat, Proposals, Wallet).

## Verification Plan
### Review Process
- User to review the generated ADRs and this plan.
