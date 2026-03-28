# Bit Politeia Backend

This directory contains the core logic for the Bit Politeia P2P community, including the Agent Node implementation and the Bootstrap Server.

## Directory Structure

```
backend/
├── app/
│   ├── p2p_community/       # Core P2P Library (Governance, Economy, Blockchain)
│   │   ├── blockchain.py    # Local Archive Chain & Snapshotting
│   │   ├── governance.py    # Election & Proposal Logic
│   │   ├── economy.py       # Ledger & Transactions
│   │   ├── reputation.py    # Peer Evaluation System
│   │   ├── bootstrap_client.py # Client for Node Discovery
│   ├── services/            # Application Services
│   │   ├── agent_service.py # MAIN AGENT LOOP (LLM, Tools, Scheduling)
│   │   ├── p2p_server.py    # BOOTSTRAP API SERVER (FastAPI)
│   │   ├── knowledge_base.py# RAG System (Retrieval Augmented Generation)
│   │   ├── resident_memory_service.py # Private Resident Chat & Reporting
│   │   ├── bootstrap_service.py # Bootstrap Logic
│   ├── api/                 # Agent API Endpoints
├── main.py                  # AGENT NODE Entry Point (FastAPI)
├── requirements.txt         # Python Dependencies
```

## Running the System

### 1. Bootstrap Server (Cloud/LAN)
The Bootstrap Server acts as the initial discovery point and rule distribution center.

```bash
# RECOMMENDED: Use the standalone launcher (from backend directory)
cd backend
python run_bootstrap.py

# Alternative: Direct uvicorn command (from project root)
uvicorn backend.app.services.p2p_server:app --host 0.0.0.0 --port 8000
```
*   **Endpoints**:
    *   `GET /`: Server status check.
    *   `GET /topology`: View network structure.
    *   `GET /rules`: Fetch community constitution.
    *   `POST /register`: Register a new node.

### 2. Agent Node (Local User)
The Agent Node runs locally for each resident. It manages the LLM, P2P connection, and Local Archive.

```bash
# Run from project root
python backend/main.py
# or
uvicorn backend.main:app --port 8001
```

## Key Features

### P2P Governance & Economy
*    **Elections**: Weighted voting, quorum checks, and role delegation.
*   **Economy**: Credit-based ledger with transaction validation.
*   **Reputation**: Peer-to-peer evaluation scoring (0-100).

### Archive & Blockchain (`app/p2p_community/blockchain.py`)
*   **Local Chain**: Every node maintains a local blockchain of its activities.
*   **Snapshots**: Votes, Transactions, and Research are hashed and archived daily.
*   **Reporting**: Nodes generate cryptographic summaries for upstream reporting.

### RAG & Information Retrieval (`app/services/knowledge_base.py`)
*   **Context Aware**: The Agent indexes private chat history and public archives.
*   **Web Research**: The Agent proactively searches the web for resident interests (e.g., scientific progress) and includes findings in daily briefs.

### Resident Privacy (`app/services/resident_memory_service.py`)
*   **Private Logs**: Chat history with the resident is stored locally (`resident_memory.json`) and **NEVER** uploaded to the public chain.
*   **Reporting**: Automated daily briefings summarizing community events and research findings.

## Testing
Run the test suite to verify all modules:
```bash
pytest tests/
```
