# DATN Backend

A FastAPI backend for the DATN notebook workspace and document-grounded RAG system. The backend handles Supabase authentication, notebook/source management, PDF/DOCX ingestion, asynchronous document indexing, vector retrieval, streaming chat answers, citations, and saved Studio notes.

This README follows the structure of the older `pdp8-rag` README, but the content reflects the current `DATN/backend` implementation.

## Features

### Core Capabilities
- **Supabase Auth Integration**: Email/password registration helper and bearer-token user resolution.
- **Notebook Workspaces**: User-owned notebooks with isolated sources, chat sessions, and saved notes.
- **Worker-Only Document Indexing**: Uploads are queued through Celery so expensive extraction and embedding do not block API requests.
- **PDF and DOCX Uploads**: PDF files go directly through the PDF pipeline; DOCX files are converted to PDF in the worker with LibreOffice.
- **LLM-Enhanced PDF Processing**: Marker extracts markdown, tables, page markers, and optional image/figure descriptions.
- **Semantic Chunking**: Chonkie semantic chunking preserves topical coherence while retaining page ranges and table metadata.
- **Vector Search**: Supabase PostgreSQL with pgvector `halfvec(3072)` and HNSW indexing.
- **Adaptive RAG**: DSPy selects single-hop or multi-hop retrieval based on query scope and complexity.
- **Streaming Answers**: Notebook chat supports NDJSON token streaming with final source metadata.
- **Gemini Context Cache**: Selected-document streaming queries can use Gemini cached content with Redis-backed source manifests.
- **Citation Safety**: Cached citations are resolved against stored source manifests and fall back to DSPy if unsafe.

### Architecture
- **FastAPI API**: Auth, notebook, document, chat, note, and health endpoints.
- **Celery Workers**: Distributed document extraction, embedding fan-out, and processing finalization.
- **Redis**: Celery broker/backend, rate limiting state, distributed locks, and Gemini cache registry.
- **Supabase**: Auth, PostgreSQL tables, pgvector similarity search, RLS policies, and private `pdfs` storage bucket.
- **Gemini**: Generation, embeddings, Marker LLM support, image captions, and cached content.
- **DSPy**: Structured single-hop, multi-hop, and adaptive RAG modules.
- **Sentence Transformers**: Cross-encoder reranking with `BAAI/bge-reranker-v2-m3`.
- **Docker Compose**: API, worker, Redis, and optional Flower monitoring.

### Processing Pipeline
1. **Upload**: Authenticated user uploads a PDF or DOCX to a notebook.
2. **Queue**: API writes a pending status row and sends a Celery task.
3. **Conversion**: Worker converts DOCX to PDF when needed.
4. **Extraction**: Marker extracts markdown, tables, page markers, and visuals.
5. **Chunking**: Semantic chunking produces page-aware chunks.
6. **Embedding**: Celery fan-out generates Gemini embeddings per chunk.
7. **Storage**: Chunks are stored in Supabase with metadata and vectors.
8. **Finalization**: Worker marks the document as completed or failed.
9. **Retrieval**: RAG queries search notebook-scoped vectors and optionally rerank.
10. **Generation**: DSPy or Gemini cached context produces cited answers.

## Installation

### Prerequisites
- Python 3.12
- `uv`
- Docker and Docker Compose
- Supabase project with the migrations in `supabase/migrations`
- Redis, either local or through Docker Compose
- Google API key for Gemini
- LibreOffice for DOCX conversion when running workers outside Docker

### Environment

Create `backend/.env`:

```env
SUPABASE_URL=https://your-project-ref.supabase.co
SUPABASE_ANON_KEY=your-supabase-anon-key
SUPABASE_SERVICE_KEY=your-supabase-service-role-key
REDIS_URL=redis://localhost:6379/0
GOOGLE_API_KEY=your-google-api-key
DOCUMENT_PROCESSING_MODE=worker
DATN_REQUIRE_WORKER_MODE=true
UPLOADS_DIR=/app/uploads
```

