# 1. Technology Stack Selection (Frontend-Backend Split)

Date: 2026-01-11

## Status

Proposed

## Context

The system is divided into two distinct parts: a user-facing mobile app and an autonomous intelligent agent node. The User requested Python for the backend to leverage its AI ecosystem.

## Decision

We will use the following technology stack:

### Frontend (Android App)
- **Language**: Kotlin
- **UI**: Jetpack Compose
- **Role**: Interface for user input, notifications, and visualization. It does *not* run the heavy P2P/AI logic directly.
- **Networking**: Retrofit (HTTP), Scarlet/OkHttp (WebSocket).

### Backend (Intelligent Node)
- **Language**: Python 3.10+
- **Framework**: **FastAPI** (for App communication).
- **AI Framework**: **LangChain** (for Agent reasoning and LLM interaction).
- **P2P Library**: **python-libp2p** (or a bipy implementation if maintenance is an issue, but standard libp2p is preferred).
- **Database**: **SQLite** (structured data) + **LevelDB** (Blockchain raw data).
- **Scheduling**: **APScheduler** (for periodic tasks like Reputation updates).

### Communication
- **Protocol**: HTTP (Command/Query) + WebSocket (Real-time Event Stream).
- **Payload**: JSON.

## Consequences

- **Pros**: 
    - Python has the best libraries for AI (LangChain, NumPy, Pandas for reputation math).
    - Clear separation of concerns: UI performance isn't bogged down by P2P logic.
- **Cons**: 
    - Deployment complexity: User needs to run the Python Node somewhere (Cloud, PC, or embedded in Android via specialized tools). *We assume a "Personal Server" model for now unless "On-Device Python" is explicitly mandated.*
