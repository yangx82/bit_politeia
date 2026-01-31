---
description: Deploy Agent for production deployment and changelog generation.
---
# Deploy Agent

This workflow guides the agent to deploy applications and manage releases.

## Step 1: Pre-Deployment Checks

Ensure the application is ready for production.

1.  **Tests**: Confirm all tests pass.
    *   Command: `npm run test`
2.  **Build**: Ensure a fresh build is created.
    *   Command: `npm run build`

## Step 2: Production Deployment

Deploy the application to Cloudflare.

1.  **Deploy**: Use Wrangler to deploy.
    *   Command: `npx wrangler deploy`
2.  **Verify Output**: Check for "Published" success message and the deployed URL.

## Step 3: Changelog Generation

Generate a release log.

1.  **Git Log**: Get recent commits.
    *   Command: `git log --pretty=format:"- %s (%h)" --no-merges -n 20`
2.  **Format**: Group changes by type (Features, Fixes, Chore).
    *   Example:
        ```markdown
        ### Features
        - Add login page (abc1234)
        ### Fixes
        - Fix typo in header (def5678)
        ```

## Step 4: Post-Deployment Verification

Verify the live application.

1.  **Health Check**: Curl the deployed URL.
    *   Command: `curl https://<your-worker>.workers.dev/health` (or `/`)
2.  **Manual Check**: Visit the URL in a browser if applicable.
