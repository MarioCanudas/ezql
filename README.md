# EzQL 🚀
> **Talk to your data, get answers—not just code.**

EzQL is an intelligent, minimalist web application designed to democratize data analytics. Instead of forcing users to learn SQL or complex BI tools, EzQL allows anyone to connect a database and ask questions in plain, natural language. 

Unlike traditional Text-to-SQL utilities that just dump lines of code for the user to copy-paste, **EzQL acts as an autonomous data analyst built into a chat window.** It completely hides technical complexity, delivering beautifully formatted summaries, dynamic data visualizations, and implicit statistical analysis.

---

## Architecture Philosophy

EzQL is built with a **decoupled architecture**, strictly separating the presentation layer from the core business logic:

*   **Backend (FastAPI):** Acts as the centralized brain. It exposes a secure REST API that manages database connections, orchestrates the LangChain agentic workflows, executes implicit statistical routines, and returns structured JSON payloads (containing text, chart data structures, or tabular results).
*   **Frontend (Streamlit for MVP):** A lightweight client that talks exclusively to the FastAPI backend. By keeping this layer completely separate, the user interface can be seamlessly rewritten in other frameworks (like React, Next.js, or Vue) in the future without modifying a single line of the AI core.

---

## Core Features

*   **Plug & Play Connectivity:** A simple, secure interface to upload or link your database (starting with SQLite files for the MVP) and start chatting instantly.
*   **Total Code Abstraction:** End-users never see SQL queries or Python scripts. EzQL prioritizes human readability, clean typography, and elegant presentation.
*   **Implicit Statistical Intelligence:** Equipped with an "invisible" analytics engine. If a user asks, *"Is our revenue this month significantly different from last month?"*, the AI agent autonomously decides to run a hypothesis test (like a T-test) or regression model under the hood, translating complex mathematical rigor into plain business insights.
*   **Dynamic Visualizations:** EzQL doesn't just return tables. If the data benefits from visual impact, the backend delivers raw chart configurations that the frontend automatically renders as clean, interactive plots (line, bar, or scatter).
*   **Context-Aware Reasoning:** The agent analyzes table metadata to understand abstract business concepts (e.g., "churn risk," "peak demand," or "profit margins") without requiring strict column-name phrasing from the user.

---

## 🛠️ Tech Stack

EzQL leverages a modern, robust, and highly modular stack optimized for rapid AI deployment:

*   **Environment & Package Management:** [uv](https://github.com/astral-sh/uv) – An extremely fast Python package installer and resolver, managing dependencies via a centralized workspace and `pyproject.toml`.
*   **Backend API Engine:** [FastAPI](https://fastapi.tiangolo.com/) – For high-performance, asynchronous REST API routing and native Pydantic data validation.
*   **AI Orchestration & Agents:** [LangChain](https://www.langchain.com/) – The backbone of the application, utilizing autonomous SQL Agents (`SQLDatabaseToolkit`) that follow iterative refinement loops to self-correct queries.
*   **Frontend Client:** [Streamlit](https://streamlit.io/) – Serving as a reactive UI layer for the MVP, effortlessly rendering markdown, dataframes, and charts consumed from the API.

---

## 📂 Project Structure

This project uses a unified monorepo structure managed by `uv`, keeping backend and frontend code bases cleanly isolated.

```text
ezql/
├── README.md                # Project documentation
├── pyproject.toml           # Root workspace configuration and shared metadata
├── uv.lock                  # Universal lockfile generated automatically by uv
│
├── backend/                 # FastAPI Application (The Brain)
│   ├── main.py              # FastAPI entrypoint and API routing
│   ├── routers/             # API route definitions
│   └── services/            # Service layer for backend logic
│
└── frontend/                # Streamlit Application (The UI Layer)
    ├── app.py               # Main Streamlit web interface
    ├── components/          # Reusable Streamlit components
    └── pages/               # Streamlit page components
```

---

## Getting Started

### 1. Install dependencies

```bash
uv sync
```

### 2. Configure environment

Model API keys are configured per user in the Streamlit profile/settings screen. The backend no longer requires global OpenAI or DeepSeek API keys.

DeepSeek is used through LangChain's OpenAI-compatible chat client with the default base URL `https://api.deepseek.com`. Administrators can override provider base URLs when needed:

```bash
export OPENAI_BASE_URL="https://your-openai-compatible-endpoint/v1"
export DEEPSEEK_BASE_URL="https://api.deepseek.com"
```

Frontend (optional overrides):

```bash
export EZQL_API_BASE_URL="http://localhost:8000/api/v1"
```

You can also set a Streamlit secret:

```toml
# .streamlit/secrets.toml
API_BASE_URL = "http://localhost:8000/api/v1"
```

### 3. Initialize the database

```bash
uv run python backend/init_db.py
```

### 4. Run the backend

```bash
uv run fastapi dev backend/main.py
```

### 5. Run the frontend

```bash
uv run streamlit run frontend/app.py
```

### 6. Run both with poethepoet

```bash
uv run poe run-app
```
