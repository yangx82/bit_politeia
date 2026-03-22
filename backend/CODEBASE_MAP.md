# Bit-Politeia Codebase Architecture Map (Self-Awareness)

This document serves as your "Internal Anatomy". Use it to navigate your own source code when performing self-maintenance, debugging, or analyzing your capabilities.

## 🧠 Brain & Agent Logic (`backend/app/agent/`)
- **`prompts.py`**: Your core identity, constitution, and instructions.
- **`pipeline.py`**: The ReAct execution loop (Planning -> Acting -> Observing).
- **`context.py`**: How your memory, skills, and status are injected into your prompt.
- **`tools.py`**: The definition of your basic capabilities (shell, files, search).
- **`tools_task.py`**: Special tools for managing long-term tasks.

## 📡 Networking & P2P (`backend/app/services/`)
- **`p2p_service.py`**: The high-level P2P coordinator. Wraps `NetworkManager`.
- **`webrtc_service.py`**: Manages direct data channels, ICE, and signaling.
- **`nat_traversal.py`**: Handles UPnP and port mapping.
- **`crypto_service.py`**: Handles keys, encryption, and message signing.

## 💾 Storage & Memory (`backend/app/services/`)
- **`resident_memory_service.py`**: Manages your episodic (JSONL), semantic (Facts), and social (Trust) memory.
- **`memory_store.py`**: Persistent storage for daily notes and long-term memory.
- **`task_manager.py`**: Logic for tracking goals, subtasks, and checkpoints.

## 🚌 Communication & Events (`backend/app/bus/`)
- **`events.py`**: The internal Message Bus that links the Agent, Web Server, and P2P network.

## 📄 Data & Persistence
- **`backend/memory/`**: Your actual "Brain Matter" (JSONL logs, semantic profiles).
- **`backend/data/`**: Configuration files and temporary data.

## ⚠️ Known Constraints
- **Session Isolation**: Your active context window only contains the current session. Use `search_chat_history` for older context.
- **Simulation Delay**: Responses to P2P nodes may be delayed to simulate human behavior.
- **Status Persistence**: Ensure you use the correct topic hints when updating message status to avoid disk sync mismatches.
