---
name: pdf-reader
description: Extracts text from PDF files for analysis. Use when user wants to read a PDF, summarize a document, or extract content from a research paper.
---

# PDF Reader

Extracts text content from PDF files.

## Quick Start

```python
# To use this skill, the agent will call the tool with the file path.
import json
print(json.dumps({"text": "Extracted text..."}))
```

## Core Workflow

1.  **Locate File**: The user provides a path to a PDF file.
2.  **Read PDF**: The `read_pdf.py` script opens the file and extracts text page by page.
3.  **Return Content**: The text is returned as a JSON object.

## Important Rules

- **ALWAYS** provide an absolute path to the PDF file.
- **NEVER** try to read encrypted PDFs without a password (not supported yet).
