---
description: Cross-Platform App Architect for full-stack evaluation, deployment assessment, and ADR generation.
---
# Cross-Platform App Architect

This workflow guides the agent to design cross-platform application architectures.

## Step 1: Full-Stack Technology Evaluation

Recommend technologies based on requirements.

### Frontend
| Framework | Best For | Pros | Cons |
| :--- | :--- | :--- | :--- |
| **React Native** | iOS/Android apps | Large ecosystem, JS/TS | Native bridge overhead |
| **Flutter** | iOS/Android/Web/Desktop | Single codebase, fast UI | Dart learning curve |
| **Expo** | Rapid prototyping | Easy dev experience | Less native control |
| **Web (React/Vue)** | Browser-based apps | Maximum reach | No native features |

### Backend
| Language/Framework | Best For | Pros | Cons |
| :--- | :--- | :--- | :--- |
| **Node.js (TS)** | Real-time, I/O heavy | Fast dev, large ecosystem | Single-threaded |
| **Go** | High performance, microservices | Concurrency, binary deploy | Verbose error handling |
| **Rust** | Systems, WebAssembly | Memory safe, blazing fast | Steep learning curve |
| **Python (FastAPI)** | ML/AI integration, scripting | Rapid dev, rich libs | GIL limitations |

## Step 2: Platform Deployment Assessment

Evaluate deployment difficulty for each target.

| Platform | Difficulty | Key Challenges | Recommended Tooling |
| :--- | :---: | :--- | :--- |
| **Web** | ⭐ Easy | CDN setup, caching | Cloudflare Pages, Vercel |
| **Android** | ⭐⭐ Medium | Play Store policies, fragmentation | Gradle, Fastlane |
| **iOS** | ⭐⭐⭐ Hard | App Store review, signing | Xcode, Fastlane, TestFlight |
| **Desktop (Electron)** | ⭐⭐ Medium | Auto-updates, native packaging | electron-builder |
| **Desktop (Tauri)** | ⭐⭐ Medium | Rust knowledge, OS APIs | Tauri CLI |

## Step 3: Architecture Decision Record (ADR)

Generate an ADR using this template.

```markdown
# ADR-[Number]: [Title]

## Status
[Proposed | Accepted | Rejected | Deprecated]

## Context
[Description of requirements, constraints, and why this decision is needed.]

## Decision
[The chosen architecture. E.g., "Use Flutter for frontend, Go for backend, deploy via Cloudflare."]

## Alternatives Considered
[Other options evaluated and why they were not chosen.]

## Consequences
*   **Positive**: [Benefits, e.g., Code reuse across platforms, faster time-to-market]
*   **Negative**: [Drawbacks, e.g., Flutter's Dart ecosystem is smaller than JS]
*   **Risks**: [Potential risks and mitigation strategies]
```
