# Bit Politeia Development

## Build and Tests
- Backend: `pip install -r requirements.txt` (or use conda environment `bit_politeia`)
- Run tests: `pytest`
- Run local server: `python main.py`

## Git Commit Conventions
We use **Conventional Commits** for all changes.
- Format: `type(scope): subject`
- Types: `feat`, `fix`, `refactor`, `perf`, `test`, `ci`, `docs`, `chore`, `style`, `security`
- Scope: kebab-case (e.g., `p2p-community`, `agent-service`, `gateway`, `schemas`)
- Subject: present tense imperative, no period, max 50 chars.

### Summary of Change
Provide a brief summary of WHAT was changed and WHY (if not obvious).
Reference any relevant Task IDs or Requirements.
 
+## Environment and Tooling
+- **File Searching**: DO NOT use `grep` or `ripgrep`. Use PowerShell's `Select-String` exclusively for searching text within files on Windows.
+- **OS Portability**: For core logic (like the Universal Search tool), use Python-native libraries (sqlite3/chromadb) to ensure cross-platform compatibility without shell-specific dependencies.
