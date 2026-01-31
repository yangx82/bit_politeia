---
description: Workflow for constructing and invoking agents, involving LLM selection (local/cloud), prompt engineering, and tool customization.
---

1.  **Analyze Agent Requirements**
    -   **Goal Definition**: Clearly define what the agent needs to accomplish.
    -   **Constraints**: Identify constraints regarding data privacy, latency, cost, and hardware availability.

2.  **Select & Deploy Large Language Model (LLM)**
    -   **Model Selection**:
        -   **Cloud Models**: Recommend top-tier models (chatGPT, Claude, Gemini) for complex reasoning and general knowledge.
        -   **Local Models**: Recommend open-weight models (Llama 3, Mistral, Qwen) for privacy-sensitive or offline scenarios.
    -   **Deployment Strategy**:
        -   **Cloud**: Configure API clients and manage secrets securely.
        -   **Local**: specific steps for local inference (e.g., using Ollama, LM Studio, or vLLM).

3.  **Prompt Engineering**
    -   **System Prompt**: Draft a comprehensive system prompt defining the agent's persona, role, and strict interaction rules.
    -   **Context Management**: Define how the agent handles context window (RAG, memory summaries).
    -   **Refinement**: iteratively test and refine prompts to minimize hallucinations and improve adherence to instructions.

4.  **Tool Customization & Selection**
    -   **Capability Mapping**: Map requirements to specific tools (e.g., calculator, web search, database access).
    -   **Tool Definition**:
        -   **Existing Tools**: Select from standard libraries.
        -   **Custom Tools**: Define schemas (JSON) and implement handler functions for specialized tasks.

5.  **Agent Assembly & Integration**
    -   **Framework**: Choose an orchestration framework if needed (LangChain, AutoGen) or build a custom loop.
    -   **Integration**: Connect the agent to the main application logic (e.g., API endpoints, event handlers).

6.  **Verification & Optimization**
    -   **Testing**: Run test cases to verify tool usage and reasoning.
    -   **Optimization**: Tune parameters (temperature, top_p) and optimize prompt length for cost/speed.
