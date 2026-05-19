# Complete RAG Implementation Guide: DATN Backend

A practical deep-dive into the current Retrieval-Augmented Generation implementation in `DATN/backend`.

This guide intentionally follows the format of `pdp8-rag/RAG_IMPLEMENTATION_GUIDE.md`, but the implementation details are from the current DATN backend. DATN is now a notebook-scoped RAG backend with authentication, source management, asynchronous document indexing, streaming chat, Gemini cached context, and saved notes.

---

## Table of Contents

1. [Overview](#overview)
2. [Step 1: Document Ingestion & Chunking](#step-1-document-ingestion--chunking)
3. [Step 2: Embedding Generation](#step-2-embedding-generation)
4. [Step 3: Vector Storage](#step-3-vector-storage)
5. [Step 4: Retrieval](#step-4-retrieval)
6. [Step 5: Reranking](#step-5-reranking)
7. [Step 6: Answer Generation](#step-6-answer-generation)
8. [Step 7: Streaming & Cached Context](#step-7-streaming--cached-context)
9. [Complete Pipeline Summary](#complete-pipeline-summary)
10. [Operational Notes](#operational-notes)
11. [Best Practices](#best-practices)
12. [Troubleshooting](#troubleshooting)

---

## Overview

### What RAG Means in DATN

DATN uses Retrieval-Augmented Generation to answer questions from documents uploaded into a user-owned notebook. The model does not query a global corpus by default; retrieval is scoped by `notebook_id` and usually further scoped by selected source names.

The main product workflow is:

1. A user signs in through Supabase Auth.
2. The user creates a notebook.
3. The user uploads PDF or DOCX sources.
4. Celery workers extract, chunk, embed, and store the sources.
5. The user asks questions over selected completed documents.
6. The backend returns persisted chat messages with citations and source metadata.
7. The user can save useful answers as notebook notes.

### The RAG Pipeline

```text
Upload
  -> Queue worker task
  -> DOCX-to-PDF conversion when needed
  -> Marker PDF extraction
  -> Image/table/page-aware markdown normalization
  -> Semantic chunking
  -> Gemini embeddings
  -> Supabase pgvector storage
  -> Notebook-scoped retrieval
  -> Optional cross-encoder reranking
  -> DSPy or Gemini cached-context generation
  -> Chat persistence and citations
```

### Architecture Components

- **Backend**: FastAPI async API (`app/main.py`, `app/routers/notebooks.py`)
- **Authentication**: Supabase Auth (`app/routers/auth.py`, `app/services/auth/*`)
- **Workspace Model**: Notebook-scoped documents, chats, and notes (`app/services/notebooks.py`)
- **Task Queue**: Celery + Redis (`app/workers/celery_app.py`, `app/workers/tasks/*`)
- **Vector DB**: Supabase PostgreSQL + pgvector (`app/db/repository.py`, `supabase/migrations/*.sql`)
- **Storage**: Supabase Storage for uploaded and converted PDFs (`app/services/storage/service.py`)
- **PDF Processing**: Marker PDF with LLM enhancement (`app/services/pdf_processor/processor.py`)
- **DOCX Conversion**: LibreOffice headless conversion (`app/workers/tasks/document.py`)
- **Chunking**: Chonkie semantic chunking (`app/services/pdf_processor/processor.py`)
- **Embeddings**: Gemini `gemini-embedding-001` (`app/services/embedding/service.py`)
- **LLM Framework**: DSPy (`app/services/rag/dspy_rag.py`, `adaptive_rag.py`, `multihop_rag.py`)
- **LLM Provider**: Gemini (`app/services/rag/service.py`)
- **Reranking**: Sentence Transformers cross-encoder (`app/services/reranker.py`)
- **Caching**: Gemini cached content + Redis manifest registry (`app/services/rag/gemini_cache.py`, `cache_registry.py`)
- **Deployment**: Docker Compose with API, worker, Redis, and Flower (`docker-compose.yml`)

### Notebook Scope Is a Core Design Constraint

Every document chunk belongs to both a `user_id` and a `notebook_id`. Retrieval requires a notebook scope:

```python
scope_token = self.retrieval_service.set_notebook_scope(notebook_id)
try:
    prediction = self.rag(question=question, doc_names=effective_doc_names)
finally:
    self.retrieval_service.reset_notebook_scope(scope_token)
```

This prevents accidental cross-notebook retrieval and lets each notebook behave like its own small RAG workspace.

---

## Step 1: Document Ingestion & Chunking

### Overview

DATN transforms uploaded PDF or DOCX files into semantically meaningful, page-aware chunks. Upload is intentionally worker-only for the notebook API.

### 1.1 Authenticated Upload

**File**: `app/routers/notebooks.py`

```python
@router.post("/{notebook_id}/documents/upload", response_model=DocumentUploadResponse)
async def upload_document(
    notebook_id: str,
    file: UploadFile = File(...),
    current_user: CurrentUser = Depends(get_current_user),
    service: NotebookWorkspaceService = Depends(get_workspace_service),
) -> DocumentUploadResponse:
    content = await file.read()
    result = service.upload_document(current_user.id, notebook_id, content, file.filename)
```

The route:

- Requires a Supabase bearer token.
- Reads the uploaded file.
- Delegates all workspace checks and queueing to `NotebookWorkspaceService`.

### 1.2 Worker-Only Queueing

**File**: `app/services/notebooks.py`

```python
if settings.document_processing_mode.strip().lower() != "worker":
    raise NotebookValidationError(
        "Document upload requires worker mode. Set DOCUMENT_PROCESSING_MODE=worker "
        "and run the Celery worker."
    )

task_id = str(uuid4())
upload_dir = Path(settings.uploads_dir) / user_id / notebook_id
file_path = upload_dir / safe_document_storage_path(document_name, source_extension)
file_path.write_bytes(file_content)

status_repo.create_status(
    notebook_id=notebook_id,
    user_id=user_id,
    document_name=document_name,
    task_id=task_id,
)

self._celery_app(settings.redis_url).send_task(
    "app.workers.tasks.document.process_document_task",
    args=[notebook_id, user_id, document_name, str(file_path)],
    queue="document_processing",
    task_id=task_id,
)
```

Important behavior:

- Source names are normalized from the client filename.
- The first upload can auto-title an untitled notebook.
- Existing Gemini caches for that source are invalidated before queueing.
- The uploaded file is stored under `UPLOADS_DIR/user_id/notebook_id`.
- The API returns immediately with `queued: true`.

### 1.3 PDF and DOCX Support

**File**: `app/workers/tasks/document.py`

```python
def _ensure_pdf_for_processing(file_path: str, document_name: str) -> str:
    if file_path.startswith("http"):
        return file_path

    source_path = Path(file_path)
    suffix = source_path.suffix.lower()
    if suffix == ".pdf":
        return file_path
    if suffix == ".docx":
        return str(_convert_docx_to_pdf(source_path, document_name))

    raise ValueError("Only PDF and DOCX files are supported")
```

DOCX conversion uses LibreOffice:

```python
subprocess.run(
    [
        "soffice",
        "--headless",
        "--convert-to",
        "pdf:writer_pdf_Export",
        "--outdir",
        str(temp_output_path),
        str(source_path),
    ],
    timeout=180,
)
```

The worker image installs `libreoffice-writer`; local worker environments must provide `soffice` themselves.

### 1.4 Worker Orchestration

**File**: `app/workers/tasks/document.py`

```python
@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
@circuit_breaker("pdf_processing", failure_threshold=5, timeout=300)
def process_document_task(self, notebook_id: str, user_id: str, document_name: str, file_path: str):
    with distributed_lock(f"document:{notebook_id}:{document_name}", timeout=3600):
        status_repo.create_status(...)
        status_repo.update_status(notebook_id, document_name, ProcessingStatus.PROCESSING)
        file_path = _ensure_pdf_for_processing(file_path, document_name)
        storage_service.upload_pdf(file_path, destination_path=f"{user_id}/{notebook_id}/{safe_pdf_storage_path(document_name)}")
        extract_and_chunk_task.apply_async(...)
```

Reliability layers:

- Distributed lock prevents duplicate processing of the same notebook/source.
- Circuit breaker protects repeated PDF processing failures.
- Status table tracks `pending`, `processing`, `completed`, and `failed`.
- Supabase Storage receives the generated or uploaded PDF.

### 1.5 Marker PDF Extraction

**File**: `app/services/pdf_processor/processor.py`

```python
config = {
    "output_format": "markdown",
    "use_llm": pdf_config.use_llm or describe_images,
    "llm_model": pdf_config.llm_model,
    "gemini_model_name": caption_model,
    "gemini_api_key": settings.google_api_key,
    "extract_tables": True,
    "paginate_output": True,
}
if describe_images:
    config["extract_images"] = True
```

Marker produces markdown and metadata. DATN config enables:

- Markdown output.
- Table extraction.
- Pagination markers.
- Gemini-assisted extraction.
- Optional image extraction for visual captions.

### 1.6 Visual Description Normalization

DATN stores image and figure content as searchable text when possible.

Marker may emit lines such as:

```text
Image /page/0/Picture/1 description: ...
```

DATN normalizes them:

```text
Image description on page 1: ...
```

When Marker leaves markdown image placeholders, DATN attempts a Gemini vision fallback:

```python
markdown = self._replace_image_placeholders_with_captions(markdown, images, file_path)
```

Caption generation includes quality checks:

- Captions must end with `[VISUAL_DESCRIPTION_COMPLETE]`.
- Empty captions are rejected.
- Captions ending mid-phrase are rejected.
- Failed captions produce diagnostic text instead of silently storing useless markdown image syntax.

### 1.7 Semantic Chunking

**File**: `app/services/pdf_processor/processor.py`

```python
self.chunker = SemanticChunker(
    embedding_function=self.embedding_service.embed_text,
    chunk_size=chunking_config.chunk_size,
    threshold=chunking_config.similarity_threshold,
    min_sentences_per_chunk=3,
    min_characters_per_sentence=30,
)
```

DATN uses the same embedding service for semantic chunking and final vector generation. The configured defaults are:

```yaml
chunking:
  strategy: "semantic"
  chunk_size: 512
  similarity_threshold: 0.5
```

### 1.8 Table Protection

Markdown tables are protected before chunking and restored afterward:

```python
protected_text, table_markers = self._protect_tables(text)
chunks_result = self.chunker.chunk(protected_text)
chunk_text = self._restore_tables(chunk.text, table_markers)
```

This avoids splitting table rows across unrelated chunks.

### 1.9 Page Tracking

Marker pagination is used when available:

```python
PAGE_MARKER_PATTERN = re.compile(r"(?:^|\n)\s*\{(?P<page>\d+)\}-{3,}\s*(?=\n|$)")
```

If Marker page boundaries are missing, DATN falls back to:

- Recognizing `Page N` lines or separator-like markers.
- Distributing text across `metadata["total_pages"]` when needed.

Each chunk includes:

```python
{
    "text": "...",
    "chunk_id": 0,
    "start_index": 123,
    "end_index": 987,
    "token_count": 512,
    "pages": [3, 4],
    "page_range": "3-4",
    "has_table": False,
    "has_visual": True,
    "visual_pages": [4],
    "content_type": "mixed",
}
```

### Key Takeaways

- Upload is asynchronous and worker-only.
- DOCX support is implemented through LibreOffice conversion.
- Marker handles LLM-enhanced PDF extraction.
- Gemini can textualize visuals for search.
- Semantic chunks keep page ranges, table metadata, and visual metadata.

---

## Step 2: Embedding Generation

### Overview

DATN converts chunks into Gemini embeddings and stores them in Supabase.

### 2.1 Embedding Service

**File**: `app/services/embedding/service.py`

The service uses `GOOGLE_API_KEY` and the configured Gemini embedding model:

```yaml
llm:
  gemini:
    embedding_model: "gemini-embedding-001"
```

The vector database is configured for 3072 dimensions:

```yaml
vector_db:
  embedding_dimension: 3072
  similarity_metric: "cosine"
```

### 2.2 Fan-Out Embedding Tasks

**File**: `app/workers/tasks/document.py`

After extraction and chunking, the worker creates one embedding task per chunk:

```python
embedding_tasks = group(
    generate_embedding_and_store_task.s(
        document_name=document_name,
        notebook_id=notebook_id,
        user_id=user_id,
        chunk_data=chunk,
    )
    for chunk in chunks
)

workflow = chord(embedding_tasks)(
    finalize_document_task.s(
        document_name=document_name,
        notebook_id=notebook_id,
        total_chunks=len(chunks),
    )
)
```

This is a Celery fan-out/fan-in pattern:

```text
extract_and_chunk_task
  -> embedding task for chunk 0
  -> embedding task for chunk 1
  -> embedding task for chunk N
  -> finalize_document_task after all embedding tasks return
```

### 2.3 Rate Limiting and Circuit Breaker

**File**: `app/workers/tasks/embedding.py`

```python
@celery_app.task(bind=True, max_retries=5, default_retry_delay=30)
@circuit_breaker("gemini_embedding", failure_threshold=10, timeout=120)
def generate_embedding_and_store_task(...):
    rate_limiter = get_rate_limiter("gemini_embedding")
    acquired = rate_limiter.acquire(tokens=1, blocking=True, timeout=60)
```

The embedding task:

- Waits for a Redis token-bucket rate limit token.
- Retries when the limit is exceeded.
- Opens a circuit after repeated Gemini embedding failures.
- Stores each successful chunk immediately.

### 2.4 Stored Embedding Metadata

Each chunk stores:

```python
metadata={
    "start_index": chunk_data["start_index"],
    "end_index": chunk_data["end_index"],
    "token_count": chunk_data["token_count"],
    "has_table": chunk_data.get("has_table", False),
    "has_visual": chunk_data.get("has_visual", False),
    "visual_pages": chunk_data.get("visual_pages", []),
    "content_type": chunk_data.get("content_type", "text"),
}
```

This metadata is later returned in source citations.

### Key Takeaways

- DATN uses Gemini 3072-dimensional embeddings.
- Embedding work is parallelized with Celery.
- Redis rate limiting and circuit breaking protect Gemini calls.
- Chunk metadata preserves enough information for citation display and debugging.

---

## Step 3: Vector Storage

### Overview

DATN stores chunks in Supabase PostgreSQL with pgvector. The current migration upgrades embeddings to `halfvec(3072)` and indexes them with HNSW.

### 3.1 Documents Table

**File**: `supabase/migrations/002_notebook_rag_integration.sql`

```sql
ALTER TABLE public.documents
    ALTER COLUMN embedding TYPE halfvec(3072) USING embedding::halfvec(3072);

ALTER TABLE public.documents
    ADD COLUMN IF NOT EXISTS pages INTEGER[],
    ADD COLUMN IF NOT EXISTS page_range TEXT;
```

Effective table shape:

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
```

### 3.2 Why `halfvec`

`halfvec(3072)` stores half-precision vectors. It reduces memory and index size compared with full 32-bit vectors while preserving enough precision for semantic retrieval.

### 3.3 HNSW Index

```sql
CREATE INDEX IF NOT EXISTS documents_embedding_idx
ON public.documents USING hnsw (embedding halfvec_cosine_ops);
```

HNSW provides fast approximate nearest-neighbor search without needing a separate vector database.

### 3.4 Notebook and Source Indexes

```sql
CREATE INDEX IF NOT EXISTS documents_notebook_document_idx
ON public.documents(notebook_id, document_name);

CREATE INDEX IF NOT EXISTS documents_user_id_idx
ON public.documents(user_id);
```

These indexes support notebook-scoped queries, source filtering, and deletion/rename workflows.

### 3.5 Match Function

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
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
    RETURN QUERY
    SELECT
        d.id,
        d.document_name,
        d.chunk_id,
        d.content,
        d.metadata,
        d.pages,
        d.page_range,
        1 - (d.embedding <=> query_embedding) AS similarity
    FROM public.documents d
    WHERE d.notebook_id = target_notebook_id
      AND (filter_document IS NULL OR d.document_name = filter_document)
    ORDER BY d.embedding <=> query_embedding
    LIMIT match_count;
END;
$$;
```

The function is only granted to `service_role`. Backend routes use the service-role client; browser clients should not query vector tables directly.

### 3.6 Repository Usage

**File**: `app/db/repository.py`

```python
result = self.client.rpc("match_documents", {
    "query_embedding": query_embedding,
    "target_notebook_id": notebook_id,
    "match_count": limit,
    "filter_document": doc,
}).execute()
```

For `doc_names`, DATN calls the RPC per selected document and combines the results.

### Key Takeaways

- Every vector row is scoped by `notebook_id` and `user_id`.
- Supabase stores both chunks and embeddings.
- `match_documents` performs cosine similarity through pgvector.
- HNSW and notebook/document indexes are required for performance.

---

## Step 4: Retrieval

### Overview

DATN retrieval is implemented in `RetrievalService`. It supports selected-document retrieval, all-document notebook retrieval, and optional reranking.

### 4.1 Query Embedding

**File**: `app/services/rag/retrieval.py`

```python
notebook_id = self._require_notebook_id()
query_embedding = self.embedding_service.embed_text(query)
```

Retrieval fails if a notebook scope was not set by `RAGService`.

### 4.2 Selected-Document Retrieval

If `document_names` are provided by the frontend, retrieval searches those documents only:

```python
results = self.doc_repo.search_similar(
    query_embedding=query_embedding,
    notebook_id=notebook_id,
    limit=limit,
    document_name=document_name,
    doc_names=doc_names,
)
```

Reranking is used only when multiple selected documents are involved:

```python
should_rerank = (
    self.use_reranking and
    doc_names is not None and
    len(doc_names) > 1
)
```

Single-source queries skip reranking because the scope is already focused.

### 4.3 All-Document Notebook Retrieval

When no document filter is passed, DATN uses a two-stage retrieval strategy:

```text
Stage 1: Quick scan
  - list all documents in the notebook
  - retrieve 1-2 top chunks per document
  - rank documents by best chunk similarity
  - keep top N documents

Stage 2: Deep search
  - retrieve more chunks from top documents
  - combine candidates

Stage 3: Rerank
  - rerank candidates with cross-encoder if available
  - return top_k chunks
```

Configured defaults:

```yaml
rag:
  retrieval:
    top_k: 10
    initial_chunks_per_doc: 2
    top_n_documents: 5
    deep_chunks_per_doc: 8
    use_reranking: true
```

### 4.4 Context Formatting

Retrieved chunks are formatted with source numbers:

```python
source_header = f"[Source {i}] Document: {document_name}, Pages: {page_range}"
if has_visual:
    source_header += f"\nContent type: {content_type} extracted from image/figure descriptions"
```

The LLM is instructed to cite these sources with `[N]`.

### 4.5 Source Formatting for API Responses

**File**: `app/services/rag/service.py`

```python
source = {
    "content": chunk.get("content", ""),
    "document": chunk.get("document_name", ""),
    "pages": chunk.get("pages", []),
    "page_range": chunk.get("page_range", "unknown"),
    "metadata": metadata,
    "content_type": metadata.get("content_type", "text"),
    "has_visual": bool(metadata.get("has_visual", False)),
    "image_url": metadata.get("image_url"),
}
```

`chunk_id` and `similarity` are included when valid.

### Key Takeaways

- Retrieval is always notebook-scoped.
- Selected document queries search only selected completed sources.
- All-document retrieval uses a two-stage search to avoid reranking too many chunks.
- Context headers drive frontend-friendly citations.

---

## Step 5: Reranking

### Overview

DATN uses a cross-encoder reranker for better relevance ranking across multiple candidate chunks.

### 5.1 Reranker Service

**File**: `app/services/reranker.py`

```python
self.model = CrossEncoder(model_name, device=device)
```

Default model:

```yaml
rag:
  reranking:
    model: "BAAI/bge-reranker-v2-m3"
    enabled: true
```

### 5.2 Lazy Initialization

**File**: `app/services/rag/retrieval.py`

```python
if self.reranker is None:
    self.reranker = RerankerService(model_name=self.reranker_model, force_cpu=True)
```

DATN loads the reranker only when a query actually needs reranking. It forces CPU mode in retrieval to avoid GPU contention with PDF workers.

### 5.3 Cross-Encoder Scoring

```python
pairs = [
    (query, chunk.get("content", "")[:max_content_length])
    for chunk in chunks
]

batch_scores = self.model.predict(batch_pairs, convert_to_tensor=True)
```

The reranker sees the query and chunk together, which is more precise than comparing independent embeddings.

### 5.4 OOM Fallback

If GPU memory errors occur when not forced to CPU, the service can fall back to CPU for that batch:

```python
if "out of memory" in str(e).lower():
    self.model.device = "cpu"
    self.model.model.to("cpu")
    batch_scores = self.model.predict(batch_pairs, convert_to_tensor=False)
```

### Key Takeaways

- Reranking is mainly for multi-document relevance.
- It is lazy-loaded to keep simple requests faster.
- DATN defaults to CPU reranking for predictable worker/API coexistence.
- Content is truncated before reranking for speed and memory safety.

---

## Step 6: Answer Generation

### Overview

DATN uses DSPy modules for structured answer generation. The active mode is configured in `config.yaml`.

```yaml
rag:
  mode: "adaptive"
```

### 6.1 RAG Service Initialization

**File**: `app/services/rag/service.py`

```python
lm = dspy.LM(
    model=f"gemini/{self.app_config.llm.gemini.model}",
    api_key=self.settings.google_api_key,
    temperature=self.app_config.llm.gemini.temperature,
    max_tokens=self.app_config.llm.gemini.max_tokens,
)
dspy.settings.configure(lm=lm, adapter=dspy.ChatAdapter())
```

Then the service selects a RAG module:

- `adaptive` -> `AdaptiveRAG`
- `multi-hop` -> `MultiHopRAG`
- `single-hop` -> `RAGModule` or explicitly configured optimized DSPy model

### 6.2 Single-Hop RAG

**File**: `app/services/rag/dspy_rag.py`

```python
chunks = self.retrieval_service.retrieve(
    query=question,
    doc_names=doc_names,
)

context = self.retrieval_service.format_context(chunks[:self.num_passages])
prediction = self.generate_answer(context=context, question=question)
prediction.chunks = chunks[:self.num_passages]
```

The answer signature asks for:

- Clear paragraphs.
- `**bold**` for key terms.
- Citations only in `[N]` format.
- Markdown tables when relevant.
- Image/figure descriptions treated as document evidence.

### 6.3 Multi-Hop RAG

**File**: `app/services/rag/multihop_rag.py`

```python
for hop in range(max_hops):
    if hop == 0:
        search_query = question
    else:
        query_pred = self.generate_query(context=current_context, question=question)
        search_query = query_pred.query

    chunks = self.retrieval_service.retrieve(query=search_query, doc_names=doc_names)[:self.passages_per_hop]
```

Multi-hop performs iterative retrieval, then generates a final answer from all gathered chunks.

When `doc_names` are provided, DATN reduces max hops:

```python
max_hops = 2 if doc_names else self.max_hops
```

### 6.4 Adaptive RAG

**File**: `app/services/rag/adaptive_rag.py`

For one or two selected documents, adaptive RAG skips the complexity assessor:

```python
if doc_names is not None and len(doc_names) <= 2:
    prediction = self.single_hop(question=question, doc_names=doc_names)
    prediction.strategy = "single-hop"
    prediction.strategy_reasoning = "Using single-hop for document-filtered query (focused scope)"
```

Otherwise, DSPy assesses complexity:

```python
assessment = self.assess_complexity(question=question)

if assessment.complexity == "complex":
    prediction = self.multi_hop(question=question, doc_names=doc_names)
else:
    prediction = self.single_hop(question=question, doc_names=doc_names)
```

### 6.5 Persisted Chat

**File**: `app/services/notebooks.py`

Non-streaming chat:

```python
result = get_rag_service().query(
    question=message.strip(),
    notebook_id=notebook_id,
    doc_names=selected_documents,
)

self._insert_message(session_id, "user", message.strip(), [])
self._insert_message(session_id, "assistant", answer, sources)
```

DATN validates selected documents before RAG:

```python
if missing:
    raise NotebookValidationError(f"These documents are not ready for chat: {', '.join(missing)}")
```

### 6.6 Fallback Citations

If an answer returns sources but no `[N]` citation markers, DATN appends fallback source markers:

```python
if not sources or CITATION_PATTERN.search(answer):
    return answer

citations = " ".join(f"[{index}]" for index in range(1, citation_count + 1))
return f"{answer.rstrip()}\n\nSource: {citations}"
```

This protects frontend source display when generation omitted citation syntax.

### Key Takeaways

- DSPy structures prompts and predictions.
- Adaptive mode chooses single-hop or multi-hop.
- Selected-document queries are intentionally biased toward single-hop.
- Chat messages are persisted after successful answer generation.

---

## Step 7: Streaming & Cached Context

### Overview

DATN supports streaming chat via `POST /notebooks/{notebook_id}/chat/messages/stream`. The stream returns NDJSON events and persists the assistant message after generation finishes.

### 7.1 Streaming Route

**File**: `app/routers/notebooks.py`

```python
@router.post("/{notebook_id}/chat/messages/stream")
async def send_chat_message_stream(...):
    prepared = service.begin_chat_message(...)

    async for chunk in rag_service.query_stream(...):
        if chunk.get("type") == "token":
            yield {"type": "token", "content": content}
        elif chunk.get("type") == "metadata":
            yield {"type": "metadata", "sources": chunk.get("sources", [])}

    result = service.finalize_chat_message(...)
    yield {"type": "done", ...}
```

Event types:

- `token`: answer text fragment.
- `metadata`: strategy and source list.
- `done`: persisted session/messages.
- `error`: failure message.

### 7.2 Gemini Cached Context Fast Path

**File**: `app/services/rag/service.py`

For streaming queries over one to three selected documents, DATN first tries Gemini cached content:

```python
if effective_doc_names and len(effective_doc_names) <= 3:
    cache_key = build_document_cache_key(notebook_id, effective_doc_names)
    manifest_key = build_document_cache_manifest_key(notebook_id, effective_doc_names)
```

If no cache exists:

```python
chunks = await asyncio.to_thread(
    self.retrieval_service.doc_repo.get_all_chunks_by_names,
    effective_doc_names,
    notebook_id,
)

source_manifest = [self._format_source(chunk) for chunk in chunks]
cache_name = await asyncio.to_thread(
    self.cache_service.create_document_cache,
    cache_key,
    chunks,
    source_manifest,
    manifest_key,
    ttl_hours=1,
)
```

The cache is skipped when context is too small:

```python
if len(full_context) < 4000:
    return None
```

### 7.3 Source Manifest

Gemini cached content returns answer text with citations, but the backend must map `[N]` back to source chunks. DATN stores a Redis manifest alongside the Gemini cache name:

```python
set_cache_manifest(manifest_key, source_manifest, ttl_seconds)
```

The manifest contains ordered source metadata, including document name, chunk id, pages, page range, and content metadata.

### 7.4 Citation Resolution

Before a cached answer is accepted, citations must resolve to manifest entries:

```python
resolved = self._resolve_manifest_citations(cached_answer, source_manifest)
if not resolved:
    raise ValueError("Cached answer did not produce resolvable source citations.")
```

The resolver:

- Rejects answers with no citations.
- Rejects out-of-range citations.
- Compacts cited sources so returned sources match displayed `[N]`.

Example:

```text
Manifest has 10 sources.
Answer cites [2] and [7].
Returned sources become:
  [1] original source 2
  [2] original source 7
Answer citations are rewritten from [2], [7] to [1], [2].
```

### 7.5 Fresh Similarity Scores for Cached Sources

Cached source manifests do not have query-specific similarity scores. DATN refreshes them by embedding the current question and searching the cited chunks:

```python
query_embedding = await asyncio.to_thread(
    self.retrieval_service.embedding_service.embed_text,
    question,
)
```

If scores cannot be resolved, DATN falls back to DSPy RAG rather than returning unsafe metadata.

### 7.6 DSPy Streaming Fallback

If cache creation/use fails, DATN runs DSPy streaming in a worker thread with its own event loop:

```python
thread = threading.Thread(target=run_dspy_streaming, daemon=True)
thread.start()
```

If the DSPy/Gemini stack does not produce true streaming chunks, DATN simulates token streaming by splitting the final answer while preserving whitespace.

### Key Takeaways

- Streaming is NDJSON, not Server-Sent Events.
- Cached context is only used for small selected-source sets.
- Cached answers must have manifest-resolvable citations.
- Cache invalidation happens on upload, rename, and delete.
- DSPy remains the fallback path for correctness.

---

## Complete Pipeline Summary

### Upload and Indexing

```text
User uploads PDF/DOCX
  |
  v
POST /notebooks/{id}/documents/upload
  |
  v
NotebookWorkspaceService
  - validates notebook ownership
  - normalizes document name
  - invalidates document caches
  - writes file to UPLOADS_DIR
  - creates processing status
  - sends Celery task
  |
  v
process_document_task
  - distributed lock
  - status -> processing
  - DOCX -> PDF if needed
  - upload PDF to Supabase Storage
  |
  v
extract_and_chunk_task
  - Marker markdown extraction
  - visual caption fallback
  - semantic chunking
  - page/table/visual metadata
  - delete stale chunks
  |
  v
Celery group(generate_embedding_and_store_task)
  - rate-limited Gemini embeddings
  - insert chunks into documents table
  |
  v
finalize_document_task
  - status -> completed or failed
```

### Non-Streaming Question

```text
POST /notebooks/{id}/chat/messages
  |
  v
Validate selected documents are completed
  |
  v
RAGService.query
  - set notebook scope
  - adaptive/single/multi-hop DSPy
  - retrieve chunks
  - optional rerank
  - generate answer
  |
  v
Persist user and assistant messages
  |
  v
Return answer, sources, strategy
```

### Streaming Question

```text
POST /notebooks/{id}/chat/messages/stream
  |
  v
Persist user message
  |
  v
RAGService.query_stream
  |
  +-- cached path for <= 3 selected docs
  |     - fetch/create Gemini cache
  |     - load source manifest
  |     - generate answer
  |     - resolve citations
  |     - stream tokens
  |
  +-- DSPy fallback
        - adaptive RAG
        - stream or simulate tokens
  |
  v
Emit metadata
  |
  v
Persist assistant message
  |
  v
Emit done event
```

---

## Operational Notes

### Runtime Settings

`app/main.py` logs key settings at startup:

```text
document_processing_mode
worker_mode_active
require_worker_mode
redis_url
uploads_dir
```

The health endpoint returns the same worker-mode state:

```bash
curl http://localhost:8000/health
```

### Required Environment

```env
SUPABASE_URL=...
SUPABASE_ANON_KEY=...
SUPABASE_SERVICE_KEY=...
REDIS_URL=redis://localhost:6379/0
GOOGLE_API_KEY=...
DOCUMENT_PROCESSING_MODE=worker
DATN_REQUIRE_WORKER_MODE=true
UPLOADS_DIR=/app/uploads
```

### Celery Queues

`app/workers/celery_app.py` declares:

```python
task_routes={
    "app.workers.tasks.document.*": {"queue": "document_processing"},
    "app.workers.tasks.embedding.*": {"queue": "embedding"},
    "app.workers.tasks.storage.*": {"queue": "storage"},
}
```

Docker Compose currently runs the worker with:

```bash
celery -A app.workers.celery_app worker --loglevel=info --pool=solo --concurrency=1 -Q document_processing,embedding,storage
```

### Storage

The `pdfs` bucket is private and managed by service role. Migration `002_notebook_rag_integration.sql` configures:

```sql
INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
VALUES ('pdfs', 'pdfs', false, 52428800, ARRAY['application/pdf']::text[])
```

DATN stores generated/converted PDFs under:

```text
{user_id}/{notebook_id}/{safe-document-name}.pdf
```

### Cache Invalidation

Cache invalidation happens when:

- A source is uploaded/re-indexed.
- A source is renamed.
- A source is deleted.

Redis keys are notebook-scoped and document-name-aware:

```text
gemini_cache:{notebook_id}:docs:{docA|docB}
gemini_cache_manifest:{notebook_id}:docs:{docA|docB}
```

---

## Best Practices

### 1. Document Upload

Do:

- Keep upload processing in worker mode.
- Run API and worker against the same Redis and Supabase project.
- Poll processing status before enabling chat on a source.
- Keep LibreOffice installed wherever DOCX conversion runs.

Avoid:

- Calling legacy synchronous document processing from request paths.
- Chatting against `pending`, `processing`, or `failed` sources.
- Renaming sources while indexing is still in progress.

### 2. Chunking

Do:

- Preserve Marker pagination.
- Keep table protection enabled.
- Store visual descriptions as text when `describe_images` is enabled.
- Use `scripts/debug_chunking.py` before changing chunking config.

Avoid:

- Removing page metadata; citations depend on it.
- Storing raw image placeholders as the only representation of visual content.
- Making chunks so small that retrieval loses context.

### 3. Embedding

Do:

- Use the configured Gemini embedding model consistently.
- Keep vector dimension aligned with Supabase `halfvec(3072)`.
- Keep rate limiting and retries around Gemini calls.

Avoid:

- Changing embedding models without a migration/re-index plan.
- Mixing old 768-dimensional rows with 3072-dimensional rows.

### 4. Retrieval

Do:

- Always set notebook scope before retrieval.
- Pass selected `document_names` from the frontend when the user scopes a question.
- Use two-stage retrieval for all-document notebook queries.
- Rerank multi-document candidates when latency allows.

Avoid:

- Searching the global `documents` table without `notebook_id`.
- Returning cached answers unless citations resolve against the manifest.

### 5. Answer Generation

Do:

- Keep source headers in `[Source N]` format.
- Ask the model for `[N]` citations.
- Preserve markdown tables in generated answers.
- Treat image descriptions as extracted evidence.

Avoid:

- Letting generated source numbers drift from returned `sources`.
- Saving assistant messages before streaming completes.

### 6. Operations

Do:

- Use Flower or worker logs when diagnosing stuck indexing.
- Run unit tests after changing workspace, cache, or RAG citation behavior.
- Use service-role access only from the backend.

Avoid:

- Exposing vector RPC execution to anon clients.
- Keeping stale Redis cache entries after document mutations.

---

## Troubleshooting

### 1. Upload Returns Queued but Never Completes

Check:

```bash
docker compose logs -f worker
docker compose logs -f redis
```

Common causes:

- Worker is not running.
- Worker uses a different `REDIS_URL`.
- Supabase service key is missing or invalid.
- Marker or Gemini extraction failed.

### 2. DOCX Conversion Fails

The worker needs `soffice`.

Docker worker image:

```dockerfile
RUN apt-get update && apt-get install -y libreoffice-writer
```

Local workers must install LibreOffice manually.

### 3. RAG Says Source Is Not Ready

The selected document must have `status = completed` in `document_processing_status`.

Check:

```bash
curl "http://localhost:8000/notebooks/{notebook_id}/documents" \
  -H "Authorization: Bearer <token>"
```

### 4. Vector Search Fails

Confirm migration `002_notebook_rag_integration.sql` has been applied:

- `documents.embedding` is `halfvec(3072)`.
- `match_documents(halfvec, uuid, integer, text)` exists.
- Service role has execute permission.
- HNSW index exists.

### 5. Cached Streaming Falls Back

Expected fallback cases:

- Context is under 4000 characters.
- Cache manifest is missing.
- Manifest lacks chunk ids.
- Gemini answer has no citations.
- Gemini answer cites out-of-range source numbers.
- Fresh similarity scores cannot be attached.

### 6. First Multi-Document Query Is Slow

The cross-encoder reranker is lazy-loaded. First use can take several seconds.

### 7. Answers Lack Citations

DATN appends fallback citations when sources exist but no `[N]` markers appear. If this happens frequently, inspect:

- DSPy answer signature.
- Retrieved context headers.
- Whether `sources` are actually attached to the final prediction.

---

## Conclusion

DATN/backend implements a notebook-scoped RAG system rather than a single global document QA app. Its current design centers on:

- Authenticated user ownership through Supabase.
- Notebook-isolated source storage and retrieval.
- Worker-only PDF/DOCX indexing.
- Marker plus Gemini for structure, tables, and visuals.
- Chonkie semantic chunking with page-aware citations.
- Gemini embeddings stored in Supabase pgvector `halfvec(3072)`.
- Two-stage retrieval plus cross-encoder reranking.
- DSPy adaptive/single-hop/multi-hop answer generation.
- NDJSON streaming with Gemini cached-context acceleration.
- Redis-backed source manifests for safe cached citations.

For setup and endpoint usage, see `README.md`.

---

**Last updated**: May 2026
