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
Verified presentation blocks are produced by tools and selected by the orchestrator. Specialist LLMs may provide narrative, but must not invent rows, series, KPIs or chart data.

### 3. Decoupled Architecture
The project strictly separates the **Brain** (Backend) from the **Face** (Frontend).
*   **Backend (FastAPI):** Owns logic, database connections, AI orchestration, and statistical computations. It returns a structured `AgentResponse` containing a summary, ordered `UIBlock` items, and metadata for verified facts.
*   **Frontend (Streamlit MVP):** Thin client responsible *only* for rendering the structured `AgentResponse` using `render_agent_response` in `frontend/components/ui.py`.

### 4. Use-Case-Driven Testing
Every new feature, behavior, or procedural change MUST include tests that represent
the real way the backend and its users exercise that behavior. Isolated unit tests
are useful but insufficient when the change crosses the agent, tools, persistence,
API, or frontend boundaries. Tests should validate the complete contract and the
important failure modes of the use case, including realistic provider responses,
fallbacks, retries, validation, and persisted output where applicable. The number
of tests is not constrained: add as many as necessary to give meaningful coverage;
passing a large number of narrow tests does not compensate for missing end-to-end
or integration coverage.

---

## Tech Stack & Implementation Details

### Environment Management
*   **[uv](https://github.com/astral-sh/uv):** Used for all package management. Always use `uv sync` or `uv add` for dependencies.
*   Statistical foundations use Pandas/NumPy. `scipy` and `scikit-learn` are installed for the next inference/regression iteration but are not enabled by the current statistical tools.

### AI Orchestration
*   **LangGraph & LangChain:** The core engine (`backend/services/agent/`). Stateful LangGraph workflow with a Hub-and-Spoke architecture centered around `OrchestratorNode` and specialist sub-nodes (`SqlNode`, `StatisticsNode`, `VisualizationNode`).
*   **Agentic Loops & Self-Correction:** Iterative refinement within LangGraph tool calls. SQL errors are caught and retried automatically.
*   **Evidence-first finalization:** After tool execution, the orchestrator receives semantic facts and presentation candidates. A structured selection step chooses candidate IDs and writes the summary/narrative. Invalid selections fall back to verified candidates.

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
    2. **Specialist Execution:** Specialists run their tool calls independently, store typed artifacts, and provide narrative plus tool-proposed presentation candidates. They always return control to the Orchestrator.
    3. **Statistics authorization:** Before a statistics step, the graph may create a short-lived, bounded `DatasetGrantDescriptor`. The actual rows remain in an in-memory grant store and are never placed in graph state.
    4. **Evidence Review:** When a round completes, the Orchestrator may finalize or add a bounded complementary plan using accumulated artifacts and contributions.
    5. **Candidate Selection:** The Orchestrator validates selected candidate IDs and fact references, preserves their order, and falls back to available verified candidates when the model response is invalid.
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
9. **Evidence contract:** Presentable tool results should declare validated `suggested_blocks`. Semantic metric facts are cataloged with a stable key, display value, tool-call provenance and evidence path. Do not flatten every scalar into response metadata.

---

## Project Structure

```text
ezql/
├── backend/                 # The Brain (FastAPI)
│   ├── main.py              # Entrypoint & Global Exception Handlers
│   ├── routers/             # Functional Thin Controllers
│   ├── models/              # Shared API schemas and SQL entities
│   │   ├── blocks.py        # Typed UIBlock & AgentResponse schemas
│   │   ├── metadata.py      # Verified fact metadata contracts
│   │   └── statistics.py    # Analysis scopes, filters and grants
│   ├── prompts/             # System prompts for Orchestrator & Specialists
│   ├── utils/               # ServiceRegistry & DI Providers
│   └── services/            # Business Logic & OOP Service Objects
│       └── agent/           # LangGraph ecosystem
│           ├── agent.py     # AnalystAgent entrypoint service
│           ├── agent_chat.py# ChatOpenAI wrapper & provider resolver
│           ├── graph.py     # Hub-and-Spoke StateGraph compilation
│           ├── state.py     # AgentState, artifacts and candidates
│           ├── metadata.py  # Fact catalog and safe template resolver
│           ├── statistics_grants.py # Short-lived authorized snapshots
│           ├── statistics_sandbox.py # Docker sandbox executor
│           ├── sandbox/      # Pinned sandbox image and runner
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
7.  **Metadata as evidence:** `AgentResponse.metadata` contains only selected, presentable facts. Each fact has its original value, safe display string, tool-call ID and evidence path. Internal debug flattening must not be exposed to prompts or persisted response payloads.
8.  **Safe references:** `{{meta.clave}}` references resolve in the frontend without mutating stored messages. Invalid references become `Dato no disponible` individually; free narrative, including literal numbers, must not trigger a global fallback.
9.  **Verified candidates:** Metrics, tables and charts in a candidate-aware response must come from validated tool candidates. The orchestrator selects candidate IDs; it does not accept arbitrary numeric data from the formatter.
10. **Use-case tests are mandatory:** Whenever implementing a new capability or changing an existing procedure, add tests at the highest relevant boundary, preferably exercising the real service/graph/tools and API flow with realistic inputs and provider outputs. Do not rely only on isolated mocks or happy-path unit tests. Include the necessary error, fallback, retry, persistence, and rendering scenarios, regardless of how many tests that requires.

---

## UI Rendering & Tool Contracts

The backend-frontend contract uses structured `AgentResponse` objects:

1. **`AgentResponse` Schema:** Contains `summary: str`, `blocks: list[UIBlock]`, and `metadata: MessageMetadata`. Metadata is persisted through `AgentReply`, `Content` and chat history for traceability.
2. **`UIBlock` Types:**
   * **`MarkdownBlock` (`type: "markdown"`):** Text explanation, narrative, and embedded Markdown tables.
   * **`MetricBlock` (`type: "metric"`):** KPI metric card with `label`, `value` (string), and optional `delta`.
   * **`ChartBlock` (`type: "chart"`):** Native chart with `chart_type` (`bar`, `line`, `area`, `scatter`), `x_axis`, `y_axis`, and `data` (list of dicts).
   * **`TableBlock` (`type: "table"`):** Explicit user-requested data table with `columns` and `data`.
3. **Frontend Block Renderer (`frontend/components/ui.py`):** `render_agent_response` iterates through `blocks` and renders native Streamlit components (`st.markdown`, `st.columns` + `st.metric`, `st.bar_chart`, `st.line_chart`, `st.scatter_chart`, `st.info`).
4. **Streamlit Component Parameters:** Use `width="stretch"` for dataframes (do NOT use deprecated `use_container_width`).

### Statistics specialist

`StatisticsNode` handles descriptive business analysis, not inference. Its
current tools are `profile_data`, `describe_metric`, `compare_segments`,
`analyze_trend`, `detect_outliers` (IQR), and `run_statistics_python` for
optional descriptive analysis over an authorized snapshot. Regular tools use
the SQL-free `AnalysisScope` and typed `AnalysisFilter` contracts; supported
aggregations are `count`, `sum`, `mean`, `min` and `max`.

Results should report population, valid/discarded rows, truncation, method and
warnings. Trends are aggregated time series with period changes and moving
average; they are not predictions or regressions. Statistical tools must not
claim causality, significance or forecast results.

### Isolated statistics sandbox

`StatisticsGrantNode` creates a bounded `DatasetGrantDescriptor` before an
advanced statistics step. `StatisticsGrantStore` keeps the actual records
in-memory with user/database/step binding and a short TTL. The Docker executor
uses no network, host mounts, privileges or database access, has resource and
output limits, and returns only validated findings, metrics, tables and
warnings. Build the pinned image from `backend/services/agent/sandbox` before
deploying the sandbox capability.

### Bundled sample databases

The New Chat flow supports the bundled `netflix` and `uber` samples. Runtime
registration accepts `sample_name`; the Uber sample is exposed as
`uber_ride_bookings` and is generated from
`frontend/test_data/ncr_ride_bookings.csv` using the accompanying SQLite build
script. Sample SQLite files remain local and are not committed. Frontend chat
reactivation must treat both sample runtime IDs as recoverable bundled samples.

### Verified metadata and presentation candidates

Tool artifacts internally carry semantic `metadata`, validated
`presentation_candidates`, and optional `debug_metadata`. A candidate contains
an ID, validated UI block, tool-call ID and supporting fact keys. The
orchestrator selects candidates and preserves their order; invalid selections
fall back to available verified candidates. The flattened debug metadata is
excluded from evidence and persisted user messages.

The frontend resolves `{{meta.clave}}` only at render time. A missing reference
is replaced individually with `Dato no disponible`; narrative text without
references remains valid. Historical messages without metadata continue to
render normally.

### Testing expectations

Tests are part of the implementation, not a final checklist. A change is incomplete
until its real use cases are represented in the test suite. Prefer integration and
contract tests that cross the changed boundaries (for example, provider response →
LangGraph → database tool → `AgentResponse` → API persistence) while retaining unit
tests for deterministic edge cases. Mocks must preserve realistic response shapes
and failure behavior; they must not hide validation errors, unsupported provider
features, swallowed exceptions, or incorrect persistence. Add as many tests as the
behavior requires, with no arbitrary test-count limit.

Run `uv run pytest` after agent, metadata, statistics, sandbox or renderer
changes. Cover exact descriptive metrics, typed filters, missing periods and
zero values, segment ranking, IQR edge cases, candidate ordering and fallback,
invalid references, frontend rendering without payload mutation, and historical
messages without metadata. Use `uv run ruff check` for linting.
