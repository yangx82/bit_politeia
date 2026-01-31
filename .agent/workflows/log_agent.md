---
description: Log Agent for development progress tracking, summaries, and retrospectives.
---
# Log Agent

This workflow guides the agent to document development sessions and reflect on progress.

## Step 1: Read Progress

Understand the current status.

1.  **Read Task List**: Read `task.md` (or equivalent) to see what was planned vs. completed.
    *   Action: `view_file task.md`

## Step 2: Analyze Commits

Review recent changes.

1.  **Git Log**: detailed log of recent work.
    *   Command: `git log --stat -n 20`
2.  **Summary**: Identify key technical changes (e.g., "Refactored auth module", "Added database schema").

## Step 3: Generate Summary

Create a development log entry.

1.  **Completed Items**: List tasks marked as [x].
2.  **Technical Decisions**: Note important choices (e.g., "Chose kv over d1 for session storage").
3.  **Challenges**: Mention any blockers or bugs encountered.

## Step 4: Retrospective

Reflect on the session.

1.  **What went well**: (e.g., "Fast implementation of feature X").
2.  **Areas for improvement**: (e.g., "Need better test coverage for Y").
3.  **Next Steps**: What should be tackled next session?
