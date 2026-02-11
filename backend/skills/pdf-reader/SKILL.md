---
name: pdf-reader
description: Extracts text from PDF files for analysis. Use when user wants to read a PDF, summarize a document, or extract content from a research paper.
---

# PDF Reader

Extracts text content from PDF files.

## Quick Start
To read a PDF file:
1. Locate the file path (e.g., `D:\docs\paper.pdf`).
2. Call `pdf-reader_read_pdf(arguments="D:\\docs\\paper.pdf")` for the whole file.
3. Call `pdf-reader_read_pdf(arguments="D:\\docs\\paper.pdf --start 1 --end 5")` for a specific page range.

## Capabilities
- Extract full text from PDF
- Handles multi-page documents
- Support for reading specific page ranges (--start, --end)
