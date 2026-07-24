# AGENTS.md - Project Context for AI Assistants

This document provides essential context, philosophy, and technical guidelines for AI agents working on the EzQL project.

## Project Overview
**EzQL** is an autonomous data analyst interface. Its primary goal is to democratize data analytics by allowing users to interact with their databases using natural language. 

**Key Distinction:** EzQL is **not** a Text-to-SQL converter for developers. It is a business intelligence tool for end-users. It must deliver answers, insights, and visualizations—never raw code.

---

## Philosophy & Core Principles

### 1. Total Code Abstraction
Users should never see SQL, Python, or any technical artifacts. The agent's output must always be human-readable business language. If a query fails, the system should attempt to self-correct (via LangGraph's agentic loops) or explain the issue in plain English without exposing database internals.

### 2. Implicit Statistical Intelligence
EzQL goes beyond simple data retrieval. It should proactively apply statistical methods when relevant. 
*   **Example:** If asked "How are sales doing?", the backend shouldn't just sum sales; it should consider trends, identify outliers, or perform a t-test if comparing periods, translating these results into "Sales have increased significantly (p < 0.05)" rather than "The sum is X".

### 3. Decoupled Architecture
The project strictly separates the **Brain** (Backend) from the **Face** (Frontend).
*   **Backend (FastAPI):** Owns all logic, database connections, AI orchestration, and statistical computations. It must return rich, structured JSON that includes text summaries, data tables, and chart specifications.
*   **Frontend (Streamlit MVP):** Acts as a thin client. It is responsible *only* for rendering the structured data received from the API. It should not contain business logic or direct database access.

---

## Tech Stack & Implementation Details

