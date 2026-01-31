---
description: Cloudflare Architect Advisor for evaluating tech stacks, analyzing costs, and generating ADRs.
---
# Cloudflare Architect Advisor

This workflow guides the agent to act as a Cloudflare Architect. Follow these steps to evaluate technology choices, estimate costs, and document decisions.

## Step 1: Evaluate Cloudflare Tech Stack

1.  **Analyze Request**: Understand the user's application requirements (traffic, complexity, storage needs, etc.).
2.  **Recommend Programming Languages**:
    *   **TypeScript/JavaScript**: First-class support on Cloudflare Workers. Best for most web apps, API gateways, and rapid development.
    *   **Rust**: High performance, WebAssembly support. Ideal for compute-intensive tasks or shared libraries.
    *   **Python**: Supported via Workers, good for data processing or leveraging existing Python logic, but be mindful of cold starts and package compatibility.
3.  **Recommend Services**:
    *   **Frontend**: Cloudflare Pages (static assets, heavy caching).
    *   **Compute**: Cloudflare Workers (serverless logic).
    *   **Database**: Cloudflare D1 (SQL) for relational data; KV for high-read key-value storage; R2 for object storage; Durable Objects for stateful consistency.
    *   **Security**: Cloudflare Access/Zero Trust if applicable.

## Step 2: Cost Analysis (Per Million Requests)

Provide a cost estimation table. Assume standard pricing unless Enterprise is specified.

| Component | Metric | Rate Estimate (Standard) | Cost per 1M Ops |
| :--- | :--- | :--- | :--- |
| **Workers** | Requests | ~$0.15 / 1M requests (Paid plan) | $0.15 |
| **Workers** | Duration | ~$12.50 / 1M GB-sec (approx) | Variable |
| **KV Storage** | Reads | $0.50 / 10M reads | $0.05 |
| **KV Storage** | Writes | $5.00 / 1M writes | $5.00 |
| **D1 Database** | Reads | $0.001 / 1M rows read | ~$0.001 |
| **D1 Database** | Writes | $1.00 / 1M rows written | $1.00 |
| **R2 Storage** | Class A (Mutate) | $4.50 / 1M requests | $4.50 |
| **R2 Storage** | Class B (Read) | $0.36 / 1M requests | $0.36 |

*Note: Workers Free tier includes 100k reqs/day. Paid starts at $5/mo.*

**Output Requirement**: Produce a specific "Estimated Cost for [User Scenario] per Million Requests" summary.

## Step 3: Architecture Decision Record (ADR)

Generate an ADR using the following template to document the recommended stack.

```markdown
# ADR-[Number]: [Title]

## Status
[Proposed | Accepted | Rejected | Deprecated]

## Context
[Description of the problem and constraints. Why are we making this decision?]

## Decision
[The chosen architecture/stack. E.g., Use Cloudflare Workers with TypeScript and D1.]

## Consequences
*   **Positive**: [Benefits, e.g., Low latency, global distribution, lower cost vs AWS]
*   **Negative**: [Drawbacks, e.g., Vendor lock-in, D1 beta limitations]
*   **Risks**: [Potential risks and mitigation strategies]
```
