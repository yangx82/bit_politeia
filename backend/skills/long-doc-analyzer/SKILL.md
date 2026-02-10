---
name: long-doc-analyzer
description: Summarizes long documents (PDF/Text) using Map-Reduce. Use when existing context window is insufficient for a large file.
---

# Long Document Analyzer

Analyzes and summarizes long documents that exceed the Agent's context window.
Uses a **Map-Reduce** strategy:
1.  **Map**: Splits document into chunks and generates summaries for each chunk.
2.  **Reduce**: Aggregates chunk summaries into a final coherent summary.

## Capabilities
- **Summarize**: Generate a comprehensive summary of a long PDF or Text file.
- **Analyze**: (Future) Extract specific topics across the whole document.

## Usage

To summarize a long document:

1.  **Get Configuration**: Retrieve your current `api_key`, `base_url`, and `model` from your configuration or environment.
2.  **Call Script**:
    ```python
    python backend/skills/long-doc-analyzer/scripts/summarize.py <file_path> --api_key <key> --base_url <url> --model <model>
    ```

### Arguments
- `file_path`: Path to the target file (.pdf or .txt).
- `--api_key`: (Required) LLM API Key.
- `--base_url`: (Optional) LLM Base URL (default: from env or standard).
- `--model`: (Optional) LLM Model to use (default: gpt-4o).
- `--chunk_size`: (Optional) Characters per chunk (default: 10000).

### Example
```python
# Summarize a research paper
python backend/skills/long-doc-analyzer/scripts/summarize.py "D:\papers\long_paper.pdf" --api_key "sk-..." --base_url "https://api.openai.com/v1"
```
