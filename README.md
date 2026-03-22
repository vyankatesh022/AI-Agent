# AI Agent API Backend

A production-ready AI Agent backend built with FastAPI, LangGraph, Google Gemini, and PostgreSQL, developed systematically across 7 dedicated sessions.

> **Infrastructure Notice**: This project runs directly on native Python with Uvicorn. **Docker is explicitly NOT used** in this project (no Dockerfile, docker-compose, or container runtimes).

---

## Current Technology Stack (Session 1)

- **Language**: Python 3.10+ (tested on Python 3.13)
- **Web Framework**: FastAPI (Async ASGI)
- **ASGI Server**: Uvicorn
- **Configuration & Validation**: Pydantic v2 & Pydantic Settings
- **Testing**: Pytest & HTTPX (FastAPI TestClient)
- **Linter & Formatter**: Ruff

---

## 7-Session Development Roadmap

1. **Session 1 (Current)**: Foundation + FastAPI (`/health`, logging, pydantic settings, tests)
2. **Session 2**: PostgreSQL + Authentication (Users, JWT, Password Hashing)
3. **Session 3**: LangGraph + LLM + Tool Calling (Gemini/OpenAI, StateGraph, tools)
4. **Session 4**: RAG + PDF Documents + FAISS (Chunking, vector embeddings, indexing)
5. **Session 5**: Hybrid Retrieval + Citations + Conversation Memory + RAG Evaluation
6. **Session 6**: Security + User Isolation + Prompt Injection Defense + Observability
7. **Session 7**: Production Hardening + Testing + GitHub Actions + Documentation

---

## Local Setup

### 1. Create and Activate Virtual Environment

Create a dedicated virtual environment using Python 3:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

*(On Windows PowerShell: `.\.venv\Scripts\Activate.ps1`)*

### 2. Install Dependencies

Install the project in editable mode including development tools:

```bash
pip install -e ".[dev]"
```

### 3. Configure Environment Variables

Copy the example environment configuration:

```bash
cp .env.example .env
```

Ensure `SECRET_KEY` in `.env` is set to a secure, random string of at least 32 characters.

> **Security Note**: Never commit your `.env` file to version control. It is ignored by `.gitignore`.

---

## Running the Application

Start the local development server with auto-reload:

```bash
uvicorn app.main:app --reload
```

The application will start on `http://127.0.0.1:8000`.

### Health Check Endpoint

Verify the server is running:

```bash
curl http://127.0.0.1:8000/health
```

Expected Response (`200 OK`):

```json
{
  "status": "ok",
  "service": "AI Agent API",
  "version": "0.1.0"
}
```

Interactive API documentation (Swagger UI) is available at:
- `http://127.0.0.1:8000/docs`

---

## Running Automated Tests

Run the test suite with pytest:

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
│   ├── logging_config.py     # Context-aware stdout logging setup
│   └── main.py               # FastAPI factory, lifespan, and /health route
├── docs/
│   └── architecture.md       # Current and target architecture & security rules
├── tests/
│   └── test_api.py           # Automated tests for health endpoint and config
├── .github/
│   └── workflows/            # GitHub Actions CI workflow (Session 7)
├── .env.example              # Template for environment configuration
├── .gitignore                # Git exclusions (protects secrets, venv, caches)
├── pyproject.toml            # Project metadata, dependencies, and tool settings
└── README.md                 # Project documentation and setup guide
```
