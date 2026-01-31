---
description: Cloudflare Workers Coding Agent for high-performance, secure, and type-safe serverless code.
---
# Cloudflare Workers Coder

This workflow guides the agent to write production-ready Cloudflare Workers code.

## Step 1: TypeScript & Environment Setup

1.  **Strict Typing**: ALWAYS use TypeScript with `strict: true`.
2.  **No `any`**: Avoid `any`. Use `unknown` with validation or generic types.
3.  **ES Modules**: Use ES Module syntax (`import`/`export`).
4.  **Env Interface**: Define an `Env` interface for bindings.

```typescript
interface Env {
  MY_KV: KVNamespace;
  DB: D1Database;
  BUCKET: R2Bucket;
  CHAT_DO: DurableObjectNamespace;
}
```

## Step 2: Resource Integration

Use efficient patterns for Cloudflare resources.

1.  **D1 (SQL)**: usage `stmt.bind().all()` or `.first()`. Prevent SQL injection by ALWAYS using bindings.
2.  **KV (Key-Value)**: Use for high-read configurations. Handle `null` returns gracefully.
3.  **R2 (Object Storage)**: Use for file uploads.
4.  **Queues**: Use `batch` processing in consumer workers to reduce invocations.

## Step 3: Real-Time Features (WebSocket & Durable Objects)

For stateful or real-time needs:

1.  **Durable Objects**: Use for consistency (e.g., chat rooms, counters).
2.  **WebSocket Hibernation**: Use the WebSocket Hibernation API for scale.
    *   `state.acceptWebSocket(ws)`
    *   `webSocketMessage(ws, msg)` handler
    *   `webSocketClose(ws, code, reason)` handler

## Step 4: Security & Validation

NEVER skip these checks.

1.  **Input Validation**: Use **Zod** or **Valibot** to validate request bodies and parameters.
2.  **CORS**: Handle `OPTIONS` requests and set strict `Access-Control-Allow-Origin`.
3.  **CSRF**: Validate Origin/Referer headers or use tokens for state-changing requests.
4.  **Secrets**: Never hardcode secrets. Use `wrangler secret put`.
