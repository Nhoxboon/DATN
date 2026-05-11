# DATN Backend

Slim FastAPI backend for authentication helpers and future RAG integration.

## Environment

Create `backend/.env` with:

```env
SUPABASE_URL=your_supabase_url
SUPABASE_ANON_KEY=your_supabase_anon_key
SUPABASE_SERVICE_KEY=your_supabase_service_role_key
REDIS_URL=redis://localhost:6379/0
GOOGLE_API_KEY=your_google_api_key
```

## Run With uv

Install dependencies and run the API locally:

```bash
cd backend
uv sync
uv run uvicorn app.main:app --reload
```

Run backend checks:

```bash
uv run python -m compileall app tests
uv run python -m unittest tests.test_auth_dependencies
```

## Run With Docker

Run the backend and Redis together:

```bash
cd backend
docker compose up --build
```

Run in the background:

```bash
docker compose up -d --build
```

Stop services:

```bash
docker compose down
```

The Docker Compose setup loads `backend/.env`, starts Redis as the `redis` service, and overrides `REDIS_URL` to `redis://redis:6379/0` inside the backend container.
Docker Compose also forces `DOCUMENT_PROCESSING_MODE=worker` and `DATN_REQUIRE_WORKER_MODE=true`, so production-style document indexing fails fast if it is not routed through Celery.

## RAG Chunking Debug

Use the read-only chunking debug command to compare DATN and `pdp8-rag` without writing to Supabase:

```bash
cd backend
uv run python scripts/debug_chunking.py /path/to/file.pdf
```

Run the same processor from the `pdp8-rag` environment:

```bash
cd ../pdp8-rag
uv run python ../backend/scripts/debug_chunking.py /path/to/file.pdf --project-root .
```

The command prints markdown length, first/last text, chunk count, chunk ids, token counts, page metadata, and chunk snippets.

## Local Ports

When running locally, the project uses these default ports:

- Backend API: http://localhost:8000
- Backend API docs: http://localhost:8000/docs
- Backend health check: http://localhost:8000/health
- Frontend dev server: http://localhost:5173
- Redis: localhost:6379
