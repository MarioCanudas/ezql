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

## Desarrollo local (configuración y ejecución)

> Ejecuta todos los comandos desde la raíz del repo (donde están `pyproject.toml` y `uv.lock`).

### Requisitos

- [uv](https://docs.astral.sh/uv/) (gestiona Python + dependencias)
- (Opcional) `sqlite3` CLI si quieres generar la base de prueba (`frontend/test_data/netflix.db`).

> Python requerido por el proyecto: `>=3.13` (uv lo gestiona automáticamente).

### 1) Instalar dependencias

```bash
uv sync
```

### 2) Configuración (URLs y proveedores de modelos)

#### Frontend → Backend (API base URL)

Por defecto el frontend llama a `http://localhost:8000/api/v1`.

Si tu backend corre en otra URL/puerto, puedes configurarlo de dos formas:

1) **Streamlit secrets (recomendado):** crea/edita `frontend/.streamlit/secrets.toml` (no se sube al repo):

```toml
API_BASE_URL = "http://localhost:8000/api/v1"
```

2) **Variable de entorno al ejecutar Streamlit:**

```bash
export EZQL_API_BASE_URL="http://localhost:8000/api/v1"
```

#### Backend → Proveedor LLM (base URLs)

Las **API keys** (OpenAI / DeepSeek) se configuran **por usuario dentro de la UI** (pantalla **Configuración → Perfil**) y se guardan localmente en la base interna de EzQL.

Si necesitas apuntar a un endpoint OpenAI-compatible o cambiar el base URL de DeepSeek, usa variables de entorno (el backend también intenta cargar `frontend/.env` si existe):

```bash
export OPENAI_BASE_URL="https://your-openai-compatible-endpoint/v1"
export DEEPSEEK_BASE_URL="https://api.deepseek.com"
```

Opcionalmente puedes crear `frontend/.env` (no se sube al repo) con esas variables:

```bash
# frontend/.env
OPENAI_BASE_URL=https://your-openai-compatible-endpoint/v1
DEEPSEEK_BASE_URL=https://api.deepseek.com
```

### 3) Bases de datos (muy importante)

EzQL usa **dos tipos** de base de datos cuando lo corres en local:

#### A) Base interna de EzQL (persistencia de la app)

- Archivo: `backend/ezql.db` (SQLite)
- Contiene: usuarios, chats, mensajes, modelos/engines disponibles, etc.
- Se crea/migra automáticamente al arrancar el backend.
- Por seguridad **no se versiona** (`*.db` está en `.gitignore`).
- Reset rápido: borra `backend/ezql.db` y vuelve a arrancar (perderás usuarios/chats locales).

> (Opcional) También puedes inicializarla manualmente:
>
> ```bash
> uv run python backend/init_db.py
> ```

#### B) Base de datos que vas a analizar (tus datos)

En el MVP, EzQL analiza bases **SQLite** (`.db`, `.sqlite`, `.sqlite3`).

- En **Chats → Nuevo chat** puedes:
  - **Subir un archivo SQLite** (se guarda como base **temporal**, solo vive durante el runtime actual del backend).
  - Usar la **base de prueba Netflix**.
- Si reinicias el backend, tendrás que volver a cargar el archivo y recrear el chat (esto es intencional).

##### Base de prueba “Netflix” (no se sube al repo)

Por seguridad, el archivo `frontend/test_data/netflix.db` **no se versiona**. El repo incluye el dataset `frontend/test_data/netflix_titles.csv`.

Para generar la base de prueba:

```bash
cd frontend/test_data
sqlite3 netflix.db
```

Luego, dentro del prompt de `sqlite3`, ejecuta:

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

(Referencia completa: `frontend/test_data/README.md`.)

### 4) Arrancar la app

#### Opción A — Dos terminales (recomendado, cross-platform)

Terminal 1 (backend):

```bash
uv run fastapi dev backend/main.py --host 127.0.0.1 --port 8000
```

Terminal 2 (frontend):

```bash
uv run streamlit run frontend/app.py
```

URLs útiles:

- Frontend (Streamlit): `http://localhost:8501`
- API docs (FastAPI): `http://localhost:8000/docs`

#### Opción B — Un solo comando (macOS/Linux)

```bash
uv run poe run-app
```

> Nota: esta tarea usa `lsof`/`kill` para liberar el puerto 8000. En Windows es mejor usar la opción de dos terminales.

### 5) Primer uso (paso a paso)

1. Abre el frontend en `http://localhost:8501`.
2. Crea el primer usuario (botón **Crear usuario**) e inicia sesión.
3. Ve a **Configuración → Perfil** y configura tu API key (OpenAI o DeepSeek).
4. Ve a **Chats → Nuevo chat** y elige:
   - **Usar base de prueba Netflix** (requiere `frontend/test_data/netflix.db`), o
   - **Subir archivo SQLite .db** (tu propia base).

### 6) Apagar la app

- Si la ejecutas en dos terminales: `Ctrl + C` en cada una.
- Si usas `poe run-app`: `Ctrl + C` una vez (Streamlit se detiene y el script mata el backend).

Si algún puerto queda ocupado (macOS/Linux):

```bash
lsof -ti tcp:8000 | xargs kill
lsof -ti tcp:8501 | xargs kill
```
