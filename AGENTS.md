# AGENTS.md - Project Context for AI Assistants

This document provides essential context, philosophy, and technical guidelines for AI agents working on the EzQL project.

## Project Overview
**EzQL** is an autonomous data analyst interface. Its primary goal is to democratize data analytics by allowing users to interact with their databases using natural language. 

**Key Distinction:** EzQL is **not** a Text-to-SQL converter for developers. It is a business intelligence tool for end-users. It must deliver answers, insights, and visualizations—never raw code or raw SQL.

---

## Philosophy & Core Principles

### 1. Total Code Abstraction
Users should never see SQL, Python, or technical execution details. The system strictly excludes `SqlBlock` from user-facing responses. The agent's output must always be human-readable business language. If a query fails, the system self-corrects via LangGraph loops or explains the issue in plain English without exposing database internals.

### 2. Clean Business Intelligence Rendering
Internal database inspection tools (`preview_table`, `summarize_column`, `execute_advanced_sql`) execute purely in the background to inform the LLM's reasoning. They DO NOT pollute the user interface with raw preview tables. User-facing outputs use only composable Markdown, metric, table and chart blocks.

### 3. Decoupled Architecture
The project strictly separates the **Brain** (Backend) from the **Face** (Frontend).
*   **Backend (FastAPI):** Owns logic, database connections, AI orchestration, and statistical computations. It returns a structured `AgentResponse` containing a summary and an ordered array of `UIBlock` items (`MarkdownBlock`, `MetricBlock`, `TableBlock`, `ChartBlock`).
*   **Frontend (Streamlit MVP):** Thin client responsible *only* for rendering the structured `AgentResponse` using `render_agent_response` in `frontend/components/ui.py`.

---

## Tech Stack & Implementation Details

