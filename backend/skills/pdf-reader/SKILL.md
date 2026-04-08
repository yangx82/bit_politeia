---
name: pdf-reader
description: Extracts text from PDF files for analysis. Use when user wants to read a PDF, summarize a document, or extract content from a research paper. Supports intelligent chunked reading for large documents to avoid API timeout.
---

# PDF Reader (Enhanced v2.0)

Extracts text content from PDF files with **intelligent chunked reading** to prevent API timeout on large documents.

## ✨ New Features (v2.0)

| Feature | Description |
|:---|:---|
| **Auto-mode** | Automatically switches to chunked reading for documents > 30 pages |
| **Chunked reading** | Processes large PDFs in manageable chunks (default 10 pages) |
| **Output file** | Saves summary to temp file for later analysis |
| **Info mode** | Quick metadata extraction without full reading |

## Quick Start

### Basic Usage
```python
# Read entire PDF (auto-switches to chunked mode if > 30 pages)
pdf-reader_read_pdf(arguments="path/to/file.pdf")

# Read specific page range
pdf-reader_read_pdf(arguments="path/to/file.pdf --start 1 --end 10")
```

### Intelligent Chunked Reading (Recommended for Large Docs)
```python
# Auto-chunk mode: reads in 10-page chunks
pdf-reader_read_pdf(arguments="path/to/file.pdf --mode chunked")

# Custom chunk size (5 pages per chunk)
pdf-reader_read_pdf(arguments="path/to/file.pdf --mode chunked --chunk-size 5")

# Save output to temp file (recommended)
pdf-reader_read_pdf(arguments="path/to/file.pdf --mode chunked --output temp/pdf_summary.md")
```

### Quick Info Check
```python
# Get document metadata only (fast, no content)
pdf-reader_read_pdf(arguments="path/to/file.pdf --info")
```

## Modes

| Mode | Description | Best For |
|:---|:---|:---|
| `full` | Read entire document at once | Small PDFs (< 30 pages) |
| `chunked` | Read in chunks, summarize each | Large PDFs (30+ pages) |
| `auto` | Auto-detect size, switch to chunked if needed | **Default, recommended** |

## Parameters

| Parameter | Description | Default |
|:---|:---|:---|
| `--start` | Start page (1-based) | 1 |
| `--end` | End page (1-based) | last page |
| `--mode` | Reading mode: full/chunked/auto | auto |
| `--chunk-size` | Pages per chunk (chunked mode) | 10 |
| `--output` | Output file path (optional) | stdout |
| `--info` | Show PDF metadata only | false |

## 🛡️ Anti-Timeout Strategy

### When encountering "Error communicating with LLM (Request timed out)"

| Solution | Command |
|:---|:---|:---|
| **Use chunked mode** | `--mode chunked --chunk-size 5` |
| **Save to file** | `--output temp/summary.md` |
| **Manual page range** | `--start 1 --end 5` |

### Recommended Workflow for Large Documents (> 30 pages)

```python
# Step 1: Get document info first
pdf-reader_read_pdf(arguments="large_doc.pdf --info")

# Step 2: Read in chunked mode with output file
pdf-reader_read_pdf(arguments="large_doc.pdf --mode chunked --chunk-size 10 --output temp/doc_chunks.md")

# Step 3: Read the generated summary file
read_file(path="temp/doc_chunks.md")

# Step 4: Process each chunk with LLM (if needed)
# ... analyze content in manageable pieces ...
```

## Best Practices

### ✅ DO
- Use `--mode auto` for unknown document sizes
- Use `--output temp/summary.md` for large documents
- Check `--info` first for quick metadata
- Use `--chunk-size 5` for very dense documents

### ❌ DON'T
- Read entire 50+ page PDF without chunked mode
- Ignore timeout errors (switch to chunked instead)
- Use `--mode full` for documents > 30 pages

## Example Output (Chunked Mode)

```
=== Chunked Reading Mode ===
Total pages: 55
Chunk size: 10 pages
Estimated chunks: 6
========================================

--- Chunk 1: Pages 1-10 ---
[Content...]

--- Chunk 2: Pages 11-20 ---
[Content...]

...

=== Reading Summary ===
Total chunks processed: 6
Chunk 1: Pages 1-10 - 2500 chars
Chunk 2: Pages 11-20 - 2800 chars
...

✅ Summary saved to: temp/pdf_summary.md
```

## Version History

| Version | Changes |
|:---|:---|
| v2.0 | Added chunked reading, auto-mode, output file, info mode |
| v1.0 | Basic PDF text extraction |