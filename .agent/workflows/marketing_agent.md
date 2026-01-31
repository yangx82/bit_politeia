---
description: Marketing Agent for converting technical logs into user-centric marketing stories (Chinese).
---
# Marketing Agent

This workflow guides the agent to bridge the gap between technical engineering and user value.

## Step 1: Input Analysis

Read technical updates.

1.  **Read Logs**: Check `logs/deploy/` or ask the user for the latest changes/commits.
    *   Command: `view_file` relevant logs or `git log`.
2.  **Understand**: Identify what changed technically (e.g., "Refactored WebSocket handling").

## Step 2: Theme Extraction

Find the story.

1.  **Technical to Value**: Map tech changes to user benefits.
    *   *Example*: "Fixing duplicate forks" -> "Reliability & Trust".
    *   *Example*: "Optimized database queries" -> "Blazing Fast Speed".
2.  **Select Theme**: Choose one core theme for the article.

## Step 3: Article Generation (Chinese)

Write the article using the following structure.

### Structure
*   **Headline**: A catchy, non-technical title. (e.g., "为什么我们把这个图标变成了咖啡色？")
*   **The "Why"**: Start with the user pain point. (e.g., "大家都不喜欢等待...")
*   **The "What"**: Introduce the solution/update. (e.g., "所以我们重构了核心引擎...")
*   **The "Wow"**: Highlight design/engineering details. (e.g., "通过使用 Durable Objects...")

## Step 4: Output

Save the article.

1.  **File naming**: `articles/marketing_<topic>_<date>.md`.
