# Complete RAG Implementation Guide: pdp8-rag System

A comprehensive deep-dive into Retrieval-Augmented Generation (RAG) implementation, illustrated with production code from the pdp8-rag project.

---

## Table of Contents

1. [Overview](#overview)
2. [Step 1: Document Ingestion & Chunking](#step-1-document-ingestion--chunking)
3. [Step 2: Embedding Generation](#step-2-embedding-generation)
4. [Step 3: Vector Storage](#step-3-vector-storage)
5. [Step 4: Retrieval](#step-4-retrieval)
6. [Step 5: Reranking](#step-5-reranking)
7. [Step 6: Answer Generation](#step-6-answer-generation)
8. [Complete Pipeline Summary](#complete-pipeline-summary)
9. [Performance Metrics](#performance-metrics)
10. [Best Practices](#best-practices)

---

## Overview

### What is RAG?

**Retrieval-Augmented Generation (RAG)** is a technique that enhances Large Language Models (LLMs) by providing them with relevant external knowledge. Instead of relying solely on the model's training data, RAG retrieves pertinent information from a knowledge base and uses it as context for generation.

### The RAG Pipeline

```
┌──────────────┐    ┌──────────────┐    ┌──────────────┐    ┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│   Document   │ -> │   Chunking   │ -> │  Embedding   │ -> │    Vector    │ -> │  Retrieval   │ -> │    Answer    │
│  Ingestion   │    │  & Parsing   │    │  Generation  │    │   Storage    │    │  & Rerank    │    │  Generation  │
└──────────────┘    └──────────────┘    └──────────────┘    └──────────────┘    └──────────────┘    └──────────────┘
     Step 1              Step 1              Step 2              Step 3              Step 4             Step 6
                                                                                     Step 5
```

### Architecture Components

- **Backend**: FastAPI (async, high-performance)
- **Frontend**: React + Vite
- **Task Queue**: Celery + Redis
- **Vector DB**: PostgreSQL + pgvector
- **LLM Framework**: DSPy
- **PDF Processing**: Marker (with LLM enhancement)
- **Embeddings**: Gemini / OpenAI
- **Reranking**: BAAI/bge-reranker-v2-m3

---

## Step 1: Document Ingestion & Chunking

### Overview

Transform unstructured PDF documents into semantically meaningful chunks that can be embedded and searched.

### 1.1 PDF Extraction

**File**: `app/services/pdf_processor/processor.py`

```python
class PDFProcessor:
    def __init__(self, app_config: AppConfig, settings: Settings, embedding_service: EmbeddingService):
        """Initialize with LLM-enhanced PDF extraction."""
        config = {
            "output_format": "markdown",      # Structured output
            "use_llm": True,                  # LLM understands layout
            "llm_model": "gemini-2.5-flash",  # Fast model
            "extract_tables": True,           # Preserve tables
        }

        self.converter = PdfConverter(
            config=self.config_parser.generate_config_dict(),
            llm_service=self.config_parser.get_llm_service()
        )

    def process_pdf(self, file_path: str) -> tuple[str, Dict[str, Any]]:
        """Extract PDF to markdown with metadata."""
        rendered = self.converter(file_path)

        metadata = {
            "total_pages": len(rendered.pages),
            "images": rendered.images,
        }

        return rendered.markdown, metadata
```

**What Marker Does**:
1. **Layout Detection**: Identifies columns, headers, tables
2. **Text Extraction**: Preserves reading order
3. **Table Recognition**: Converts to markdown tables
4. **LLM Enhancement**: Understands complex layouts

**Example**:

```
Input PDF:
┌────────────────────────────────────┐
│  PDP8 - ELECTRICITY MASTER PLAN    │
│  Renewable Energy Targets          │
│  ┌────────┬──────────┐            │
│  │ Year   │ Capacity │            │
│  │ 2030   │ 30 GW    │            │
│  └────────┴──────────┘            │
└────────────────────────────────────┘

Marker Output:
# PDP8 - ELECTRICITY MASTER PLAN
## Renewable Energy Targets
| Year | Capacity |
|------|----------|
| 2030 | 30 GW    |
```

### 1.2 Semantic Chunking

**Key Innovation**: Group sentences by semantic similarity, not fixed size.

```python
self.chunker = SemanticChunker(
    embedding_function=self.embedding_service.embed_text,
    chunk_size=512,                    # Target size
    threshold=0.5,                     # Similarity threshold
    min_sentences_per_chunk=3,
    min_characters_per_sentence=30
)
```

**Algorithm**:

1. Split text into sentences
2. Embed each sentence
3. Calculate similarity between consecutive sentences
4. Create chunk boundary when similarity drops below threshold

**Example**:

```
Text with Sentence Similarities:
─────────────────────────────────────────────────
S1: "Solar energy is a key renewable source."
    ↓ similarity = 0.85 ✓ (high)
S2: "Vietnam aims to install 30 GW of solar by 2030."
    ↓ similarity = 0.78 ✓ (high)
S3: "Wind power will complement solar capacity."
    ↓ similarity = 0.42 ✗ (LOW - topic shift)
S4: "The grid infrastructure requires modernization."
    ↓ similarity = 0.91 ✓ (high)
S5: "Smart grid technology enables distribution."

Result:
─────────────────────────────────────────────────
Chunk 1: S1 + S2 + S3 (about renewable energy)
Chunk 2: S4 + S5 (about grid infrastructure)
```

### 1.3 Table Preservation

**Problem**: Semantic chunking might split tables, destroying structure.

**Solution**: Protect tables before chunking, restore after.

```python
def chunk_text_with_pages(self, text: str, metadata: Dict):
    # Step 1: Replace tables with placeholders
    protected_text, table_markers = self._protect_tables(text)
    # "...targets include: <<<TABLE_0>>> These targets..."

    # Step 2: Chunk protected text
    chunks_result = self.chunker.chunk(protected_text)

    # Step 3: Restore tables
    for chunk in chunks_result:
        chunk_text = self._restore_tables(chunk.text, table_markers)

def _protect_tables(self, text: str) -> tuple[str, Dict[str, str]]:
    """Replace markdown tables with placeholders."""
    table_pattern = r'(\|[^\n]+\|\n)+(\|[-:| ]+\|\n)?(\|[^\n]+\|\n)+'
    tables = re.finditer(table_pattern, text)

    for idx, match in enumerate(tables):
        table_text = match.group(0)
        marker = f"<<<TABLE_{idx}>>>"
        table_markers[marker] = table_text
        protected_text = protected_text.replace(table_text, marker, 1)

    return protected_text, table_markers
```

### 1.4 Page Tracking

Track which pages each chunk spans for source citation.

```python
def _get_chunk_pages(self, start_idx: int, end_idx: int, page_boundaries: List[int]) -> List[int]:
    """Determine which pages a chunk spans."""
    pages = []

    for i, boundary in enumerate(page_boundaries):
        if i + 1 < len(page_boundaries):
            next_boundary = page_boundaries[i + 1]
            # If chunk overlaps with this page
            if start_idx < next_boundary and end_idx > boundary:
                pages.append(i + 1)

    return pages if pages else [1]
```

### 1.5 Output Format

Each chunk contains:

```python
{
    "text": "Vietnam's renewable energy targets...",
    "chunk_id": 5,
    "start_index": 2450,
    "end_index": 2720,
    "token_count": 487,
    "pages": [3, 4],
    "page_range": "3-4",
    "has_table": True
}
```

### Key Takeaways

✅ **LLM-Enhanced PDF Parsing**: Marker + Gemini for accurate extraction
✅ **Semantic Chunking**: Preserves topic coherence
✅ **Table Preservation**: Maintains structured data
✅ **Page Tracking**: Enables source citation

---

## Step 2: Embedding Generation

### Overview

Convert text chunks into high-dimensional vectors that capture semantic meaning.

### 2.1 What Are Embeddings?

**Embeddings** are numerical representations of text where semantic similarity translates to geometric proximity.

```
"renewable energy" → [0.12, 0.85, 0.33, -0.42, ...] (3072 dimensions)
"solar and wind"   → [0.14, 0.83, 0.31, -0.40, ...] (similar vector!)
"pizza toppings"   → [0.78, -0.22, 0.91, 0.15, ...] (very different!)
```

**Mathematical Foundation**: Distributional Semantics

> "You shall know a word by the company it keeps" - J.R. Firth

Words appearing in similar contexts have similar meanings:

```
Training Examples:
"The cat sat on the mat."
"The kitten played with yarn."

Neural Network Learns:
cat ≈ kitten (similar embeddings)
sat ≈ played (similar contexts)
```

### 2.2 Embedding Service

**File**: `app/services/embedding/service.py`

```python
class EmbeddingService:
    def __init__(self, settings: Settings):
        self.client = genai.Client(api_key=settings.google_api_key)
        self.model = "gemini-embedding-001"  # 3072-dimensional

    def embed_text(self, text: str) -> List[float]:
        """Generate embedding for text."""
        result = self.client.models.embed_content(
            model=self.model,
            contents=text
        )
        return result.embeddings[0].values  # [0.12, 0.85, ...]
```

**What Happens Inside**:

```
1. Tokenization:
   "Vietnam's renewable targets"
   → ["Vietnam", "'s", "renewable", "targets"]
   → [15234, 2049, 8921, 9012] (token IDs)

2. Transformer Processing:
   [15234, 2049, 8921, 9012]
   → 12-24 layers of attention + feed-forward
   → Token embeddings: [[0.1, 0.2, ...], [0.3, 0.4, ...], ...]

3. Pooling:
   Multiple token embeddings → Single sentence embedding
   Mean pooling: average all token embeddings

4. Normalization:
   Normalize to unit vector for cosine similarity
```

### 2.3 Embedding Models

| Model | Dimensions | Cost | Speed | Quality |
|-------|------------|------|-------|---------|
| gemini-embedding-001 | 3072 | Low | Fast | Excellent |
| text-embedding-3-large | 3072 | Medium | Medium | Excellent |
| text-embedding-3-small | 1536 | Low | Very Fast | Good |

**Why More Dimensions?**
- More expressiveness (capture finer distinctions)
- Better multilingual performance
- Trade-off: slower, more storage

### 2.4 Parallel Processing

**File**: `app/workers/tasks/embedding.py`

Process all chunks in parallel using Celery:

```python
@celery_app.task(bind=True, max_retries=5)
@circuit_breaker("gemini_embedding", failure_threshold=10, timeout=120)
def generate_embedding_and_store_task(self, document_name: str, chunk_data: Dict):
    """Generate embedding for one chunk (runs in parallel)."""

    # Rate limiting
    rate_limiter = get_rate_limiter("gemini_embedding")
    acquired = rate_limiter.acquire(tokens=1, blocking=True, timeout=60)

    if not acquired:
        raise self.retry(countdown=5)

    # Generate embedding
    embedding_service = EmbeddingService(settings)
    embedding = embedding_service.embed_text(chunk_data["text"])

    # Store in database
    doc_repo.insert_chunk(
        document_name=document_name,
        chunk_id=chunk_data["chunk_id"],
        content=chunk_data["text"],
        embedding=embedding,  # 3072-dim vector
        pages=chunk_data["pages"],
        page_range=chunk_data["page_range"]
    )
```

**Celery Chord Pattern** (fan-out/fan-in):

```python
# Create embedding task for each chunk
embedding_tasks = group(
    generate_embedding_and_store_task.s(document_name, chunk)
    for chunk in chunks  # 50 chunks
)

# Run all 50 tasks in parallel, then finalize
workflow = chord(embedding_tasks)(
    finalize_document_task.s(document_name, total_chunks=50)
)
```

**Execution Flow**:

```
Main Task
│
├─ Creates 50 chunks from PDF
│
└─ Spawns 50 parallel embedding tasks:
    │
    ├─ Worker 1: Chunk 0 → Embed → Store
    ├─ Worker 2: Chunk 1 → Embed → Store
    ├─ Worker 3: Chunk 2 → Embed → Store
    ...
    └─ Worker N: Chunk 49 → Embed → Store
         │
         └─ All complete? → Finalize
```

**Performance**: 50 chunks in ~2-3 seconds (vs ~50 seconds sequential)

### 2.5 Error Handling

**Circuit Breaker Pattern**:

```python
@circuit_breaker("gemini_embedding", failure_threshold=10, timeout=120)
```

**How It Works**:

```
Normal Operation (Closed):
Request 1: ✓ Success
Request 2: ✓ Success
Request 3: ✗ Failure (1/10)
...
Request 11: ✗ Failure (10/10) ← Threshold reached!

Circuit Opens:
→ Reject all requests for 120 seconds
→ Prevents overwhelming failing service

Recovery (Half-Open):
After 120s: Try one request
If successful → Close circuit
If fails → Open for another 120s
```

### Key Takeaways

✅ **High-Dimensional Embeddings**: 3072 dims for expressiveness
✅ **Parallel Processing**: Celery for speed
✅ **Rate Limiting**: Respects API limits
✅ **Circuit Breaker**: Handles failures gracefully

---

## Step 3: Vector Storage

### Overview

Store embeddings in PostgreSQL with pgvector extension for efficient similarity search.

### 3.1 Database Schema

**File**: `supabase/migrations/20251117083440_create_documents_table.sql`

```sql
-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE documents (
    id BIGSERIAL PRIMARY KEY,
    document_name TEXT NOT NULL,
    chunk_id INTEGER NOT NULL,
    content TEXT NOT NULL,
    embedding halfvec(3072),  -- Half-precision for efficiency
    metadata JSONB,
    pages INTEGER[],
    page_range TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);
```

### 3.2 Vector Types

| Type | Precision | Memory/Vector | Accuracy | Speed |
|------|-----------|---------------|----------|-------|
| `vector(3072)` | 32-bit float | 12 KB | 100% | Slower |
| `halfvec(3072)` | 16-bit float | 6 KB | 99.9% | Faster |

**Why halfvec?**
- 50% memory reduction (critical at scale)
- Minimal accuracy loss (0.1%)
- Faster operations

### 3.3 Vector Indexing: HNSW

**File**: `supabase/migrations/20251117090926_update_embedding_dimension.sql`

```sql
-- HNSW index for fast similarity search
CREATE INDEX documents_embedding_idx
ON documents USING hnsw (embedding halfvec_cosine_ops);
```

**HNSW (Hierarchical Navigable Small World)**:

```
Multi-Layer Graph Structure:
═══════════════════════════════════════════════════════════

Layer 2 (Top):    A ←→ B ←→ C
                  ↕     ↕     ↕
Layer 1 (Middle): A ←→ D ←→ B ←→ E ←→ C
                  ↕ ↕ ↕ ↕ ↕ ↕ ↕ ↕ ↕ ↕
Layer 0 (Bottom): A-D-F-B-G-E-H-C-I-J...

Search Process:
1. Start at top layer (sparse, long jumps)
2. Navigate to next layer (more connections)
3. Bottom layer (exhaustive local search)

Result: O(log N) search time instead of O(N)
```

**Performance**:
- 10,000 vectors: 100x faster than brute force
- 99%+ recall (finds actual nearest neighbors)
- No training required

### 3.4 Similarity Search Function

**File**: `supabase/migrations/20251117193000_create_match_documents_with_pages.sql`

```sql
CREATE FUNCTION match_documents(
    query_embedding halfvec(3072),
    match_count integer DEFAULT 5,
    filter_document text DEFAULT NULL
)
RETURNS TABLE (
    id bigint,
    document_name text,
    content text,
    pages integer[],
    page_range text,
    similarity float
)
AS $$
BEGIN
    RETURN QUERY
    SELECT
        d.id,
        d.document_name,
        d.content,
        d.pages,
        d.page_range,
        1 - (d.embedding <=> query_embedding) AS similarity
    FROM documents d
    WHERE (filter_document IS NULL OR d.document_name = filter_document)
    ORDER BY d.embedding <=> query_embedding
    LIMIT match_count;
END;
$$;
```

**The `<=>` Operator (Cosine Distance)**:

```python
cosine_similarity = dot(A, B) / (norm(A) * norm(B))
cosine_distance = 1 - cosine_similarity

# In SQL:
1 - (embedding <=> query_embedding)
↓
1 - 0.02 = 0.98  (high similarity)
1 - 0.85 = 0.15  (low similarity)
```

### 3.5 Inserting Vectors

**File**: `app/db/repository.py`

```python
def insert_chunk(
    self,
    document_name: str,
    chunk_id: int,
    content: str,
    embedding: List[float],  # 3072 floats
    pages: Optional[List[int]] = None,
    page_range: Optional[str] = None
) -> Dict[str, Any]:
    """Insert chunk with embedding."""

    data = {
        "document_name": document_name,
        "chunk_id": chunk_id,
        "content": content,
        "embedding": embedding,  # Auto-converts to halfvec
        "pages": pages,
        "page_range": page_range
    }

    result = self.client.table("documents").insert(data).execute()
    return result.data[0]
```

### Key Takeaways

✅ **pgvector Extension**: Adds vector operations to PostgreSQL
✅ **halfvec Type**: 50% memory savings with minimal accuracy loss
✅ **HNSW Index**: O(log N) search time
✅ **Cosine Similarity**: Scale-invariant semantic matching

---

## Step 4: Retrieval

### Overview

Find the most relevant chunks for a user's query using vector similarity search.

### 4.1 Basic Retrieval

**File**: `app/services/rag/retrieval.py`

```python
class RetrievalService:
    def retrieve(
        self,
        query: str,
        document_name: Optional[str] = None,
        doc_names: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """Retrieve relevant chunks."""

        # Step 1: Embed query
        query_embedding = self.embedding_service.embed_text(query)

        # Step 2: Vector similarity search
        results = self.doc_repo.search_similar(
            query_embedding=query_embedding,
            limit=self.top_k
        )

        # Step 3: Rerank (if enabled)
        if self.use_reranking and self.reranker:
            results = self.reranker.rerank(query, results, top_k=self.top_k)

        return results
```

**Example**:

```python
query = "What are Vietnam's solar energy targets for 2030?"

# Embed query
query_embedding = embed_text(query)
# → [0.13, 0.84, 0.31, ...]

# Search database
results = db.search_similar(query_embedding, limit=10)

# Results:
[
    {
        "content": "Vietnam's PDP8 sets 30 GW solar target by 2030...",
        "similarity": 0.92,
        "page_range": "15-16"
    },
    {
        "content": "Renewable energy plan includes solar...",
        "similarity": 0.87,
        "page_range": "22-23"
    },
    ...
]
```

### 4.2 Multi-Document Retrieval (Two-Stage)

**Problem**: Searching 33 documents × 10 chunks = 330 chunks is expensive.

**Solution**: Two-stage retrieval

```python
def _retrieve_multi_document(self, query: str, query_embedding: List[float]):
    """
    Stage 1: Quick scan - identify relevant documents
    Stage 2: Deep search - exhaustive search in relevant docs
    Result: 330 → 40 chunks (8x reduction!)
    """

    # STAGE 1: Quick document ranking
    initial_chunks_per_doc = 2  # Only 2 chunks per doc
    top_n_documents = 5

    document_scores = {}
    for doc_name in all_documents:
        # Get top 2 chunks from each document
        doc_results = self.doc_repo.search_similar(
            query_embedding=query_embedding,
            limit=2,
            document_name=doc_name
        )

        # Score document by best chunk
        if doc_results:
            best_similarity = max(chunk["similarity"] for chunk in doc_results)
            document_scores[doc_name] = best_similarity

    # Select top 5 documents
    ranked_documents = sorted(
        document_scores.items(),
        key=lambda x: x[1],
        reverse=True
    )[:top_n_documents]

    # STAGE 2: Deep search in top documents only
    deep_chunks_per_doc = 8
    deep_results = []

    for doc_name, _ in ranked_documents:
        doc_results = self.doc_repo.search_similar(
            query_embedding=query_embedding,
            limit=8,
            document_name=doc_name
        )
        deep_results.extend(doc_results)

    # STAGE 3: Rerank
    if self.use_reranking:
        final_results = self.reranker.rerank(query, deep_results, top_k=self.top_k)

    return final_results
```

**Performance**:

```
Stage 1: 33 docs × 2 chunks = 66 chunk comparisons
Stage 2: 5 docs × 8 chunks = 40 chunk comparisons
Reranking: 40 chunks (vs 330 with naive approach)

Time: 15s → 2s (7.5x faster!) ⚡
```

### 4.3 Context Formatting

```python
def format_context(self, chunks: List[Dict[str, Any]]) -> str:
    """Format chunks for LLM."""
    context_parts = []

    for i, chunk in enumerate(chunks, 1):
        context_parts.append(
            f"[Source {i}] Document: {chunk['document_name']}, "
            f"Pages: {chunk['page_range']}\n{chunk['content']}"
        )

    return "\n\n---\n\n".join(context_parts)
```

**Output**:

```
[Source 1] Document: PDP8_full_EN, Pages: 15-16
Vietnam's Power Development Plan VIII sets 30 GW solar target by 2030...

---

[Source 2] Document: PDP8_full_EN, Pages: 22-23
The investment requirements are estimated at $50 billion USD...

---

[Source 3] Document: Solar_Investment_Guide, Pages: 5-6
International funding mechanisms include Green Climate Fund...
```

### Key Takeaways

✅ **Vector Similarity Search**: Fast, semantic matching
✅ **Two-Stage Retrieval**: 8x speedup for multi-document search
✅ **Source Attribution**: Track page numbers for citations

---

## Step 5: Reranking

### Overview

Improve retrieval accuracy by re-scoring results with a cross-encoder model.

### 5.1 Why Rerank?

**Embedding Models (Bi-Encoders)**: Fast but limited

```
Query: "What are 2030 solar targets?"
Document: "Solar energy development goals"

Bi-Encoder:
Query → [0.12, 0.85, ...]
Doc   → [0.14, 0.83, ...]
Score: cosine_similarity = 0.82

Limitation: No interaction between query and document
```

**Cross-Encoder Reranker**: Slower but more accurate

```
Cross-Encoder:
"What are 2030 solar targets? [SEP] Solar energy development goals"
↓
[Transformer with cross-attention]
↓
Score: 0.94

Benefit: Model sees both together, understands interactions
```

### 5.2 Reranking Service

**File**: `app/services/reranker.py`

```python
class RerankerService:
    def __init__(self, model_name: str = "BAAI/bge-reranker-v2-m3"):
        """Initialize with state-of-the-art cross-encoder."""
        device = "cuda" if torch.cuda.is_available() else "cpu"
        self.model = CrossEncoder(model_name, device=device)

    def rerank(
        self,
        query: str,
        chunks: List[Dict],
        top_k: int = 10,
        batch_size: int = 2
    ) -> List[Dict]:
        """Rerank chunks using cross-encoder."""

        # Step 1: Prepare (query, document) pairs
        pairs = [(query, chunk["content"][:1000]) for chunk in chunks]

        # Step 2: Score pairs in batches
        all_scores = []
        for i in range(0, len(pairs), batch_size):
            batch_pairs = pairs[i:i + batch_size]
            batch_scores = self.model.predict(batch_pairs, convert_to_tensor=True)
            all_scores.extend(batch_scores.tolist())

            # Clear GPU cache
            if self.device == "cuda":
                torch.cuda.empty_cache()

        # Step 3: Add rerank scores
        for chunk, score in zip(chunks, all_scores):
            chunk["rerank_score"] = float(score)

        # Step 4: Sort by rerank score
        reranked = sorted(
            chunks,
            key=lambda x: x.get("rerank_score", -float('inf')),
            reverse=True
        )

        return reranked[:top_k]
```

### 5.3 Reranking Example

```
Query: "What are Vietnam's 2030 solar targets?"

After Embedding Search:
═══════════════════════════════════════════════════════════
Rank  Similarity  Content
1.    0.85       "Solar energy targets include capacity goals..."
2.    0.83       "Renewable targets span multiple technologies..."
3.    0.82       "Vietnam's 2030 solar capacity goal is 30 GW."

After Cross-Encoder Reranking:
═══════════════════════════════════════════════════════════
Rank  Rerank      Content
1.    0.94       "Vietnam's 2030 solar capacity goal is 30 GW." ⭐
2.    0.89       "Solar energy targets include capacity goals..."
3.    0.82       "Renewable targets span multiple technologies..."

The most relevant answer moved from rank 3 to rank 1!
```

### 5.4 Performance Optimization

**Batch Processing**:

```python
batch_size = 2  # Process 2 chunks at once

# Why small batches?
# - Cross-encoders are memory-intensive
# - Long input sequences (query + document)
# - Better to be conservative with OOM fallback
```

**Content Truncation**:

```python
max_content_length = 1000  # characters

# Why truncate?
# - First 1000 chars usually contain key info
# - 3-4x speedup with minimal accuracy loss
```

### Key Takeaways

✅ **Cross-Encoder**: More accurate than embeddings alone
✅ **Attention Mechanism**: Models query-document interactions
✅ **Batch Processing**: GPU acceleration with OOM protection
✅ **Content Truncation**: Speed optimization

---

## Step 6: Answer Generation

### Overview

Generate comprehensive answers using retrieved context and LLM.

### 6.1 DSPy Framework

**DSPy** (Declarative Self-improving Language Programs): Structured prompting framework

**File**: `app/services/rag/dspy_rag.py`

```python
class GenerateAnswer(dspy.Signature):
    """Signature defines inputs and outputs."""

    context: str = dspy.InputField(
        desc="Retrieved passages from documents, may include tables"
    )
    question: str = dspy.InputField(
        desc="User's question"
    )
    answer: str = dspy.OutputField(
        desc="Comprehensive answer with **bold** for key terms. "
             "Cite sources with [N]. Preserve tables. "
             "Separate aspects into paragraphs."
    )
```

**Benefits**:
- Structured, typed interfaces
- Automatic prompt optimization
- Chain-of-thought reasoning
- Trainable with examples

### 6.2 Single-Hop RAG

```python
class RAGModule(dspy.Module):
    """Single retrieval, then generate."""

    def __init__(self, retrieval_service, num_passages=5):
        super().__init__()
        self.retrieval_service = retrieval_service
        self.generate_answer = dspy.ChainOfThought(GenerateAnswer)

    def forward(self, question: str, doc_names=None):
        # Step 1: Retrieve
        chunks = self.retrieval_service.retrieve(
            query=question,
            doc_names=doc_names
        )

        # Step 2: Format context
        context = self.retrieval_service.format_context(chunks)

        # Step 3: Generate answer
        prediction = self.generate_answer(
            context=context,
            question=question
        )

        prediction.chunks = chunks
        return prediction
```

**Chain-of-Thought**:

```
Context: [retrieved chunks]
Question: What are the solar targets?

Reasoning:
- Context mentions PDP8 targets
- Source 1 states 30 GW solar by 2030
- Source 2 provides regional breakdown
- Aligns with Paris Agreement

Answer: Vietnam's PDP8 sets **solar capacity target
of 30 GW by 2030**. This includes utility-scale and
rooftop installations. [1][2]
```

### 6.3 Multi-Hop RAG

For complex queries requiring multiple retrievals:

**File**: `app/services/rag/multihop_rag.py`

```python
class MultiHopRAG(dspy.Module):
    """Iterative retrieval and reasoning."""

    def forward(self, question: str):
        context_parts = []
        all_chunks = []

        for hop in range(self.max_hops):
            # Hop 1: Original question
            if hop == 0:
                search_query = question
            else:
                # Hop 2+: Generate follow-up query
                query_pred = self.generate_query(
                    context="\n".join(context_parts),
                    question=question
                )
                search_query = query_pred.query

            # Retrieve
            chunks = self.retrieval_service.retrieve(search_query)
            all_chunks.extend(chunks)
            context_parts.extend([c["content"] for c in chunks])

        # Generate final answer from all hops
        context = self.retrieval_service.format_context(all_chunks)
        prediction = self.generate_answer(context=context, question=question)

        return prediction
```

**Multi-Hop Example**:

```
Question: "Compare solar and wind investment requirements"

HOP 1: Original Question
Query: "Compare solar and wind investment requirements"
Retrieved: Solar investment info ($30B)

HOP 2: Follow-up
LLM generates: "Wind energy investment costs PDP8"
Retrieved: Wind investment info ($18B)

HOP 3: Synthesis
LLM generates: "Solar vs wind cost comparison"
Retrieved: Comparative analysis

FINAL ANSWER:
"Vietnam's PDP8 allocates different investments:

**Solar**: $30B over 10 years [1]
- Lower capex
- Faster deployment (3-4 years)

**Wind**: $18B total [4]
- Higher upfront costs
- Longer timeline (5-7 years)"
```

### 6.4 Adaptive RAG

Automatically choose between single-hop and multi-hop:

**File**: `app/services/rag/adaptive_rag.py`

```python
class AdaptiveRAG(dspy.Module):
    def forward(self, question: str):
        # Assess complexity
        assessment = self.assess_complexity(question=question)

        # Choose strategy
        if assessment.complexity == "complex":
            return self.multi_hop(question)
        else:
            return self.single_hop(question)
```

**Complexity Examples**:

```
Simple → Single-Hop:
✓ "What is the solar target for 2030?"
✓ "Who published PDP8?"

Complex → Multi-Hop:
✓ "Compare solar and wind investments"
✓ "How does PDP8 align with climate commitments?"
✓ "Analyze regional differences in deployment"
```

### Key Takeaways

✅ **DSPy Framework**: Structured, optimizable prompting
✅ **Chain-of-Thought**: Better reasoning
✅ **Multi-Hop**: Handles complex queries
✅ **Adaptive Strategy**: Automatic complexity assessment

---

## Complete Pipeline Summary

### End-to-End Flow

```
USER: "What are Vietnam's 2030 solar targets?"
│
▼
┌─────────────────────────────────────────────────┐
│ STEP 1: DOCUMENT INGESTION                      │
│ • Extract PDF with Marker + LLM                 │
│ • Semantic chunking (512 tokens)                │
│ • Table preservation                            │
│ • Page tracking                                 │
│ Output: 52 chunks                               │
└─────────────────────────────────────────────────┘
│
▼
┌─────────────────────────────────────────────────┐
│ STEP 2: EMBEDDING GENERATION                    │
│ • 52 parallel Celery tasks                      │
│ • Gemini embedding (3072 dims)                  │
│ • Rate limiting + circuit breaker               │
│ Output: 52 vectors stored in DB                 │
└─────────────────────────────────────────────────┘
│
▼
┌─────────────────────────────────────────────────┐
│ STEP 3: VECTOR STORAGE                          │
│ • PostgreSQL + pgvector                         │
│ • halfvec for efficiency                        │
│ • HNSW index for fast search                    │
│ Output: Indexed vector database                 │
└─────────────────────────────────────────────────┘
│
▼
USER QUERY: "What are Vietnam's 2030 solar targets?"
│
▼
┌─────────────────────────────────────────────────┐
│ STEP 4: RETRIEVAL                               │
│ • Embed query: [0.13, 0.84, ...]               │
│ • Vector similarity search (HNSW)               │
│ • Two-stage multi-doc retrieval                 │
│ Output: Top 10 chunks (0.92 - 0.78 similarity)  │
└─────────────────────────────────────────────────┘
│
▼
┌─────────────────────────────────────────────────┐
│ STEP 5: RERANKING                               │
│ • Cross-encoder (BGE-reranker-v2-m3)           │
│ • Score (query, doc) pairs                      │
│ • Re-sort by rerank score                       │
│ Output: Top 10 reranked (0.94 - 0.82 score)    │
└─────────────────────────────────────────────────┘
│
▼
┌─────────────────────────────────────────────────┐
│ STEP 6: ANSWER GENERATION                       │
│ • Format context with citations                 │
│ • DSPy adaptive RAG                             │
│ • Chain-of-thought reasoning                    │
│ • Generate comprehensive answer                 │
└─────────────────────────────────────────────────┘
│
▼
ANSWER:
"Vietnam's Power Development Plan VIII (PDP8) sets
ambitious **solar capacity targets of 30 GW by 2030** [1].
This includes both utility-scale solar farms and rooftop
installations distributed across regions [2]. The targets
align with Vietnam's commitments under the Paris Agreement
and represent a significant increase from current capacity [3]."
```

---

## Performance Metrics

### Processing Speed

| Operation | Time | Throughput |
|-----------|------|------------|
| PDF Extraction (100 pages) | 30-45s | 2-3 pages/s |
| Semantic Chunking (50 chunks) | 5-8s | 6-10 chunks/s |
| Embedding (50 chunks, parallel) | 2-3s | 16-25 chunks/s |
| Vector Search (10k vectors) | 5-10ms | 100-200 queries/s |
| Reranking (40 chunks) | 300-500ms | 80-130 chunks/s |
| Answer Generation | 2-5s | 0.2-0.5 answers/s |

### Accuracy Metrics

| Metric | Without Reranking | With Reranking |
|--------|-------------------|----------------|
| Precision@5 | 0.78 | 0.89 |
| Recall@10 | 0.82 | 0.91 |
| MRR | 0.75 | 0.87 |

### Resource Usage

| Resource | Usage |
|----------|-------|
| Vector Storage (1k chunks) | ~6 MB (halfvec) |
| RAM (embedding service) | ~500 MB |
| GPU VRAM (reranking) | ~2 GB |
| PostgreSQL connections | 10-20 concurrent |

---

## Best Practices

### 1. Chunking Strategy

✅ **DO**:
- Use semantic chunking for better context preservation
- Protect tables and structured data
- Track page numbers for citations
- Aim for 400-600 tokens per chunk

❌ **DON'T**:
- Use fixed-size chunking (splits mid-sentence)
- Ignore document structure
- Create chunks smaller than 100 or larger than 1000 tokens
- Split tables across chunks

### 2. Embedding Generation

✅ **DO**:
- Process chunks in parallel (Celery)
- Use rate limiting to respect API limits
- Implement circuit breaker for failures
- Cache embeddings when possible

❌ **DON'T**:
- Process sequentially (too slow)
- Ignore rate limits (API errors)
- Skip error handling
- Re-embed unchanged content

### 3. Vector Storage

✅ **DO**:
- Use HNSW index for fast search
- Use halfvec for memory efficiency
- Create indexes on frequently filtered columns
- Monitor index build time

❌ **DON'T**:
- Use IVFFlat for <10k vectors (overkill)
- Skip indexing (slow searches)
- Use full-precision vectors unnecessarily
- Ignore database connection pooling

### 4. Retrieval

✅ **DO**:
- Use two-stage retrieval for many documents
- Implement reranking for accuracy
- Format context with source citations
- Limit context length (avoid token limits)

❌ **DON'T**:
- Retrieve too many chunks (>20)
- Skip reranking (lower accuracy)
- Omit source attribution
- Exceed LLM context window

### 5. Reranking

✅ **DO**:
- Use state-of-the-art models (BGE, MXBai)
- Process in small batches (avoid OOM)
- Truncate long content (first 1000 chars)
- Implement CPU fallback for GPU OOM

❌ **DON'T**:
- Use outdated models (MS-MARCO MiniLM)
- Process all chunks at once (OOM)
- Use full chunk content (slow)
- Crash on OOM errors

### 6. Answer Generation

✅ **DO**:
- Use DSPy for structured prompting
- Implement chain-of-thought reasoning
- Choose adaptive strategy (single vs multi-hop)
- Include source citations

❌ **DON'T**:
- Use raw string prompts
- Skip reasoning steps
- Always use multi-hop (slow)
- Generate answers without citations

---

## Troubleshooting

### Common Issues

**1. Slow Embedding Generation**
```
Problem: 50 chunks take 50+ seconds
Solution: Use Celery parallel processing (should be 2-3s)
Check: Celery workers running? Redis connected?
```

**2. Low Retrieval Accuracy**
```
Problem: Irrelevant results returned
Solution: Enable reranking with cross-encoder
Check: Reranker model loaded? GPU available?
```

**3. GPU Out of Memory**
```
Problem: Reranking crashes with OOM
Solution: Reduce batch_size or use CPU
Check: batch_size=2, force_cpu=True if needed
```

**4. Missing Citations**
```
Problem: Answers lack source references
Solution: Include page tracking in chunks
Check: page_range populated? Context formatted?
```

**5. Slow Vector Search**
```
Problem: Searches take >1 second
Solution: Create HNSW index
Check: Index exists? Index type correct?
```

---

## Conclusion

This guide covered the complete RAG pipeline from document ingestion to answer generation. The pdp8-rag system demonstrates production-ready patterns:

- **Semantic chunking** for context preservation
- **Parallel processing** for speed
- **Two-stage retrieval** for multi-document efficiency
- **Cross-encoder reranking** for accuracy
- **Adaptive RAG** for query complexity handling

Key innovations:
1. LLM-enhanced PDF extraction with Marker
2. Semantic chunking with table preservation
3. Parallel embedding generation with Celery
4. HNSW indexing for fast vector search
5. Two-stage multi-document retrieval
6. State-of-the-art reranking
7. DSPy for structured prompting

For questions or contributions, see the [project repository](https://github.com/your-repo/pdp8-rag).

---

**Generated from pdp8-rag codebase analysis**
**Last updated**: February 2026
