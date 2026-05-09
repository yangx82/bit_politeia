---
name: literature-watcher
description: Periodic academic literature monitoring and incremental briefing. Tracks multiple databases (OpenAlex, PubMed, arXiv, Semantic Scholar) and generates automated briefs of new publications since the last report. Maintains a historical database to prevent duplicate notifications.
allowed-tools: [Read, Write, Edit, Bash]
license: MIT license
metadata:
    skill-author: BitPoliteia Agent
---

# Literature Watcher

## Overview

A specialized skill for periodic surveillance of scientific literature. Unlike the one-off `literature-review`, this skill is designed for ongoing monitoring. It uses a local SQLite database to track every paper "seen" by the agent, ensuring that periodic briefs only contain truly new findings.

## Key Features

1.  **Incremental Updates**: Only searches and reports papers published after the previous briefing or a specified interval.
2.  **OpenAlex Integration**: Leverages the OpenAlex "polite pool" for high-performance, cross-disciplinary retrieval.
3.  **Historical Deduplication**: Cross-references DOI, ID, Title, and Abstract Content Hash against a permanent local database.
4.  **Thematic Synthesis**: Summarizes newly found literature into a cohesive briefing document.

## Tools

### watcher_periodic_update

Executes a monitoring pass for a given topic and generates a briefing if new literature is found.

**Arguments:**
- `topic`: (string) The research area or keywords to monitor.
- `interval_days`: (int, default=7) How many days to look back if no history exists.
- `output_dir`: (string, optional) Where to save the generated brief.

**Usage:**
```bash
python scripts/generate_brief.py --topic "Decentralized Governance" --interval 14
```

## Implementation Workflow

### 1. Incremental Search
The script queries OpenAlex using the `from_publication_date` filter, combined with a search for the requested topic.

### 2. Historical Filtering
Every result is checked against the local `watcher_history.db`. If a DOI or highly similar title is found, the paper is skipped.

### 3. Database Update
Newly identified papers are added to the history so they aren't reported in future runs.

### 4. Briefing Generation
An AI-optimized summary of the new papers is created using a professional Markdown template.

## Requirements

- Python `requests` package.
- `sqlite3` (standard library).
- A valid `OPENALEX_EMAIL` in `.env` (recommended for faster API access).
