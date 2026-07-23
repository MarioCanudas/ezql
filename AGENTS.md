# AGENTS.md - Project Context for AI Assistants

This document provides essential context, philosophy, and technical guidelines for AI agents working on the EzQL project.

## Project Overview
**EzQL** is an autonomous data analyst interface. Its primary goal is to democratize data analytics by allowing users to interact with their databases using natural language. 

**Key Distinction:** EzQL is **not** a Text-to-SQL converter for developers. It is a business intelligence tool for end-users. It must deliver answers, insights, and visualizations—never raw code.

---

## Philosophy & Core Principles

### 1. Total Code Abstraction
Users should never see SQL, Python, or any technical artifacts. The agent's output must always be human-readable business language. If a query fails, the system should attempt to self-correct (via LangChain's agentic loops) or explain the issue in plain English without exposing database internals.

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
*   **LangChain:** The core engine. We use `SQLDatabaseToolkit` and autonomous agents.
*   **Agentic Loops:** Implementation should rely on iterative refinement. If a generated SQL query is invalid, the agent must catch the error and retry.

### API & Data Validation
*   **FastAPI:** High-performance asynchronous backend.
*   **Pydantic:** Strictly used for data validation and defining the contract between backend and frontend.

### Frontend
*   **Streamlit:** Used for the MVP. It should be used to render Markdown, DataFrames, and Plotly/Altair charts based on the backend's instructions.

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

### 3. Agent Ecosystem (LangGraph)
*   **Strict Contracts:** Due to the nature of LangGraph, nodes (`backend/services/agent/nodes/`) MUST inherit from `NodeBase`. 
*   **Type Safety & Fail Fast:** Dependency injection for the graph must be done via `RunnableConfig` using strictly validated Pydantic models (e.g., `AgentConfiguration` in `state.py`). Validate critical requirements (like API keys or DB existence) *before* entering LLM loops.
*   **Decoupled Tools:** LangChain tools (`@tool`) must be fully decoupled from the Nodes. They belong in `backend/services/agent/tools/` and should extract their context from `RunnableConfig`.

---

## Project Structure

```text
ezql/
├── backend/                 # The Brain (FastAPI)
│   ├── main.py              # Entrypoint & Global Exception Handlers
│   ├── routers/             # Functional Thin Controllers
│   ├── models/              # Shared API schemas and SQL entities
│   ├── utils/               # ServiceRegistry & DI Providers
│   └── services/            # Business Logic & OOP Service Objects
│       └── agent/           # LangGraph ecosystem (Nodes, Tools, State)
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
2. **Strict Pydantic Blocks:** Tools (`@tool`) must NEVER append raw dictionaries or generic lists to `query_data_ref`. They must instantiate and append formal Pydantic blocks from `backend/models/blocks.py` (e.g., `TableBlock`, `MetricBlock`, `TrendBlock`, `OutlierBlock`) using `.model_dump()`.
3. **Frontend Rendering Logic:** The frontend (`frontend/components/ui.py`) renders the Markdown text generated by the agent. It also renders specific statistical data blocks (`TrendBlock`, `MetricBlock`, `OutlierBlock`) using native Streamlit components (like `st.metric`). However, it intentionally ignores `TableBlock` and raw legacy tables to avoid visual duplication, as the agent is expected to render tabular data via Markdown.
4. **DataBlock Fallbacks:** To ensure backward compatibility, the `AgentReply` and `Content` models use `FlexibleDataBlock` (a discriminated union based on the `"type"` key). This enforces types for new messages while preventing `ValidationError` crashes on historical unstructured chats.
5. **Streamlit Component Widths:** Do NOT use the deprecated `use_container_width` parameter for Streamlit components. Instead, use the `width` parameter (e.g., `width="stretch"` instead of `use_container_width=True`, and `width="content"` instead of `use_container_width=False`).
