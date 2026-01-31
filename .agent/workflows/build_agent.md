---
description: Build Agent for CI/CD, code quality checks, and build verification.
---
# Build Agent

This workflow guides the agent to ensure code quality and build stability before commits.

## Step 1: Code Quality Checks

Run these checks to maintain code standards.

1.  **Format**: Ensure code is formatted.
    *   Command: `npm run format` (or `npx prettier --write .`)
2.  **Lint**: Catch potential errors.
    *   Command: `npm run lint` (or `npx eslint .`)
3.  **Type Check**: Verify TypeScript types.
    *   Command: `npm run typecheck` (or `npx tsc --noEmit`)

## Step 2: Testing

Validate functionality.

1.  **Unit Tests**: Run unit tests for logic.
    *   Command: `npm run test` (or `npx vitest run`)
2.  **Integration Tests**: Run integration tests if available.

## Step 3: Build Verification

Ensure the project builds for production.

1.  **Dry Run Build**: Attempt a build to catch compilation errors.
    *   Command: `npm run build`
    *   For Workers: `npx wrangler deploy --dry-run`

## Step 4: Error Handling

If any check fails:

1.  **Analyze**: Read the error output carefully.
2.  **Fix**: Correct the code causing the error.
3.  **Retry**: Re-run the failing check until it passes.
4.  **Block**: DO NOT proceed to commit if checks are failing.
