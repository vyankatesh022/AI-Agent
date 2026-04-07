# AI Agent API (`ai-agent-api`)

[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115%2B-009688.svg)](https://fastapi.tiangolo.com/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-14%2B-336791.svg)](https://www.postgresql.org/)
[![LangGraph](https://img.shields.io/badge/LangGraph-0.2%2B-orange.svg)](https://github.com/langchain-ai/langgraph)
[![FAISS](https://img.shields.io/badge/FAISS-CPU_1.9%2B-0467DF.svg)](https://github.com/facebookresearch/faiss)
[![Tests](https://img.shields.io/badge/tests-129%20passed-brightgreen.svg)](tests/)
[![Code Style](https://img.shields.io/badge/code%20style-ruff-black.svg)](https://github.com/astral-sh/ruff)

A production-ready, multi-tenant AI Agent backend and web interface featuring hybrid RAG retrieval (dense FAISS + sparse PostgreSQL full-text search), bounded conversation memory, pluggable multi-model LLM execution (Google Gemini & OpenAI), and deterministic safety controls.

---

## Table of Contents

- [Overview](#overview)
- [Key Features](#key-features)
- [System Architecture](#system-architecture)
  - [API Gateway & Routing](#api-gateway--routing)
  - [LangGraph Agent Workflow](#langgraph-agent-workflow)
  - [Hybrid Retrieval & Citation Verification](#hybrid-retrieval--citation-verification)
  - [Document Ingestion Pipeline](#document-ingestion-pipeline)
- [Prerequisites](#prerequisites)
- [Installation & Setup](#installation--setup)
- [Configuration & Environment Variables](#configuration--environment-variables)
- [Running the Application](#running-the-application)
- [Web Interface (GUI)](#web-interface-gui)
- [API Reference](#api-reference)
  - [System Probes](#system-probes)
  - [Authentication (`/auth`)](#authentication-auth)
  - [Conversations (`/conversations`)](#conversations-conversations)
  - [AI Agent (`/agent`)](#ai-agent-agent)
  - [Documents & RAG (`/documents`)](#documents--rag-documents)
- [End-to-End Workflow Examples](#end-to-end-workflow-examples)
- [RAG Evaluation Suite](#rag-evaluation-suite)
- [Security Architecture & Defense in Depth](#security-architecture--defense-in-depth)
- [Testing & Quality Assurance](#testing--quality-assurance)
- [Troubleshooting](#troubleshooting)

---

## Overview

**ai-agent-api** is an enterprise-grade AI Agent backend built in Python and [FastAPI](https://fastapi.tiangolo.com/), designed without containerization abstractions (pure Python/Uvicorn runtime) for direct execution and transparent debugging.

The system follows a strict **Defense-in-Depth** security philosophy: authorization, tenant isolation, parameter sanitization, and rate limits are enforced exclusively in deterministic application code ([FastAPI](https://fastapi.tiangolo.com/) + [SQLAlchemy](https://www.sqlalchemy.org/) + [PostgreSQL](https://www.postgresql.org/)) and **never delegated to the Language Model**.

---

## Key Features

- **Multi-Model LLM Abstraction Layer**: Pluggable provider support for **Google Gemini** (`gemini-2.0-flash`, `gemini-1.5-flash`, `gemini-1.5-pro`) and **OpenAI** (`gpt-4o`, `gpt-4o-mini`, `gpt-3.5-turbo`) via `LLMFactory` (`app/llm/factory.py`), dynamically selectable per chat or RAG query with model allowlist validation.
- **LangGraph Agent Workflow**: Autonomous intent classification via `classify_intent_node` (`app/agent/nodes.py`) routing queries into `general_chat`, `database_query`, or `document_search`.
- **Hybrid RAG Retrieval Engine**: Fuses dense semantic vector search (FAISS `IndexFlatIP` with normalized cosine similarity via `UserFAISSIndex`) and sparse keyword search (PostgreSQL `tsvector` with `ts_rank_cd` via `KeywordRetriever`), applying min-max score normalization, linear weighted fusion (0.6 vector / 0.4 keyword default), and deduplication.
- **Authoritative Citation Verification**: Delimits retrieved context blocks as `[DOCUMENT SOURCE S1]`, prompts the model to cite facts with `[S1]`, and strips hallucinated source tags via `CitationValidator` (`app/rag/citations.py`).
- **Secure Document Processing & Storage**: Four-stage PDF validation (`DocumentValidator` in `app/documents/validator.py`) checking file size (\(\le 10\text{MB}\)), `.pdf` extension, MIME type (`application/pdf`), magic bytes (`%PDF-`), and structural page integrity via `pypdf`. Generates server UUID filenames with path traversal protection (`DocumentStorage` in `app/documents/storage.py`).
- **Bounded Conversation Memory**: Enforces SQL-level tenant isolation, recency message windows (`MAX_CONVERSATION_MESSAGES`), character/token budgets (`MAX_CONTEXT_TOKENS`), and prompt injection isolation (`ConversationMemoryService` in `app/memory/service.py`).
- **Deterministic Tool Sandboxing**: `SafeDatabaseTool` (`app/tools/safe_database.py`) exposes read-only profile and conversation inspection without raw SQL. Bounded by `ToolPolicyEnforcer` (`app/security/tool_policy.py`) with loop limits (`MAX_TOOL_CALLS_PER_REQUEST = 5`) and tenant parameter binding.
- **Multi-Tenant Physical & Logical Isolation**: Strict separation across the database (`WHERE user_id = :current_user_id`) and vector storage (`data/indexes/{user_id}/`).
- **Prompt Injection Defense**: `PromptGuard` (`app/security/prompt_guard.py`) intercepts jailbreaks, instruction overrides, and system prompt disclosure attempts, responding politely without leaking system state.
- **In-Memory Rate Limiting**: Memory-bounded sliding-window limiter (`SlidingWindowRateLimiter` in `app/security/rate_limit.py`) keyed by IP for auth endpoints and by user ID for agent/document endpoints, returning HTTP 429 with `Retry-After`.
- **Structured Observability & Secret Scrubbing**: `ObservabilityMiddleware` (`app/observability/middleware.py`) injects `X-Request-ID` and `X-Response-Time-MS`, while `SensitiveDataScrubber` (`app/observability/logging.py`) redacts API keys, Bearer tokens, passwords, and JWTs from logs.
- **Embedded Web GUI**: Dependency-free Vanilla HTML5, CSS3, and modern JavaScript (ES modules) client mounted at `/ui/` with responsive design, model picker, PDF document manager modal, and markdown chat rendering with citation popovers.
- **Automated RAG Evaluation Suite**: Zero-API-key deterministic benchmark runner (`app.rag.evaluation`) verifying Recall@K, Precision@K, Hit Rate@K, Citation Validity, and Grounding Coverage.

---

## System Architecture

### API Gateway & Routing

The [FastAPI](https://fastapi.tiangolo.com/) application gateway manages the request lifecycle, middleware pipeline, exception handling, and service routing:

```mermaid
flowchart TD
    Client["Client (Browser GUI / REST Client)"] --> Gateway["FastAPI Application Gateway"]
    
    subgraph Middlewares["Middleware Stack (Reverse Order)"]
        Gateway --> M1["RequestSizeLimitMiddleware (Max 15MB)"]
        M1 --> M2["SecurityHeadersMiddleware (CSP, HSTS, DENY)"]
        M2 --> M3["ObservabilityMiddleware (X-Request-ID, Monotonic Timing)"]
        M3 --> M4["CORSMiddleware (Allowlist)"]
    end

    subgraph Routers["API Routers"]
        M4 --> R1["/auth (Register, Login, Me)"]
        M4 --> R2["/conversations (CRUD, Message History)"]
        M4 --> R3["/agent (Chat, Model Introspection)"]
        M4 --> R4["/documents (Upload, List, Delete, Query)"]
        M4 --> R5["/ui (Static Web GUI Mount)"]
        M4 --> R6["/health & /ready (Liveness / Readiness)"]
    end
```

### LangGraph Agent Workflow

Queries submitted to `POST /agent/chat` are orchestrated through a compiled [LangGraph](https://github.com/langchain-ai/langgraph) `StateGraph` (`app/agent/graph.py`):

```mermaid
flowchart TD
    Start([START]) --> LoadContext["load_context<br/>(Load bounded history from PostgreSQL)"]
    LoadContext --> ClassifyIntent["classify_intent<br/>(Classify intent via LLM)"]
    
    ClassifyIntent -->|"intent == 'general_chat'"| NormalLLM["normal_llm<br/>(Generate answer with retry logic)"]
    ClassifyIntent -->|"intent == 'database_query'"| ExecuteTool["execute_tool<br/>(SafeDatabaseTool via ToolPolicyEnforcer)"]
    ClassifyIntent -->|"intent == 'document_search'"| RAGNode["rag_node<br/>(Execute Hybrid Retrieval & Citation Engine)"]
    
    ExecuteTool --> SynthesizeResp["synthesize_tool_response<br/>(Format tool output for user)"]
    
    NormalLLM --> Finish([END])
    SynthesizeResp --> Finish
    RAGNode --> Finish
```

### Hybrid Retrieval & Citation Verification

When RAG is invoked via `POST /documents/query` or through the agent's `document_search` branch:

```mermaid
flowchart TD
    Query["User Query"] --> RetrieverSplit{"HybridRetriever"}
    
    subgraph ParallelRetrieval["Parallel Retrieval"]
        RetrieverSplit --> VectorRetriever["VectorRetriever<br/>(FAISS IndexFlatIP Cosine Similarity)"]
        RetrieverSplit --> KeywordRetriever["KeywordRetriever<br/>(PostgreSQL tsvector ts_rank_cd)"]
    end
    
    VectorRetriever --> VectorScores["Vector Candidates (Top-K)"]
    KeywordRetriever --> KeywordScores["Keyword Candidates (Top-K)"]
    
    VectorScores --> ResultRanker["ResultRanker<br/>(Min-Max Normalization & Weighted Fusion: 0.6 / 0.4)"]
    KeywordScores --> ResultRanker
    
    ResultRanker --> Deduplication["Deduplicate Chunks by ID & Select Top-K"]
    Deduplication --> ContextBuilder["ContextBuilder<br/>(Delimit [DOCUMENT SOURCE S1] & Build Source Map)"]
    
    ContextBuilder --> GroundedLLM["Grounded LLM Prompt<br/>(Enforces factual grounding and [S1] citations)"]
    GroundedLLM --> CitationValidator["CitationValidator<br/>(Validates cited tags against source map; discards hallucinated [S99])"]
    
    CitationValidator --> FinalRAG["Verified Answer + Verified Sources & Citations"]
```

### Document Ingestion Pipeline

Uploaded PDF files undergo multi-stage sanitization and dual-index persistence:

```mermaid
flowchart LR
    Upload["Uploaded PDF"] --> Validator["DocumentValidator<br/>Size, MIME, Magic Bytes, pypdf"]
    Validator --> Storage["DocumentStorage<br/>UUID Filename & Traversal Check"]
    Storage --> Extractor["DocumentExtractor<br/>Page-Preserving Text Extraction"]
    Extractor --> Chunker["DocumentChunker<br/>Recursive Split (500 chars, 50 overlap)"]
    Chunker --> Embedder["EmbeddingFactory<br/>Gemini / OpenAI Embeddings"]
    
    Embedder --> PostgresChunks["PostgreSQL<br/>document_chunks (FTS tsvector)"]
    Embedder --> FAISSIndex["User FAISS Index<br/>data/indexes/{user_id}/"]
```

---

## Prerequisites

- **Python**: Version `3.10` or higher (tested with Python 3.10 - 3.13).
- **PostgreSQL**: Version `14` or higher running locally or accessible over the network.
- **LLM API Key**: At least one active API key for **Google Gemini** ([Google AI Studio](https://aistudio.google.com/)) or **OpenAI** ([OpenAI Platform](https://platform.openai.com/)).

---

## Installation & Setup

### 1. Clone the Repository

```bash
git clone <repository-url>
cd ai-agent-api
```

### 2. Set Up Python Virtual Environment

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install Dependencies

You can install dependencies via `requirement.txt` or through `pyproject.toml`:

```bash
# Production dependencies
pip install -r requirement.txt

# Or install in editable mode with development dependencies
pip install -e ".[dev]"
```

### 4. Create the PostgreSQL Database

Ensure PostgreSQL is running, then create the database:

```bash
createdb -h localhost -p 5432 -U postgres ai_agent
```

*(For testing, also create the test database: `createdb -h localhost -p 5432 -U postgres ai_agent_test`)*

### 5. Configure Environment Variables

Copy the sample environment file to `.env`:

```bash
cp .env.example .env
```

Open `.env` and set your secrets and credentials:

```dotenv
APP_NAME=AI Agent API
APP_VERSION=0.6.0
ENVIRONMENT=development

# Generate with: openssl rand -hex 32
SECRET_KEY=your-random-secret-key-at-least-32-characters-long

# PostgreSQL connection string (psycopg 3 driver)
DATABASE_URL=postgresql+psycopg://postgres:password@localhost:5432/ai_agent

# LLM Providers (Configure at least one)
LLM_PROVIDER=gemini
GOOGLE_API_KEY=your-google-ai-studio-api-key
GEMINI_MODEL=gemini-2.0-flash

# Optional: OpenAI
OPENAI_API_KEY=your-openai-api-key
OPENAI_MODEL=gpt-4o-mini

# Embeddings
EMBEDDING_PROVIDER=gemini
EMBEDDING_MODEL=text-embedding-004
```

---

## Configuration & Environment Variables

All settings are managed through `Settings` (`app/config.py`) using Pydantic Settings with strict validation:

| Variable | Type | Default | Description |
|---|---|---|---|
| `APP_NAME` | `str` | `AI Agent API` | Service name reported in logs and health checks. |
| `APP_VERSION` | `str` | `0.6.0` | Semantic version string. |
| `ENVIRONMENT` | `str` | `development` | Runtime environment (`development`, `staging`, `production`). |
| `SECRET_KEY` | `str` | *Required* | JWT signing key (\(\ge 32\) characters). |
| `DATABASE_URL` | `str` | *Required* | PostgreSQL URL (e.g. `postgresql+psycopg://user:pass@host:5432/db`). |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `int` | `1440` | JWT expiration duration in minutes (24 hours). |
| `LOG_LEVEL` | `str` | `INFO` | Logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`). |
| `LLM_PROVIDER` | `str` | `gemini` | Default LLM provider (`gemini` or `openai`). |
| `GOOGLE_API_KEY` | `str \| None` | `None` | Google Gemini API key. Required if using Gemini. |
| `GEMINI_MODEL` | `str` | `gemini-2.0-flash` | Default Gemini model identifier. |
| `OPENAI_API_KEY` | `str \| None` | `None` | OpenAI API key. Required if using OpenAI. |
| `OPENAI_MODEL` | `str` | `gpt-4o-mini` | Default OpenAI model identifier. |
| `LLM_TIMEOUT_SECONDS` | `int` | `30` | Timeout in seconds for LLM API calls (1–300s). |
| `LLM_MAX_RETRIES` | `int` | `2` | Maximum transient retry attempts for LLM calls (0–5). |
| `EMBEDDING_PROVIDER` | `str` | `gemini` | Vector embedding provider (`gemini` or `openai`). |
| `EMBEDDING_MODEL` | `str` | `text-embedding-004` | Embedding model identifier. |
| `DOCUMENT_STORAGE_PATH` | `str` | `data/documents` | Directory where uploaded raw PDF files are stored. |
| `FAISS_INDEX_PATH` | `str` | `data/indexes` | Root directory for isolated user FAISS indexes. |
| `MAX_DOCUMENT_SIZE_MB` | `int` | `10` | Maximum PDF file upload size limit in megabytes. |
| `RAG_CHUNK_SIZE` | `int` | `500` | Target chunk size for text splitting (characters). |
| `RAG_CHUNK_OVERLAP` | `int` | `50` | Character overlap between consecutive chunks. |
| `VECTOR_TOP_K` | `int` | `4` | Number of dense vector candidate chunks to retrieve. |
| `KEYWORD_TOP_K` | `int` | `4` | Number of full-text keyword candidate chunks to retrieve. |
| `RAG_TOP_K` | `int` | `4` | Final number of fused chunks to supply as context to the LLM. |
| `VECTOR_RETRIEVAL_WEIGHT` | `float` | `0.6` | Weight assigned to normalized vector similarity score. |
| `KEYWORD_RETRIEVAL_WEIGHT` | `float` | `0.4` | Weight assigned to normalized keyword rank score. |
| `MAX_CONVERSATION_MESSAGES`| `int` | `10` | Maximum recent message turns loaded into agent context. |
| `MAX_CONTEXT_TOKENS` | `int` | `4000` | Token / character budget for loaded conversation history. |
| `RATE_LIMIT_ENABLED` | `bool` | `True` | Master toggle for in-memory rate limiting. |
| `RATE_LIMIT_LOGIN_PER_MINUTE` | `int` | `5` | Maximum login attempts per minute per IP. |
| `RATE_LIMIT_REGISTER_PER_MINUTE`| `int` | `3` | Maximum registration attempts per minute per IP. |
| `RATE_LIMIT_AGENT_PER_MINUTE` | `int` | `20` | Maximum agent chat requests per minute per user. |
| `RATE_LIMIT_UPLOAD_PER_MINUTE` | `int` | `10` | Maximum document uploads per minute per user. |
| `RATE_LIMIT_DEFAULT_PER_MINUTE`| `int` | `60` | Fallback rate limit per minute. |
| `MAX_REQUEST_SIZE_MB` | `int` | `15` | Maximum allowable HTTP request payload size in MB. |
| `MAX_MESSAGE_LENGTH` | `int` | `4000` | Maximum allowable character length for a chat message. |
| `MAX_TOOL_CALLS_PER_REQUEST` | `int` | `5` | Upper limit on tool calls executed per single chat turn. |
| `MAX_AGENT_GRAPH_ITERATIONS` | `int` | `10` | LangGraph recursion iteration limit to prevent loops. |
| `CORS_ALLOWED_ORIGINS` | `str` | `http://localhost:8000,...`| Comma-separated list of allowed CORS origins. |

---

## Running the Application

### Start Uvicorn Server

The database schema initializes automatically during the application startup lifespan (`app/main.py`):

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Once running, the following endpoints are immediately available:
- **Web User Interface**: [http://localhost:8000/ui/](http://localhost:8000/ui/) (or [http://localhost:8000/](http://localhost:8000/) redirect)
- **Interactive OpenAPI Docs (Swagger UI)**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **ReDoc Documentation**: [http://localhost:8000/redoc](http://localhost:8000/redoc)
- **Liveness Probe**: [http://localhost:8000/health](http://localhost:8000/health)
- **Readiness Probe**: [http://localhost:8000/ready](http://localhost:8000/ready)

---

## Web Interface (GUI)

The service includes a built-in, responsive single-page web GUI served directly by FastAPI under `/ui/`:

- **Zero Build Step**: Pure Vanilla HTML5, modern CSS3 (custom CSS variables, responsive grid/flexbox), and modular Vanilla JavaScript ES6 modules (`import`/`export`). No Node.js, Webpack, or npm dependencies.
- **Authentication**: Dedicated `/ui/login.html` and `/ui/register.html` views storing the JWT token in `localStorage`.
- **Conversational Chat**: Interactive multi-turn interface supporting real-time chat, Markdown rendering, auto-scrolling, code blocks, and conversation history sidebar.
- **Model Selector**: Dynamic dropdown populated at runtime from `GET /agent/models`, allowing instant switching between configured Google Gemini and OpenAI models.
- **Document Management Modal**: Manage your personal RAG knowledge base:
  - Drag-and-drop PDF upload with progress feedback.
  - Real-time processing status tracking (`pending`, `processing`, `ready`, `failed`).
  - View document page counts and chunk counts.
  - Delete documents with one click (purges file, database records, and vector index).
- **Interactive Citation Badges**: Messages containing source references display clickable `[S1]`, `[S2]` citation badges with popovers showing source filename, page number, relevance score, and excerpt.

---

## API Reference

All requests expecting or returning JSON use standard HTTP status codes. Protected endpoints require the `Authorization: Bearer <token>` header.

### System Probes

#### `GET /health`
Liveness probe checking if the ASGI service is responding.
- **Auth**: None
- **Response `200 OK`**:
  ```json
  {
    "status": "ok",
    "service": "AI Agent API",
    "version": "0.6.0"
  }
  ```

#### `GET /ready`
Readiness probe testing database connectivity via `SELECT 1;`.
- **Auth**: None
- **Response `200 OK`**:
  ```json
  {
    "status": "ready",
    "database": "connected"
  }
  ```
- **Response `503 Service Unavailable`**: Returned if the database connection fails.

---

### Authentication (`/auth`)

#### `POST /auth/register`
Create a new user account with an email and password.
- **Rate Limit**: 3 requests/minute per IP
- **Request Body**:
  ```json
  {
    "email": "developer@example.com",
    "password": "StrongPassword123"
  }
  ```
- **Response `201 Created`**:
  ```json
  {
    "id": "3a1f6b94-7619-457e-9497-ba105ce1e38e",
    "email": "developer@example.com",
    "created_at": "2026-10-26T18:00:00Z"
  }
  ```

#### `POST /auth/login`
Authenticate with email and password to receive a JWT bearer token.
- **Rate Limit**: 5 requests/minute per IP
- **Request Body**:
  ```json
  {
    "email": "developer@example.com",
    "password": "StrongPassword123"
  }
  ```
- **Response `200 OK`**:
  ```json
  {
    "access_token": "eyJhbGciOiJIUzI1Ni...",
    "token_type": "bearer"
  }
  ```

#### `GET /auth/me`
Retrieve the profile of the currently authenticated user.
- **Auth**: Bearer Token
- **Response `200 OK`**:
  ```json
  {
    "id": "3a1f6b94-7619-457e-9497-ba105ce1e38e",
    "email": "developer@example.com",
    "created_at": "2026-10-26T18:00:00Z"
  }
  ```

---

### Conversations (`/conversations`)

#### `POST /conversations`
Create a new conversation thread owned by the caller.
- **Auth**: Bearer Token
- **Request Body**:
  ```json
  {
    "title": "System Architecture Discussion"
  }
  ```
- **Response `201 Created`**:
  ```json
  {
    "id": "e9b25164-94c3-4d6c-bb9a-32fae0a29482",
    "user_id": "3a1f6b94-7619-457e-9497-ba105ce1e38e",
    "title": "System Architecture Discussion",
    "created_at": "2026-10-26T18:05:00Z"
  }
  ```

#### `GET /conversations`
List all conversations owned exclusively by the authenticated user (sorted newest first).
- **Auth**: Bearer Token
- **Response `200 OK`**: Array of `ConversationResponse` objects.

#### `GET /conversations/{conversation_id}`
Get metadata for a specific conversation.
- **Auth**: Bearer Token
- **Response `200 OK`**: `ConversationResponse`
- **Response `404 Not Found`**: Returned if the conversation does not exist or belongs to another user (IDOR protection).

#### `GET /conversations/{conversation_id}/messages`
Get chronological message history for a conversation.
- **Auth**: Bearer Token
- **Response `200 OK`**:
  ```json
  [
    {
      "id": "a1b2c3d4-...",
      "conversation_id": "e9b25164-...",
      "role": "user",
      "content": "Can you summarize our document retention rules?",
      "created_at": "2026-10-26T18:06:00Z"
    },
    {
      "id": "d4c3b2a1-...",
      "conversation_id": "e9b25164-...",
      "role": "assistant",
      "content": "Inactive accounts are retained for 90 days. [S1]",
      "created_at": "2026-10-26T18:06:02Z"
    }
  ]
  ```

---

### AI Agent (`/agent`)

#### `GET /agent/models`
Inspect backend-approved providers and models.
- **Auth**: None
- **Response `200 OK`**:
  ```json
  {
    "default_provider": "gemini",
    "default_model": "gemini-2.0-flash",
    "providers": {
      "gemini": {
        "name": "Google Gemini",
        "models": ["gemini-1.5-flash", "gemini-1.5-pro", "gemini-2.0-flash"]
      },
      "openai": {
        "name": "OpenAI",
        "models": ["gpt-3.5-turbo", "gpt-4o", "gpt-4o-mini"]
      }
    }
  }
  ```

#### `POST /agent/chat`
Submit a message to the LangGraph AI Agent.
- **Auth**: Bearer Token
- **Rate Limit**: 20 requests/minute per user
- **Request Body**:
  ```json
  {
    "conversation_id": "e9b25164-94c3-4d6c-bb9a-32fae0a29482",
    "message": "What is our company's refund policy?",
    "provider": "gemini",
    "model": "gemini-2.0-flash"
  }
  ```
- **Response `200 OK`**:
  ```json
  {
    "conversation_id": "e9b25164-94c3-4d6c-bb9a-32fae0a29482",
    "message": "Refund requests must be filed within 30 days of initial purchase. [S1]",
    "role": "assistant",
    "intent": "document_search",
    "provider": "gemini",
    "model": "gemini-2.0-flash",
    "citations": [
      {
        "source_id": "S1",
        "filename": "refund-policy.pdf",
        "page_number": 1,
        "valid": true
      }
    ],
    "sources": [
      {
        "source_id": "S1",
        "filename": "refund-policy.pdf",
        "page_number": 1,
        "chunk_index": 0,
        "score": 0.92,
        "text_snippet": "Refund requests must be filed within 30 days of purchase..."
      }
    ]
  }
  ```

---

### Documents & RAG (`/documents`)

#### `POST /documents/upload`
Upload and process a PDF file into the user's isolated RAG index.
- **Auth**: Bearer Token
- **Rate Limit**: 10 requests/minute per user
- **Content-Type**: `multipart/form-data`
- **Form Field**: `file` (PDF file, maximum 10MB)
- **Response `201 Created`**:
  ```json
  {
    "id": "640702c0-0258-44ba-bc94-585feca53eb3",
    "original_filename": "architecture-handbook.pdf",
    "file_size": 245190,
    "content_type": "application/pdf",
    "status": "ready",
    "page_count": 12,
    "chunk_count": 34,
    "processing_error": null,
    "created_at": "2026-10-26T18:10:00Z",
    "updated_at": "2026-10-26T18:10:04Z"
  }
  ```

#### `GET /documents`
List all documents uploaded by the authenticated user.
- **Auth**: Bearer Token
- **Response `200 OK`**:
  ```json
  {
    "documents": [
      {
        "id": "640702c0-0258-44ba-bc94-585feca53eb3",
        "original_filename": "architecture-handbook.pdf",
        "file_size": 245190,
        "content_type": "application/pdf",
        "status": "ready",
        "page_count": 12,
        "chunk_count": 34,
        "processing_error": null,
        "created_at": "2026-10-26T18:10:00Z",
        "updated_at": "2026-10-26T18:10:04Z"
      }
    ],
    "total": 1
  }
  ```

#### `GET /documents/{document_id}`
Fetch metadata for a single document owned by the user.
- **Auth**: Bearer Token
- **Response `200 OK`**: `DocumentResponse`
- **Response `404 Not Found`**: If not found or owned by another user.

#### `DELETE /documents/{document_id}`
Atomically delete a document, unlinking physical storage, removing database chunks, and pruning the user's FAISS index.
- **Auth**: Bearer Token
- **Response `200 OK`**:
  ```json
  {
    "detail": "Document successfully deleted",
    "document_id": "640702c0-0258-44ba-bc94-585feca53eb3"
  }
  ```

#### `POST /documents/query`
Execute a direct, grounded hybrid RAG query against indexed documents.
- **Auth**: Bearer Token
- **Request Body**:
  ```json
  {
    "query": "What are the retention terms for inactive accounts?",
    "top_k": 4,
    "provider": "gemini",
    "model": "gemini-2.0-flash"
  }
  ```
- **Response `200 OK`**:
  ```json
  {
    "query": "What are the retention terms for inactive accounts?",
    "response": "Accounts inactive for more than 90 days are archived. [S1]",
    "citations": [
      {
        "source_id": "S1",
        "filename": "retention-policy.pdf",
        "page_number": 2,
        "valid": true
      }
    ],
    "sources": [
      {
        "source_id": "S1",
        "filename": "retention-policy.pdf",
        "page_number": 2,
        "chunk_index": 3,
        "score": 0.88,
        "text_snippet": "Accounts inactive for more than 90 days are archived..."
      }
    ],
    "retrieved_count": 2,
    "retrieval_mode": "hybrid",
    "provider": "gemini",
    "model": "gemini-2.0-flash"
  }
  ```

---

## End-to-End Workflow Examples

### 1. Register and Authenticate via CLI

```bash
# 1. Register a new user account
curl -s -X POST http://localhost:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email": "alice@example.com", "password": "Password123!"}'

# 2. Log in and export access token
TOKEN=$(curl -s -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "alice@example.com", "password": "Password123!"}' \
  | grep -o '"access_token":"[^"]*' | cut -d'"' -f4)

echo "Token: $TOKEN"
```

### 2. Upload and Index a PDF Document

```bash
curl -s -X POST http://localhost:8000/documents/upload \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@sample-manual.pdf;type=application/pdf"
```

### 3. Initiate a Conversation and Chat with RAG

```bash
# 1. Create conversation thread
CONV_ID=$(curl -s -X POST http://localhost:8000/conversations \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"title": "Product Research"}' \
  | grep -o '"id":"[^"]*' | cut -d'"' -f4)

# 2. Ask a question answered by your uploaded document
curl -s -X POST http://localhost:8000/agent/chat \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{
    \"conversation_id\": \"$CONV_ID\",
    \"message\": \"What are the main installation steps listed in the manual?\",
    \"provider\": \"gemini\"
  }"
```

### 4. Query Grounded Documents Directly

```bash
curl -s -X POST http://localhost:8000/documents/query \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Summarize section 2.1 specifications",
    "top_k": 4
  }'
```

---

## RAG Evaluation Suite

The repository includes a deterministic, offline evaluation benchmark suite under `app/rag/evaluation/` that verifies retrieval and grounding quality **without requiring paid third-party SaaS or external LLM API tokens**:

### Running the Evaluator

Execute the module using the Python virtual environment:

```bash
python3 -m app.rag.evaluation
```

### Evaluated Benchmark Metrics

| Metric | Category | Formula / Definition | Passing Criteria |
|---|---|---|---|
| **Hit Rate@K** | Retrieval | \(1.0\) if at least one relevant ground-truth chunk is in the top-K retrieved, else \(0.0\). | \(\ge 0.75\) |
| **Citation Validity** | Attribution | Fraction of cited sources in the answer that reference genuine retrieved chunk IDs (rejects hallucinations like `[S99]`). | \(\ge 0.90\) |
| **Grounding Score** | Generation | Fraction of key ground-truth factual statements represented in the generated response. | \(\ge 0.65\) |
| **Recall@K** | Retrieval | Proportion of all relevant ground-truth chunks retrieved in top-K candidates. | Diagnostic |
| **Precision@K** | Retrieval | Proportion of retrieved chunks that are genuinely relevant to the query. | Diagnostic |

### CLI Exit Codes
- `0`: All benchmark test cases met or exceeded threshold requirements.
- `1`: One or more benchmark metrics violated threshold criteria (signaling a RAG regression).

---

## Security Architecture & Defense in Depth

The application implements rigorous defensive controls documented in `docs/security.md` and `docs/observability.md`:

1. **Authentication & Password Security**:
   - Passwords hashed with `Argon2id` via `argon2-cffi`. Password hashes are excluded from all serialization schemas.
   - Cryptographically signed JWT tokens with expiration enforced on every protected route.
2. **Strict Multi-Tenancy & IDOR Defense**:
   - Every database query explicitly filters by `user_id == current_user.id`.
   - Access attempts against resources belonging to another user return generic `404 Not Found` responses to prevent ID enumeration, while logging an `UNAUTHORIZED_ACCESS_ATTEMPT` security event.
   - FAISS indexes are stored in separate filesystem directories per tenant (`data/indexes/{user_id}/`).
3. **Prompt Injection & System Prompt Protection**:
   - `PromptGuard` (`app/security/prompt_guard.py`) heuristic scanner intercepts instruction overrides (`"ignore previous instructions"`, `"DAN mode"`) and disclosure queries (`"show your system prompt"`).
   - Prompts use structural demarcation separating immutable system instructions from passive retrieved context and untrusted user input.
4. **Tool Authorization Policy**:
   - Only registered tools (`SafeDatabaseTool` in `app/tools/safe_database.py`) can be executed. Shell commands, raw SQL, `eval()`, and filesystem traversal are forbidden.
   - The authenticated `user_id` is bound securely by the application; model-supplied `user_id` arguments are strictly discarded.
   - Bounded by `MAX_TOOL_CALLS_PER_REQUEST = 5` to prevent recursive loop cost exhaustion.
5. **PDF Upload Sanitization**:
   - File size checked before buffering (\(\le 10\text{MB}\)).
   - Verification of file extension, MIME type (`application/pdf`), and `%PDF-` magic header bytes.
   - Structural validation with `pypdf` ensuring valid pages exist before any vectorization.
   - Server-generated UUID filenames resolving with `path.is_relative_to(base_dir)` to defeat directory climbing attacks (`../../`).
6. **Rate Limiting & DoS Mitigation**:
   - `SlidingWindowRateLimiter` (`app/security/rate_limit.py`) with monotonic clocks, max key bounds (10,000 keys), and automated stale entry eviction.
   - IP-keyed on `/auth` endpoints; user-keyed on AI `/agent` and `/documents` endpoints.
   - `RequestSizeLimitMiddleware` (`app/security/request_size.py`) rejects payloads exceeding 15MB with HTTP 413.
7. **HTTP Security Headers**:
   - `SecurityHeadersMiddleware` (`app/security/headers.py`) attaches `Content-Security-Policy`, `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: strict-origin-when-cross-origin`, and `Permissions-Policy`.
8. **Sensitive Data Scrubbing**:
   - Custom logging filter `SensitiveDataScrubber` (`app/observability/logging.py`) automatically redacts Bearer tokens, OpenAI keys (`sk-...`), Google AI keys (`AIza...`), password fields, and raw JWT strings from application logs.

---

## Testing & Quality Assurance

The codebase features comprehensive test coverage with **129 passing automated tests** across unit, integration, and security suites:

```bash
# Run the complete test suite
pytest

# Run tests with short traceback and verbose output
pytest -v --tb=short

# Run a specific test module
pytest tests/test_security_hardening.py
```

### Static Analysis & Linting

Code formatting and quality checks are configured via [Ruff](https://github.com/astral-sh/ruff) in `pyproject.toml`:

```bash
# Check code style and lint rules
ruff check .

# Check formatting
ruff format --check .
```

---

## Troubleshooting

### 1. Database Connection Refused
- **Symptom**: `OperationalError: connection to server at "localhost" failed` or `/ready` returns 503.
- **Solution**: Confirm PostgreSQL is active on port 5432 and the credentials in `DATABASE_URL` match your local PostgreSQL role. Verify database existence with `psql -U postgres -d ai_agent`.

### 2. LLM Provider Missing Credentials
- **Symptom**: `ValueError: GOOGLE_API_KEY is not configured in the application environment.` or HTTP 500 on chat.
- **Solution**: Check your `.env` file. If `LLM_PROVIDER=gemini`, supply a valid `GOOGLE_API_KEY`. If `LLM_PROVIDER=openai`, set `OPENAI_API_KEY`.

### 3. Rate Limit Exceeded (HTTP 429)
- **Symptom**: HTTP 429 response with `{"detail": "Rate limit exceeded. Please retry in X seconds."}`.
- **Solution**: Check response header `Retry-After`. For development or load testing, adjust `RATE_LIMIT_AGENT_PER_MINUTE` or set `RATE_LIMIT_ENABLED=false` in `.env`.

### 4. PDF Upload Rejected (HTTP 400)
- **Symptom**: `Uploaded file is not a valid PDF` or `File size exceeds maximum allowed size`.
- **Solution**: Verify the file has a genuine `%PDF-` header byte sequence, is not a password-protected or corrupted binary, and does not exceed `MAX_DOCUMENT_SIZE_MB` (default 10MB).

### 5. CORS Header Issues with External Frontend
- **Symptom**: Browser blocks requests with `Access-Control-Allow-Origin` errors.
- **Solution**: Add your frontend origin (e.g., `http://localhost:3000`) to `CORS_ALLOWED_ORIGINS` in `.env`.