### Environment Management
*   **[uv](https://github.com/astral-sh/uv):** Used for all package management. Always use `uv sync` or `uv add` for dependencies.

### AI Orchestration
*   **LangGraph & LangChain:** The core engine (`backend/services/agent/`). We use stateful LangGraph workflows with a Hub-and-Spoke architecture centered around an `OrchestratorNode` and specialist sub-nodes (`SqlNode`, `StatisticsNode`, `VisualizationNode`).
*   **Agentic Loops:** Implementation relies on iterative refinement within LangGraph tool calls. If a generated SQL query is invalid, the agent catches the error and retries.

### API & Data Validation
*   **FastAPI:** High-performance asynchronous backend.
*   **Pydantic:** Strictly used for data validation and defining the contract between backend and frontend.

### Frontend
*   **Streamlit:** Used for the MVP. It should be used to render Markdown, DataFrames, metrics, and Plotly/Altair charts based on the backend's instructions.

---

## Backend Architecture Standards
The backend follows a strict separation of paradigms between the API layer, generic services, and the agent ecosystem.

### 1. API Layer (FastAPI Routers)
*   **Functional & Thin Controllers:** Routers (`backend/routers/`) must be purely functional. Do not instantiate classes globally or within the routes.
*   **Dependency Injection:** All services must be injected using FastAPI's `Depends()`. 
*   **Global Exception Handling:** Do not use `try...except` blocks in routes to handle domain errors (e.g., `RuntimeDatabaseError`). Let exceptions bubble up to be caught by global handlers in `main.py` (`@app.exception_handler`).

### 2. General Services Layer
*   **OOP without Interfaces:** Business logic (`backend/services/`) is encapsulated in standard Python classes (e.g., `UserDatabase`). Do not enforce redundant Abstract Base Classes or interfaces unless absolutely necessary.
*   **Naming Convention:** Do NOT append `_service` to class or file names (e.g., use `UserDatabase` in `user_database.py`, NOT `UserDatabaseService`).
*   **Service Registry:** Services are cached and managed using a Singleton `ServiceRegistry` in `backend/utils/dependencies.py`. Never attach services directly to `request.app.state`.

### 3. Agent Ecosystem (LangGraph - Hub-and-Spoke Architecture)
*   **Main Entry Service:** `AnalystAgent` (`backend/services/agent/agent.py`) orchestrates graph execution and handles initial state assembly.
*   **Hub-and-Spoke Topology:**
    *   **Orchestrator Node (`OrchestratorNode`):** The central hub and graph entry point (`START -> orchestrator`). It analyzes user intent and delegates to specialists via delegation tools (`delegate_to_sql`, `delegate_to_statistics`, `delegate_to_visualization`) returning `Command(goto=...)`.
    *   **Specialist Nodes (`SqlNode`, `StatisticsNode`, `VisualizationNode`):** Focused domain nodes equipped with dedicated toolkits. Once execution finishes, control automatically routes back to `OrchestratorNode`.
    *   **Zero Peer-to-Peer Coupling:** Specialist nodes MUST NOT know about each other or expose `transfer_to_*` tools to other specialists. All cross-domain orchestration passes through `OrchestratorNode`.
*   **Strict Contracts:** Nodes (`backend/services/agent/nodes/`) MUST inherit from `NodeBase`.
*   **Type Safety & Fail Fast:** Dependency injection for the graph must be done via `RunnableConfig` using strictly validated Pydantic models (e.g., `AgentConfiguration` in `state.py`). Validate critical requirements (like API keys or DB existence) *before* entering LLM loops.
*   **Decoupled Tools:** LangChain tools (`@tool`) must be fully decoupled from the Nodes. They belong in `backend/services/agent/tools/` and extract context from `RunnableConfig`.

---

## Rules for Adding New Specialist Nodes

To extend `AnalystAgent` with a new specialist capability (e.g., a Forecasting Node), follow this exact implementation protocol:

1. **System Prompt (`backend/prompts/<specialist>.py`):**
   * Create the prompt file defining the specialist's role, domain limits, and formatting rules.
   * Export the prompt in `backend/prompts/__init__.py`.

2. **Domain Tools (`backend/services/agent/tools/<specialist>.py`):**
   * Implement domain tools using the `@tool` decorator, retrieving `AgentConfiguration` via `RunnableConfig`.
   * Export the specialist tool list in `backend/services/agent/tools/__init__.py`.

3. **Orchestrator Delegation Tool (`backend/services/agent/tools/orchestrator.py`):**
   * Add a tool function `delegate_to_<specialist>()` returning `Command(goto="<specialist>")`.
   * Add it to `orchestrator_tools` in `backend/services/agent/tools/__init__.py`.

4. **Pydantic Data Blocks (if applicable) (`backend/models/blocks.py`):**
   * If the node outputs custom visual payloads to the frontend, define a new Pydantic block model (e.g., `ForecastBlock`).
   * Include the new block in the `DataBlock` discriminated union.

5. **Node Class (`backend/services/agent/nodes/<specialist>.py`):**
   * Implement `<Specialist>Node` inheriting from `NodeBase`.
   * Bind the specialist's tools to the LLM client and invoke with the specialist system prompt.
   * Export the node class in `backend/services/agent/nodes/__init__.py`.

6. **Graph Wiring (`backend/services/agent/graph.py`):**
   * Instantiate `ToolNode(<specialist>_tools)`.
   * Add node `<specialist>` and node `tools_<specialist>` to the `StateGraph`.
   * Add conditional edge routing `<specialist>` to `tools_<specialist>` if tool calls exist, or back to `"orchestrator"` on completion.
   * Add edge from `tools_<specialist>` back to `<specialist>`.

7. **Orchestrator Prompt Registration (`backend/prompts/orchestrator.py`):**
   * Update `ORCHESTRATOR_SYSTEM_PROMPT` to describe the new specialist's responsibilities so the Orchestrator knows when to delegate to it.

8. **AnalystAgent Integration (`backend/services/agent/agent.py`):**
   * Instantiate `self.<specialist>_node` inside `AnalystAgent.__init__` and pass it to `create_agent_graph()`.

---

## Project Structure

```text
ezql/
├── backend/                 # The Brain (FastAPI)
│   ├── main.py              # Entrypoint & Global Exception Handlers
│   ├── routers/             # Functional Thin Controllers
│   ├── models/              # Shared API schemas and SQL entities
│   │   └── blocks.py        # Typed DataBlock schemas for UI rendering
│   ├── prompts/             # System prompts for Orchestrator & Specialists
│   ├── utils/               # ServiceRegistry & DI Providers
│   └── services/            # Business Logic & OOP Service Objects
│       └── agent/           # LangGraph ecosystem
│           ├── agent.py     # AnalystAgent entrypoint service
│           ├── graph.py     # Hub-and-Spoke StateGraph compilation
│           ├── state.py     # AgentState & AgentConfiguration
│           ├── nodes/       # OrchestratorNode & Specialist Nodes
│           └── tools/       # Orchestrator & Specialist Toolkits
└── frontend/                # The UI Layer (Streamlit)
    ├── app.py               # Main interface
    └── components/          # Reusable UI elements
```

---

## Guidelines for Agents

1.  **Maintain Abstraction:** When writing code for the backend, ensure error messages sent to the frontend are user-friendly.
2.  **Statistically Driven:** When implementing data retrieval, look for opportunities to add "Invisible Analytics" (trend analysis, anomaly detection).
3.  **API-First & Functional:** Ensure new features are implemented in the service layer first, then exposed via a functional FastAPI endpoint relying on `Depends()`.
4.  **Type Safety & Fail Fast:** Use Pydantic models for all API exchanges and internal Graph configurations. Catch invalid states immediately rather than deep within execution loops.
5.  **Strict File Naming:** Never name files or classes with `_service` suffix in the `backend/services/` directory. Use absolute imports pointing to directories where possible.
6.  **Efficient Searching:** Always use `ripgrep` (e.g. via the agent `grep_search` tool) instead of conventional `grep` when searching for text across the project to improve performance.

---

## UI Rendering & Tool Contracts

The contract between the LangGraph backend and the Streamlit frontend is **strictly typed**. AI Agents must adhere to the following data exchange and rendering rules:

1. **Visual Formatting via Markdown:** Agents have full control over visual formatting in the text response. They must use Markdown (including Markdown tables, bold text, and lists) to structure their answers cleanly.
2. **Strict Pydantic Blocks:** Tools (`@tool`) must NEVER append raw dictionaries or generic lists to `query_data_ref`. They must instantiate and append formal Pydantic blocks from `backend/models/blocks.py` (e.g., `TableBlock`, `MetricBlock`, `TrendBlock`, `OutlierBlock`, `ChartBlock`) using `.model_dump()`.
3. **Frontend Rendering Logic:** The frontend (`frontend/components/ui.py`) renders the Markdown text generated by the agent. It also renders specific statistical data blocks (`TrendBlock`, `MetricBlock`, `OutlierBlock`, `ChartBlock`) using native Streamlit components (like `st.metric`). However, it intentionally ignores `TableBlock` and raw legacy tables to avoid visual duplication, as the agent is expected to render tabular data via Markdown.
4. **DataBlock Fallbacks:** To ensure backward compatibility, the `AgentReply` and `Content` models use `FlexibleDataBlock` (a discriminated union based on the `"type"` key). This enforces types for new messages while preventing `ValidationError` crashes on historical unstructured chats.
5. **Streamlit Component Widths:** Do NOT use the deprecated `use_container_width` parameter for Streamlit components. Instead, use the `width` parameter (e.g., `width="stretch"` instead of `use_container_width=True`, and `width="content"` instead of `use_container_width=False`).
