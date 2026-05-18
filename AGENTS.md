# AGENTS.md - Project Context for AI Assistants

This document provides essential context, philosophy, and technical guidelines for AI agents working on the EzQL project.

## 🎯 Project Overview
**EzQL** is an autonomous data analyst interface. Its primary goal is to democratize data analytics by allowing users to interact with their databases using natural language. 

**Key Distinction:** EzQL is **not** a Text-to-SQL converter for developers. It is a business intelligence tool for end-users. It must deliver answers, insights, and visualizations—never raw code.

---

## 🧘 Philosophy & Core Principles

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

## 🛠️ Tech Stack & Implementation Details

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

## 📂 Project Structure

```text
ezql/
├── backend/                 # The Brain (FastAPI)
│   ├── main.py              # Entrypoint & Routing
│   └── services/            # AI & Stats logic
└── frontend/                # The UI Layer (Streamlit)
    ├── app.py               # Main interface
    └── components/          # Reusable UI elements
```

---

## 📝 Guidelines for Agents

1.  **Maintain Abstraction:** When writing code for the backend, ensure error messages sent to the frontend are user-friendly.
2.  **Statistically Driven:** When implementing data retrieval, look for opportunities to add "Invisible Analytics" (trend analysis, anomaly detection).
3.  **API-First:** Ensure that any new feature is implemented in the backend service layer first, then exposed via a FastAPI endpoint, and finally consumed by the Streamlit frontend.
4.  **Type Safety:** Use Pydantic models for all API exchanges to ensure the frontend can reliably render the backend's complex outputs.
