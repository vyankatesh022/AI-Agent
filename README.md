# AI Agent API Backend

A production-ready AI Agent backend built with FastAPI, PostgreSQL, LangGraph, and Google Gemini, developed systematically across 7 dedicated sessions.

> **Infrastructure Notice**: This project runs directly on native Python with Uvicorn and local/remote PostgreSQL. **Docker is explicitly NOT used** in this project (no Dockerfile, docker-compose, or container runtimes).

---

## Current Technology Stack (Session 2)

- **Language**: Python 3.10+ (tested on Python 3.13)
- **Web Framework**: FastAPI (Async ASGI)
- **ASGI Server**: Uvicorn
- **Database & ORM**: PostgreSQL with SQLAlchemy 2.0 (UUID keys, relationships, cascade deletes)
- **Database Driver**: `psycopg` (v3 binary)
- **Password Hashing**: Argon2id via `argon2-cffi`
- **Token Authentication**: Signed JWTs via `PyJWT`
- **Configuration & Validation**: Pydantic v2 & Pydantic Settings
- **Testing**: Pytest & Starlette/HTTPX TestClient
- **Linter & Formatter**: Ruff

---

## 7-Session Development Roadmap

1. **Session 1**: Foundation + FastAPI (`/health`, logging, pydantic settings, tests) *(Completed)*
2. **Session 2 (Current)**: PostgreSQL + Authentication (Users, JWT, Argon2, Conversations, User Isolation) *(Completed)*
3. **Session 3**: LangGraph + LLM + Tool Calling (Gemini/OpenAI, StateGraph, tools)
4. **Session 4**: RAG + PDF Documents + FAISS (Chunking, vector embeddings, indexing)
5. **Session 5**: Hybrid Retrieval + Citations + Conversation Memory + RAG Evaluation
6. **Session 6**: Security + User Isolation + Prompt Injection Defense + Observability
7. **Session 7**: Production Hardening + Testing + GitHub Actions + Documentation

---

## Local Setup

### 1. Create and Activate Virtual Environment

```bash
python3 -m venv .venv
source .venv/bin/activate
```

*(On Windows PowerShell: `.\.venv\Scripts\Activate.ps1`)*

### 2. Install Dependencies

```bash
pip install -e ".[dev]"
```

### 3. Configure Environment Variables

Copy the example configuration:

```bash
cp .env.example .env
```

Configure `.env`:
```dotenv
APP_NAME=AI Agent API
APP_VERSION=0.1.0
ENVIRONMENT=development
SECRET_KEY=replace-with-a-random-secret-at-least-32-characters
DATABASE_URL=postgresql+psycopg://username:password@localhost:5432/ai_agent
LOG_LEVEL=INFO
```

> **Security Note**: Never commit your `.env` file to version control. It is ignored by `.gitignore`.

### 4. PostgreSQL Setup

Ensure PostgreSQL is installed and running locally:

```bash
createdb ai_agent
createdb ai_agent_test
```

Tables (`users`, `conversations`, `messages`) are automatically created on startup by the application lifespan manager via SQLAlchemy ORM.

---

## Running the Application

Start the local development server:

```bash
uvicorn app.main:app --reload
```

The application runs on `http://127.0.0.1:8000`.

Interactive Swagger UI documentation is available at `http://127.0.0.1:8000/docs`.

---

## API Endpoints

### System
- `GET /health` — Service health check.

### Authentication (`/auth`)
- `POST /auth/register` — Register a new account (`email`, `password` >= 8 chars).
- `POST /auth/login` — Authenticate and receive a Bearer JWT token.
- `GET /auth/me` — Retrieve authenticated user profile (`Authorization: Bearer <token>`).

### Conversations (`/conversations`)
- `POST /conversations` — Create a new conversation owned by the caller.
- `GET /conversations` — List conversations owned exclusively by the caller.
- `GET /conversations/{id}` — Retrieve conversation details (enforces user isolation).
- `GET /conversations/{id}/messages` — List messages in an owned conversation.

---

## Running Automated Tests

Run the complete test suite:

```bash
pytest
```

Run code style and lint checks with Ruff:

```bash
ruff check .
```

---

## Project Structure

```text
.
├── app/
│   ├── __init__.py           # Application package marker
│   ├── config.py             # Pydantic Settings configuration loader
│   ├── database.py           # SQLAlchemy engine, sessionmaker, init_db, get_db
│   ├── dependencies.py       # Authentication & security dependencies (get_current_user)
│   ├── logging_config.py     # Context-aware stdout logging setup
│   ├── main.py               # FastAPI factory, lifespan, and router mounting
│   ├── models.py             # SQLAlchemy models (User, Conversation, Message)
│   ├── schemas.py            # Pydantic request/response validation schemas
│   ├── security.py           # Argon2id password hashing and JWT token handlers
│   └── routers/
│       ├── __init__.py       # Routers package marker
│       ├── auth.py           # Registration, login, and user profile endpoints
│       └── conversations.py  # User-isolated conversation and message endpoints
├── docs/
│   └── architecture.md       # Architecture specification and security design
├── tests/
│   ├── conftest.py           # Isolated test database session fixtures
│   ├── test_api.py           # Health endpoint and settings verification
│   ├── test_auth.py          # User registration, login, and JWT tests
│   ├── test_database.py      # ORM relationships, constraints, and cascade tests
│   └── test_security.py      # Cross-user isolation and SQLi defense tests
├── .github/
│   └── workflows/            # GitHub Actions CI workflow (Session 7)
├── .env.example              # Template for environment configuration
├── .gitignore                # Git exclusions (protects secrets, venv, caches)
├── pyproject.toml            # Project metadata, dependencies, and tool settings
└── README.md                 # Project documentation and setup guide
```