### Environment Management
*   **[uv](https://github.com/astral-sh/uv):** Used for all package management. Always use `uv sync` or `uv add` for dependencies.

### AI Orchestration
*   **LangGraph & LangChain:** The core engine (`backend/services/agent/`). Stateful LangGraph workflow with a Hub-and-Spoke architecture centered around `OrchestratorNode` and specialist sub-nodes (`SqlNode`, `StatisticsNode`, `VisualizationNode`).
*   **Agentic Loops & Self-Correction:** Iterative refinement within LangGraph tool calls. SQL errors are caught and retried automatically.

### API & Data Validation
*   **FastAPI & Pydantic v2:** High-performance asynchronous backend and strict data contracts defined in `backend/models/blocks.py`.

---

## Backend Architecture Standards

### 1. API Layer (FastAPI Routers)
*   **Functional Controllers:** Routers (`backend/routers/`) must be purely functional. Services are injected using `Depends()`.
*   **Global Exception Handling:** Do not use `try...except` in routes for domain errors (e.g., `RuntimeDatabaseError`). Let exceptions bubble to `@app.exception_handler` in `main.py`.

### 2. General Services Layer
*   **OOP Service Objects:** Business logic (`backend/services/`) is encapsulated in standard Python classes. Never append `_service` to file/class names.
*   **Service Registry:** Services are managed via a Singleton `ServiceRegistry` in `backend/utils/dependencies.py`.

### 3. Agent Ecosystem (LangGraph - Hub-and-Spoke Architecture)
*   **Main Entry Service:** `AnalystAgent` (`backend/services/agent/agent.py`) orchestrates execution and manages dependency context.
*   **Dependency Passing:** Dependency objects (`UserDatabase`, `AgentChat`) are passed as un-serialized references in `config["configurable"]` to preserve Python object pointers during graph execution.
*   **Hub-and-Spoke Topology & Planned Execution:**
    1. **Planning:** Entry point (`START -> orchestrator`). `OrchestratorNode` builds an ordered queue of `PlanStep` items using `sql`, `statistics`, and `visualization`.
    2. **Specialist Execution:** Specialists run their tool calls independently, store typed artifacts, and propose only base UI blocks. They always return control to the Orchestrator.
    3. **Evidence Review:** When a round completes, the Orchestrator may finalize or add a bounded complementary plan using accumulated artifacts and contributions.
    4. **Structured Formatting:** The Orchestrator deduplicates and orders the proposed base blocks into one validated `AgentResponse`.
*   **Zero Peer Coupling:** Specialist nodes MUST NOT route to each other. All routing flows through `OrchestratorNode`.

---

## Rules for Adding New Specialist Nodes

To extend `AnalystAgent` with a new specialist capability (e.g., a Forecasting Node):

1. **System Prompt (`backend/prompts/<specialist>.py`):** Define the specialist's role, limits, and formatting rules.
2. **Domain Tools (`backend/services/agent/tools/<specialist>.py`):** Implement tools with `@tool` and return structured results. Presentation tools include validated UI blocks; internal inspection tools must not create raw preview blocks.
3. **Orchestrator Planning:** Register the specialist in the planner prompt and `SpecialistName` state type.
4. **Pydantic Data Blocks (`backend/models/blocks.py`):** If adding a new visual payload, define a Pydantic model and register it in `UIBlock`.
5. **Node Class (`backend/services/agent/nodes/<specialist>.py`):** Inherit from `NodeBase`, bind specialist tools, and invoke LLM.
6. **Graph Wiring (`backend/services/agent/graph.py`):** Add node and tool node to `StateGraph`. Route `tools_<specialist>` back to `<specialist>`, and `<specialist>` completion back to `"orchestrator"`.
7. **Orchestrator Prompt (`backend/prompts/orchestrator.py`):** Register the new specialist in the planner, review and formatter prompts.
8. **AnalystAgent (`backend/services/agent/agent.py`):** Instantiate node in `AnalystAgent.__init__` and pass to `create_agent_graph()`.

---

## Project Structure

```text
ezql/
├── backend/                 # The Brain (FastAPI)
│   ├── main.py              # Entrypoint & Global Exception Handlers
│   ├── routers/             # Functional Thin Controllers
│   ├── models/              # Shared API schemas and SQL entities
│   │   └── blocks.py        # Typed UIBlock & AgentResponse schemas
│   ├── prompts/             # System prompts for Orchestrator & Specialists
│   ├── utils/               # ServiceRegistry & DI Providers
│   └── services/            # Business Logic & OOP Service Objects
│       └── agent/           # LangGraph ecosystem
│           ├── agent.py     # AnalystAgent entrypoint service
│           ├── agent_chat.py# ChatOpenAI wrapper & provider resolver
│           ├── graph.py     # Hub-and-Spoke StateGraph compilation
│           ├── state.py     # AgentState & AgentConfiguration
│           ├── nodes/       # OrchestratorNode & Specialist Nodes
│           └── tools/       # Orchestrator & Specialist Toolkits
└── frontend/                # The UI Layer (Streamlit)
    ├── app.py               # Main interface
    ├── pages/               # Streamlit multipage views
    └── components/          # Reusable UI elements (ui.py block renderer)
```

---

## Guidelines for Agents

1.  **Maintain Total Abstraction:** Never expose SQL, code, or technical traces to the user. `SqlBlock` is explicitly removed from response schemas.
2.  **Clean UI Output:** Internal database queries (`preview_table`, `execute_advanced_sql`) must never create raw `TableBlock`s. Only dedicated visualization/analytics tools should produce visual UI blocks.
3.  **API-First & Functional:** Implement features in the service layer first, exposed via thin FastAPI endpoints.
4.  **Type Safety & Fail Fast:** Validate dependencies with `AgentConfiguration` and Pydantic models.
5.  **Strict File Naming:** Never name files or classes with `_service` suffix in `backend/services/`.
6.  **Efficient Searching:** Always use `ripgrep` (`grep_search`) for codebase text searches.

---

## UI Rendering & Tool Contracts

The backend-frontend contract uses structured `AgentResponse` objects:

1. **`AgentResponse` Schema:** Contains `summary: str` (one-sentence executive summary) and `blocks: list[UIBlock]`.
2. **`UIBlock` Types:**
   * **`MarkdownBlock` (`type: "markdown"`):** Text explanation, narrative, and embedded Markdown tables.
   * **`MetricBlock` (`type: "metric"`):** KPI metric card with `label`, `value` (string), and optional `delta`.
   * **`ChartBlock` (`type: "chart"`):** Native chart with `chart_type` (`bar`, `line`, `area`, `scatter`), `x_axis`, `y_axis`, and `data` (list of dicts).
   * **`TableBlock` (`type: "table"`):** Explicit user-requested data table with `columns` and `data`.
3. **Frontend Block Renderer (`frontend/components/ui.py`):** `render_agent_response` iterates through `blocks` and renders native Streamlit components (`st.markdown`, `st.columns` + `st.metric`, `st.bar_chart`, `st.line_chart`, `st.scatter_chart`, `st.info`).
4. **Streamlit Component Parameters:** Use `width="stretch"` for dataframes (do NOT use deprecated `use_container_width`).
