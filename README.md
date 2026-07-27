# EzQL 🚀
> **Talk to your data, get answers—not just code.**

EzQL is an intelligent, minimalist web application designed to democratize data analytics. Instead of forcing users to learn SQL or complex BI tools, EzQL lets anyone connect a database and ask questions in plain language.

Unlike traditional Text-to-SQL utilities that dump code for developers, **EzQL acts as an autonomous data analyst in a chat interface**. It aims to hide technical complexity and return business-friendly answers, summaries, and (eventually) visualizations.

---

## Architecture Philosophy

EzQL is built with a **decoupled architecture**, strictly separating the presentation layer from core business logic:

- **Backend (FastAPI):** The “brain”. Exposes a REST API, handles persistence, database/runtime handling, model orchestration, and returns structured JSON to the UI.
- **Frontend (Streamlit MVP):** A thin client that talks only to the FastAPI API. This keeps UI replaceable (React/Next/Vue later) without rewriting the backend.

---

## Core Features

- **Plug & play (SQLite-first):** Upload a SQLite database file and start chatting.
- **Total code abstraction:** End-users should not see SQL or Python.
- **Implicit statistical intelligence (roadmap):** The agent can apply statistical routines when relevant and translate results into plain language.
- **Context-aware reasoning:** Uses schema metadata to answer business questions without requiring strict column-name phrasing.

---

## 🛠️ Tech Stack

- **Environment & dependencies:** [uv](https://docs.astral.sh/uv/) (fast Python + dependency management via `pyproject.toml` + `uv.lock`).
- **Backend:** [FastAPI](https://fastapi.tiangolo.com/) + Pydantic/SQLModel.
- **LLM orchestration:** LangChain (`langchain-openai`).
- **Frontend:** [Streamlit](https://streamlit.io/) (MVP).

---

## 📂 Project Structure

```text
ezql/
├── README.md
├── pyproject.toml
├── uv.lock
│
├── backend/                 # FastAPI application
│   ├── main.py              # FastAPI entrypoint
│   ├── routers/             # API routes
│   └── services/            # Service layer
│
└── frontend/                # Streamlit application
    ├── app.py
    ├── components/
    └── pages/
```

---

## Local Development (setup & run)

> Run all commands from the repo root (where `pyproject.toml` and `uv.lock` live).

### Prerequisites

- [uv](https://docs.astral.sh/uv/) installed
- (Optional) `sqlite3` CLI, if you want to build the bundled sample database locally

> The project requires Python `>=3.13` (uv will manage this automatically).

### 1) Install dependencies

```bash
uv sync
```

### 2) Configure the frontend → backend URL (Streamlit Secrets)

The frontend reads the backend base URL from **Streamlit Secrets** (`st.secrets["API_BASE_URL"]`).

To configure it locally:

1. Ensure the folder exists: `frontend/.streamlit/`
2. Create/edit `frontend/.streamlit/secrets.toml`:

```toml
# frontend/.streamlit/secrets.toml
API_BASE_URL = "http://localhost:8000/api/v1"
```

Notes:

- If you don’t set anything, the default is `http://localhost:8000/api/v1`.
- `frontend/.streamlit/` is ignored by git, so this file won’t be committed.

### 3) Configure model API keys (inside the app)

API keys (OpenAI / DeepSeek) are configured **inside the web UI** on the Settings/Profile screen.

- You do **not** need environment variables for API keys.
- Keys are stored locally in EzQL’s internal SQLite database (`backend/ezql.db`).
- If you delete `backend/ezql.db`, you’ll need to set the keys again.

### 4) Databases (important)

EzQL uses **two different kinds of databases** when running locally:

#### A) EzQL internal app database (persistence)

- File: `backend/ezql.db` (SQLite)
- Stores: users, chats, messages, and **per-user model API keys**
- Created/migrated automatically when the backend starts
- Not versioned (SQLite files are ignored via `.gitignore`)

Quick reset (wipes local users/chats/keys):

```bash
rm -f backend/ezql.db
```

> Optional: you can also initialize it manually:
>
> ```bash
> uv run python backend/init_db.py
> ```

#### B) The database you want to analyze (your data)

In the current MVP, EzQL analyzes **SQLite** files (`.db`, `.sqlite`, `.sqlite3`).

You can:

- **Upload a SQLite file** when creating a new chat.
- Use a **bundled sample dataset** (Netflix or Uber Ride Analytics).

Important runtime behavior:

- Uploaded SQLite files are treated as **temporary runtime databases**.
- If the backend process restarts, you must upload the SQLite file again (and typically recreate the chat).

#### Bundled sample databases (not committed)

For safety, the SQLite files in `frontend/test_data/` are **not committed** to the repo (all `*.db` files are ignored). The repo includes the CSV datasets `netflix_titles.csv` and `ncr_ride_bookings.csv`.

The application offers both samples in **Nuevo chat**. The Uber sample is exposed as the `uber_ride_bookings` table and is ready for questions about booking status, vehicle type, revenue, cancellations, distance, and ratings.

To build the sample database locally:

```bash
cd frontend/test_data
sqlite3 netflix.db
```

Then inside the `sqlite3` prompt:

```sql
CREATE TABLE netflix_titles (
    show_id TEXT PRIMARY KEY,
    type TEXT,
    title TEXT,
    director TEXT,
    "cast" TEXT,
    country TEXT,
    date_added TEXT,
    release_year INTEGER,
    rating TEXT,
    duration TEXT,
    listed_in TEXT,
    description TEXT
);
.mode csv
.import netflix_titles.csv netflix_titles
```

### 5) Start the app

#### Option A — Two terminals (recommended, cross-platform)

Terminal 1 (backend):

```bash
uv run fastapi dev backend/main.py --host 127.0.0.1 --port 8000
```

Terminal 2 (frontend):

```bash
uv run streamlit run frontend/app.py
```

Useful URLs:

- Frontend (Streamlit): `http://localhost:8501`
- API docs (FastAPI): `http://localhost:8000/docs`

#### Option B — One command (macOS/Linux)

```bash
uv run poe run-app
```

> This task uses `lsof`/`kill` to free port 8000. On Windows, use the two-terminal option.

### 6) First run checklist

1. Open the frontend at `http://localhost:8501`.
2. Create your first local user and log in.
3. Go to Settings/Profile and add your OpenAI or DeepSeek API key.
4. Create a new chat and choose either:
   - the Netflix sample database (if you built `frontend/test_data/netflix.db`), or
   - upload your own SQLite file.

### 7) Stop the app

- If running in two terminals: press `Ctrl + C` in each terminal.
- If running via `uv run poe run-app`: press `Ctrl + C` once (the task stops Streamlit and terminates the backend).

If a port is stuck (macOS/Linux):

```bash
lsof -ti tcp:8000 | xargs kill
lsof -ti tcp:8501 | xargs kill
```