`DATN_REQUIRE_WORKER_MODE=true` makes startup fail unless `DOCUMENT_PROCESSING_MODE=worker`. This is intentional for Docker/production because document indexing is designed to run through Celery.

### Quick Start With Docker

1. Start API, worker, and Redis:

```bash
cd backend
docker compose up --build
```

This starts:

- Backend API (http://localhost:8000)
- Celery worker for document indexing
- Redis (localhost:6379)

2. Open the API docs:

- API: http://localhost:8000
- API docs: http://localhost:8000/docs
- Health: http://localhost:8000/health

3. Start Flower when task monitoring is needed:

```bash
cd backend
docker compose --profile monitoring up flower
```

Flower runs at http://localhost:5555.

### Manual Installation (Development)

#### Backend Setup

1. Install dependencies:

```bash
cd backend
uv sync
```

2. Start Redis:

```bash
docker run --rm -p 6379:6379 redis:7
```

3. Start the API:

```bash
cd backend
uv run uvicorn app.main:app --reload
```

4. Start the worker:

```bash
cd backend
uv run celery -A app.workers.celery_app worker --loglevel=info --pool=solo --concurrency=1 -Q document_processing,embedding,storage
```

5. Optional Flower:

```bash
cd backend
uv run celery -A app.workers.celery_app flower --port=5555
```

#### Frontend Setup

The frontend lives outside this folder at `../frontend`.

1. Install dependencies:

```bash
cd ../frontend
npm install
```

2. Configure frontend environment if it is not already available from root/backend env files:

```env
VITE_SUPABASE_URL=https://your-project-ref.supabase.co
VITE_SUPABASE_ANON_KEY=your-supabase-anon-key
VITE_BACKEND_URL=http://localhost:8000
VITE_APP_URL=http://localhost:5173
```

3. Start the frontend dev server:

```bash
npm run dev
```

4. Build for production:

```bash
npm run build
```

## Usage

All notebook routes require an `Authorization: Bearer <supabase-access-token>` header.

### Web Interface

1. Start the backend API, worker, Redis, and frontend dev server.
2. Open http://localhost:5173.
3. Sign in with Supabase Auth.
4. Create or open a notebook.
5. Upload PDF or DOCX sources and wait until indexing completes.
6. Ask questions over selected completed sources and review citations.
7. Save useful answers as Studio notes when needed.

### API Usage

#### Health Check

```bash
curl http://localhost:8000/health
```

#### Sign Up

```bash
curl -X POST "http://localhost:8000/auth/sign-up" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "user@example.com",
    "password": "strong-password"
  }'
```

#### Current User

```bash
curl "http://localhost:8000/auth/me" \
  -H "Authorization: Bearer <supabase-access-token>"
```

#### Create Notebook

```bash
curl -X POST "http://localhost:8000/notebooks" \
  -H "Authorization: Bearer <supabase-access-token>" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Research Notebook",
    "description": "Source-grounded working notes"
  }'
```

#### List Notebooks

```bash
curl "http://localhost:8000/notebooks" \
  -H "Authorization: Bearer <supabase-access-token>"
```

#### Upload Document

```bash
curl -X POST "http://localhost:8000/notebooks/{notebook_id}/documents/upload" \
  -H "Authorization: Bearer <supabase-access-token>" \
  -F "file=@/path/to/document.pdf"
```

The response returns `queued: true`; poll document status until it becomes `completed`.

#### List Documents

```bash
curl "http://localhost:8000/notebooks/{notebook_id}/documents" \
  -H "Authorization: Bearer <supabase-access-token>"
```

#### Ask a Notebook Question

```bash
curl -X POST "http://localhost:8000/notebooks/{notebook_id}/chat/messages" \
  -H "Authorization: Bearer <supabase-access-token>" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Summarize the main requirements in these documents.",
    "document_names": ["document"]
  }'
```

#### Stream a Notebook Question

```bash
curl -N -X POST "http://localhost:8000/notebooks/{notebook_id}/chat/messages/stream" \
  -H "Authorization: Bearer <supabase-access-token>" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Compare the key differences between the selected sources.",
    "document_names": ["source-a", "source-b"]
  }'
```

The stream uses `application/x-ndjson` events:

```json
{"type":"token","content":"..."}
{"type":"metadata","strategy":"single-hop","sources":[...]}
{"type":"done","session_id":"...","messages":[...]}
```

#### Save a Studio Note

```bash
curl -X POST "http://localhost:8000/notebooks/{notebook_id}/notes" \
  -H "Authorization: Bearer <supabase-access-token>" \
  -H "Content-Type: application/json" \
  -d '{
    "question": "Key findings",
    "answer": "The answer to save.",
    "sources": [],
    "document_names": ["document"]
  }'
```

#### Delete Document

```bash
curl -X DELETE "http://localhost:8000/notebooks/{notebook_id}/documents/{document_name}" \
  -H "Authorization: Bearer <supabase-access-token>"
```

### Python Scripts

#### Debug Chunking

Use the read-only debug script to inspect extraction and chunking without writing to Supabase:

```bash
cd backend
uv run python scripts/debug_chunking.py /path/to/file.pdf
```

Compare extraction/chunking against another project environment:

```bash
cd ../pdp8-rag
uv run python ../backend/scripts/debug_chunking.py /path/to/file.pdf --project-root .
```

## Configuration

Runtime environment is loaded from `.env`; RAG settings are loaded from `config.yaml`.

### Application Settings (`config.yaml`)

#### LLM Configuration

```yaml
llm:
  provider: "gemini"
  gemini:
    model: "gemini-2.5-flash"
    embedding_model: "gemini-embedding-001"
    temperature: 0.7
    max_tokens: 20000
```

#### PDF Processing

```yaml
pdf:
  use_llm: true
  llm_model: "gemini-2.5-flash"
  describe_images: true
  image_caption_model: "gemini-2.5-flash"
```

#### RAG Settings

```yaml
rag:
  mode: "adaptive"
  optimized_model_path: null
  retrieval:
    top_k: 10
    similarity_threshold: 0.7
    initial_chunks_per_doc: 2
    top_n_documents: 5
    deep_chunks_per_doc: 8
    use_reranking: true
  reranking:
    model: "BAAI/bge-reranker-v2-m3"
    enabled: true
  generation:
    temperature: 0.3
    max_tokens: 8000
  multihop:
    enabled: true
    max_hops: 4
    passages_per_hop: 4
```

#### Chunking Settings

```yaml
chunking:
  strategy: "semantic"
  chunk_size: 512
  similarity_threshold: 0.5
```

#### Vector Database Settings

```yaml
vector_db:
  embedding_dimension: 3072
  similarity_metric: "cosine"
```

### Environment Settings (`.env`)

- `SUPABASE_URL` - Supabase project URL.
- `SUPABASE_ANON_KEY` - Public Supabase anon key.
- `SUPABASE_SERVICE_KEY` - Service-role key used by backend repositories and workers.
- `REDIS_URL` - Redis URL for Celery, locks, rate limits, and cache registry.
- `GOOGLE_API_KEY` - Gemini key for extraction, embeddings, caching, and generation.
- `DOCUMENT_PROCESSING_MODE` - Must be `worker` for notebook uploads.
- `DATN_REQUIRE_WORKER_MODE` - Fails API startup if worker mode is not active.
- `UPLOADS_DIR` - Shared upload path visible to API and worker.

## API Endpoints

### Health
- `GET /health` - API health and worker-mode settings.

### Auth
- `POST /auth/sign-up` - Register with Supabase email/password.
- `GET /auth/me` - Return the authenticated Supabase user.

### Notebooks
- `GET /notebooks` - List notebooks owned by the current user.
- `POST /notebooks` - Create a notebook.
- `GET /notebooks/{notebook_id}` - Get notebook detail with documents and notes.
- `PATCH /notebooks/{notebook_id}` - Update notebook title or description.
- `DELETE /notebooks/{notebook_id}` - Delete notebook and dependent rows.

### Documents
- `GET /notebooks/{notebook_id}/documents` - List document processing states.
- `POST /notebooks/{notebook_id}/documents/upload` - Upload PDF or DOCX and queue indexing.
- `POST /notebooks/{notebook_id}/documents/rename` - Rename a source by request body.
- `PATCH /notebooks/{notebook_id}/documents/{document_name}` - Rename a source by path.
- `DELETE /notebooks/{notebook_id}/documents/{document_name}` - Delete source chunks, status, local upload, and cache entries.

### Chat
- `GET /notebooks/{notebook_id}/chat/current` - Load current persisted chat session.
- `POST /notebooks/{notebook_id}/chat/messages` - Ask a RAG question and persist user/assistant messages.
- `POST /notebooks/{notebook_id}/chat/messages/stream` - Stream a RAG answer and persist final assistant message.
- `POST /notebooks/{notebook_id}/chat/new` - Clear current chat and start a new session.

### Notes
- `GET /notebooks/{notebook_id}/notes` - List saved Studio notes.
- `POST /notebooks/{notebook_id}/notes` - Save an answer as a note.
- `PATCH /notebooks/{notebook_id}/notes/{note_id}` - Rename a saved note.
- `DELETE /notebooks/{notebook_id}/notes/{note_id}` - Delete a saved note.

## Database Schema

Migrations live in `supabase/migrations`.

### Notebooks

```sql
CREATE TABLE public.notebooks (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE NOT NULL,
    title TEXT NOT NULL,
    description TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);
```

### Documents

```sql
CREATE TABLE public.documents (
    id BIGSERIAL PRIMARY KEY,
    notebook_id UUID REFERENCES public.notebooks(id) ON DELETE CASCADE NOT NULL,
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE NOT NULL,
    document_name TEXT NOT NULL,
    chunk_id INTEGER NOT NULL,
    content TEXT NOT NULL,
    embedding halfvec(3072),
    metadata JSONB,
    pages INTEGER[],
    page_range TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX documents_embedding_idx
ON public.documents USING hnsw (embedding halfvec_cosine_ops);
```

### Processing Status

```sql
CREATE TABLE public.document_processing_status (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    notebook_id UUID REFERENCES public.notebooks(id) ON DELETE CASCADE NOT NULL,
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE NOT NULL,
    document_name TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('pending', 'processing', 'completed', 'failed')),
    total_chunks INTEGER,
    processed_chunks INTEGER DEFAULT 0,
    task_id TEXT,
    error_message TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    completed_at TIMESTAMP WITH TIME ZONE,
    UNIQUE(notebook_id, document_name)
);
```

### Vector Search Function

```sql
CREATE OR REPLACE FUNCTION public.match_documents(
    query_embedding halfvec(3072),
    target_notebook_id UUID,
    match_count INTEGER DEFAULT 5,
    filter_document TEXT DEFAULT NULL
)
RETURNS TABLE (
    id BIGINT,
    document_name TEXT,
    chunk_id INTEGER,
    content TEXT,
    metadata JSONB,
    pages INTEGER[],
    page_range TEXT,
    similarity DOUBLE PRECISION
);
```

The function is granted to `service_role`; browser clients should use the backend API rather than calling RAG tables directly.

## Project Structure

```text
DATN/
|-- backend/                     # FastAPI API, workers, RAG pipeline, Supabase integration
|   |-- app/
|   |   |-- core/                # Settings, YAML config, document naming helpers
|   |   |-- db/                  # Supabase clients, vector repository, processing status repo
|   |   |-- routers/             # FastAPI auth and notebook routes
|   |   |-- schemas/             # Pydantic request/response schemas
|   |   |-- services/
|   |   |   |-- auth/            # Current-user dependency and sign-up helpers
|   |   |   |-- documents/       # Synchronous document service used by legacy/internal flows
|   |   |   |-- embedding/       # Gemini embedding service
|   |   |   |-- pdf_processor/   # Marker extraction, visual captions, semantic chunking
|   |   |   |-- rag/             # DSPy RAG, retrieval, Gemini cache, training utilities
|   |   |   |-- storage/         # Supabase Storage helper
|   |   |   `-- notebooks.py     # Notebook workspace orchestration
|   |   |-- workers/
|   |   |   |-- middleware/      # Redis locks, rate limiter, circuit breaker
|   |   |   |-- tasks/           # Document, embedding, and finalization tasks
|   |   |   `-- celery_app.py    # Celery configuration
|   |   `-- main.py              # FastAPI app factory
|   |-- models/                  # Optional local model artifacts
|   |-- scripts/                 # Utility scripts
|   |-- supabase/migrations/     # Database, RLS, storage, and vector search migrations
|   |-- tests/                   # Backend unit tests
|   |-- config.yaml              # RAG and processing configuration
|   |-- docker-compose.yml       # API, worker, Redis, and Flower
|   |-- Dockerfile               # API runtime
|   |-- Dockerfile.worker        # Worker runtime with LibreOffice
|   |-- pyproject.toml           # Python dependencies
|   `-- uv.lock
|-- frontend/                    # React + Vite notebook UI
|   |-- src/
|   |   |-- components/          # Auth, layout, chat, source, shared UI components
|   |   |-- contexts/            # Auth context
|   |   |-- hooks/               # Chat, document, auth, theme, and UI hooks
|   |   |-- lib/                 # Supabase browser client
|   |   |-- pages/               # Login, signup, dashboard, notebook editor pages
|   |   |-- services/            # Backend API, auth, chat, and document services
|   |   |-- styles/              # Global CSS and variables
|   |   |-- types/               # Shared TypeScript types
|   |   |-- App.tsx              # React app shell and routes
|   |   `-- main.tsx             # Frontend entry point
|   |-- public/                  # Static assets
|   |-- package.json             # Frontend dependencies and scripts
|   |-- vite.config.ts           # Vite config and env wiring
|   `-- tsconfig.json            # TypeScript config
|-- .env                         # Optional root environment file
`-- .gitignore
```

## Development

### Running Tests

```bash
cd backend
uv run python -m unittest discover tests
```

Useful targeted checks:

```bash
uv run python -m unittest tests.test_auth_dependencies
uv run python -m unittest tests.test_notebook_workspace
uv run python -m unittest tests.test_document_worker_conversion
uv run python -m unittest tests.test_rag_stream_cache
```

### Compile Check

```bash
cd backend
uv run python -m compileall app tests
```

### Type Checking

```bash
cd backend
uv run pyright
```

### Code Formatting

Backend formatting/linting is not configured in `pyproject.toml` yet. Keep Python changes import-sorted and run the compile/test checks above.

Frontend linting:

```bash
cd ../frontend
npm run lint
```

### Chunking Debug

```bash
cd backend
uv run python scripts/debug_chunking.py /path/to/file.pdf
```

Compare with another project environment:

```bash
cd ../pdp8-rag
uv run python ../backend/scripts/debug_chunking.py /path/to/file.pdf --project-root .
```

The script prints markdown length, first/last text, page metadata, image count, chunk ids, token counts, page ranges, content type, and snippets.

## Performance Optimizations

- **Worker mode enforcement** prevents accidental synchronous indexing in Docker/production.
- **Celery chord fan-out/fan-in** embeds chunks in parallel and finalizes status after all embeddings complete.
- **Redis distributed locks** prevent duplicate processing for the same notebook/document.
- **Circuit breakers** protect PDF extraction and Gemini embedding calls from repeated failures.
- **Token-bucket rate limiting** throttles embedding calls.
- **HNSW vector indexing** speeds up notebook-scoped similarity search.
- **Cross-encoder reranking** improves multi-document relevance.
- **Gemini cached content** accelerates streaming queries over one to three selected documents when the context is large enough.
- **Cache invalidation** runs on upload, rename, and delete so stale document context is not reused.

## Monitoring

### Celery Flower

```bash
cd backend
docker compose --profile monitoring up flower
```

Open http://localhost:5555.

### Processing Status

Check document processing status through the API:

```bash
curl "http://localhost:8000/notebooks/{notebook_id}/documents" \
  -H "Authorization: Bearer <supabase-access-token>"
```

### Health Checks

- API health: http://localhost:8000/health
- API docs: http://localhost:8000/docs
- Flower: http://localhost:5555

## Troubleshooting

### Backend Issues

**Check Docker logs:**

```bash
cd backend
docker compose logs -f backend
docker compose logs -f worker
docker compose logs -f redis
```

**Restart services:**

```bash
cd backend
docker compose restart
```

**Worker mode startup failure:**

If `DATN_REQUIRE_WORKER_MODE=true`, `DOCUMENT_PROCESSING_MODE` must be `worker`.

```env
DOCUMENT_PROCESSING_MODE=worker
DATN_REQUIRE_WORKER_MODE=true
```

**Upload stays pending:**

Check that the worker is running and connected to the same Redis URL.

**DOCX conversion fails:**

The worker runtime needs LibreOffice `soffice`. The provided `Dockerfile.worker` installs `libreoffice-writer`; local workers must install LibreOffice separately.

### Database Issues

**Check Supabase settings are loaded:**

```bash
cd backend
uv run python -c "from app.core.config import get_settings; s=get_settings(); print(s.supabase_url)"
```

**Confirm vector migration state:**

- `documents.embedding` should be `halfvec(3072)`.
- `match_documents(halfvec, uuid, integer, text)` should exist.
- HNSW index should exist on `documents.embedding`.
- The RPC should be executable by `service_role`.

**RAG returns no sources:**

Confirm the document status is `completed`, the selected `document_names` match the notebook source names, and the Supabase migration for `match_documents(halfvec, uuid, integer, text)` has been applied.

### Frontend Issues

**Install and run frontend:**

```bash
cd ../frontend
npm install
npm run dev
```

**Check frontend environment:**

```env
VITE_SUPABASE_URL=...
VITE_SUPABASE_ANON_KEY=...
VITE_BACKEND_URL=http://localhost:8000
```

**Check API connection:**

```bash
curl http://localhost:8000/health
```

### RAG and Cache Issues

**Cached streaming falls back to DSPy:**

This is expected when a cache is missing, context is too small, citations cannot be resolved against the source manifest, or similarity scores cannot be refreshed.

**Slow first query:**

The reranker is lazily loaded on first multi-document rerank and can take several seconds. It runs on CPU by default to avoid GPU contention with document processing.

## Docker Commands

### Start all services

```bash
docker compose up --build
```

### Start all services in background

```bash
docker compose up -d --build
```

### Start monitoring

```bash
docker compose --profile monitoring up -d --build
```

### Stop all services

```bash
docker compose down
```

### View logs

```bash
docker compose logs -f
```

### Rebuild containers

```bash
docker compose build
docker compose up -d
```

### Access backend shell

```bash
docker exec -it datn-backend sh
```

### Access worker shell

```bash
docker exec -it datn-worker sh
```

## Contributing

1. Create a feature branch.
2. Keep changes scoped to the relevant backend or frontend module.
3. Run the applicable tests and checks.
4. Update README or `RAG_IMPLEMENTATION_GUIDE.md` when behavior, setup, or endpoints change.
5. Open a pull request with the behavior change and verification notes.

## License

No license is specified in this repository yet.

## Acknowledgments

- Built with [FastAPI](https://fastapi.tiangolo.com/) for the backend API.
- Uses [Supabase](https://supabase.com/) for Auth, PostgreSQL, Storage, and pgvector-backed search.
- RAG prompting is structured with [DSPy](https://github.com/stanfordnlp/dspy).
- PDF extraction is powered by [Marker](https://github.com/VikParuchuri/marker).
- Embeddings and generation use Gemini models.
- Background processing uses [Celery](https://docs.celeryq.dev/) and Redis.

## Related Documentation

- `RAG_IMPLEMENTATION_GUIDE.md` - Detailed DATN/backend RAG pipeline guide.
- `supabase/migrations/` - Database, RLS, pgvector, and storage setup.
- `app/training/README.md` - DSPy training notes.
- `models/README.md` - Optional local model artifact notes.
