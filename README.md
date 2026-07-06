# MinutesAPP

MinutesAPP is a lightweight, AI-assisted meeting intelligence application that transforms raw meeting minutes into structured, actionable project artifacts.

It is designed to reduce administrative overhead while improving continuity, accountability, and visibility across projects.

---

## Why MinutesAPP

In many teams, valuable decisions and action items are buried in meeting notes, emails, or documents that are difficult to track over time.

MinutesAPP addresses this by:

- Converting unstructured meeting notes into structured data  
- Preserving project context across meetings  
- Supporting executive-ready summaries and project health views  

---

## Core Features

### Minutes Upload & Parsing

- Upload meeting minutes in **PDF, DOCX, or TXT** format
- Automatically extract:
  - **Decisions**
  - **Actions**
  - **Risks**
  - **Issues**
  - **Accomplishments**

### Project Summary

- Generate summaries over a configurable time window
- View project health indicators including:
  - Decisions
  - Actions
  - Risks
  - Issues
  - Overdue actions

---

## Example Workflow

1. Upload meeting minutes and associate them with a project
2. MinutesAPP extracts and stores structured items
3. Review parsed decisions and actions
4. Generate summaries for status updates or leadership briefings

---

## Tech Stack

- **Backend:** Python, FastAPI  
- **Frontend:** HTML / CSS  
- **LLM:** Gemma3:4b (Went for something lightweight, you could use llama3:8b but that would require more compute(~16GB) to run locally)
- **Storage:** Postgres

---

## Status

MinutesAPP is production-ready for local and containerized deployment. See [Running in production](#running-in-production) below.

<img width="1059" height="1065" alt="image003" src="https://github.com/user-attachments/assets/ac0c3552-c54d-463d-9998-19e745a4911c" />
<img width="1390" height="769" alt="image002" src="https://github.com/user-attachments/assets/3f4b8cc8-01bc-4a3f-bde3-38aadff0c98a" />
<img width="945" height="409" alt="image001" src="https://github.com/user-attachments/assets/7286ee6e-8de7-4495-a673-6310f87633ce" />

---

## Quick Start (Local)

### Prerequisites

- Python 3.12+
- PostgreSQL with [pgvector](https://github.com/pgvector/pgvector)
- [Ollama](https://ollama.com/) with `gemma3:4b` and `nomic-embed-text` models pulled

### Setup

```bash
# Start database
docker compose up -d db

# Install dependencies
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Configure environment
cp .env.example .env

# Run API
uvicorn app.main:app --reload --port 8000
```

Open **http://localhost:8000** for the dashboard, or **http://localhost:8000/app** to upload minutes.

### Pull Ollama models

```bash
ollama pull gemma3:4b
ollama pull nomic-embed-text
```

---

## Running in Production

### Docker Compose (recommended)

Runs the API and Postgres together. Ollama is expected on the host at port 11434.

```bash
docker compose up -d --build
```

- **Dashboard:** http://localhost:8000
- **Health check:** http://localhost:8000/health
- **API reference:** http://localhost:8000/api

### Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `postgresql+psycopg://app:app@localhost:5432/minutesdb` | Postgres connection string |
| `OLLAMA_HOST` | `http://localhost:11434` | Ollama API endpoint |
| `OLLAMA_LLM_MODEL` | `gemma3:4b` | Model for extraction and plans |
| `OLLAMA_EMBED_MODEL` | `nomic-embed-text` | Embedding model (768-dim) |
| `MAX_UPLOAD_BYTES` | `10485760` | Max upload size (10 MB) |
| `CORS_ORIGINS` | _(empty)_ | Comma-separated allowed origins |
| `DEBUG` | `false` | Enable debug logging |

### Health checks

- `GET /health` — overall status (database + Ollama)
- `GET /health/db` — database only

The Docker image includes a built-in healthcheck against `/health`.

### Project structure

```
app/
  config.py          # Environment-based settings
  main.py            # FastAPI app factory
  routers/           # API and UI routes
  services/          # LLM, ingest, file parsing
  templates/         # Jinja2 HTML templates
  static/            # CSS and client JS
db/
  schema.sql         # Postgres + pgvector schema
```

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/` | Web dashboard |
| `GET` | `/app` | Upload UI |
| `GET` | `/summary-ui` | Summary UI |
| `GET` | `/search-ui` | Semantic search UI |
| `GET` | `/items-ui` | Item management UI |
| `GET` | `/health-ui` | Human-friendly health page |
| `POST` | `/upload` | Upload minutes file |
| `POST` | `/ingest` | Ingest raw text (JSON) |
| `GET` | `/items` | List extracted items |
| `PATCH` | `/items/{id}` | Update item owner, status, due date |
| `GET` | `/search` | Semantic search (`detail=true` for excerpts) |
| `GET` | `/summary` | Project rollup |
| `GET` | `/projects` | List projects |
| `POST` | `/reembed` | Backfill embeddings |
| `GET` | `/health` | Service health (JSON) |

