# PDP8 RAG System

A production-ready Retrieval-Augmented Generation (RAG) system for analyzing Vietnam's Electricity Master Plan VIII (PDP8) documents using advanced NLP techniques and adaptive multi-hop reasoning.

## Features

### Core Capabilities
- **Adaptive RAG**: Automatically selects between single-hop and multi-hop retrieval based on query complexity
- **Multi-hop Reasoning**: Supports up to 4 hops for complex queries requiring deeper context
- **Semantic Chunking**: Intelligent document chunking using similarity-based strategies
- **LLM-Enhanced PDF Processing**: Uses Marker PDF with LLM capabilities for accurate document extraction
- **Vector Search**: Supabase with pgvector for efficient similarity search
- **DSPy Integration**: Optimized prompts and retrieval strategies using DSPy framework

### Architecture
- **FastAPI Backend**: High-performance async API
- **React Frontend**: Modern, responsive user interface
- **Celery Workers**: Distributed task processing for document ingestion
- **Redis**: Caching and task queue management
- **Supabase**: PostgreSQL database with vector extensions
- **Multi-LLM Support**: Compatible with Gemini, OpenAI, and Anthropic models
- **Docker**: Containerized deployment for easy setup

### Processing Pipeline
1. **PDF Ingestion**: LLM-powered extraction preserving structure and formatting
2. **Semantic Chunking**: Context-aware text segmentation
3. **Embedding Generation**: Vector representations using Gemini or OpenAI embeddings
4. **Vector Storage**: Efficient storage in Supabase with pgvector
5. **Adaptive Retrieval**: Smart selection of retrieval strategy
6. **Response Generation**: Context-aware answer synthesis

## Installation

### Prerequisites
- Docker and Docker Compose
- Supabase account
- Google API key (for Gemini) or OpenAI API key

### Quick Start with Docker

1. Clone the repository:
```bash
git clone <repository-url>
cd pdp8-rag
```

2. Configure environment variables:
Create a `.env` file in the root directory:
```env
SUPABASE_URL=your_supabase_url
SUPABASE_ANON_KEY=your_anon_key
SUPABASE_SERVICE_KEY=your_service_key
REDIS_URL=redis://redis:6379/0
GOOGLE_API_KEY=your_google_api_key
```

3. Start all services:
```bash
docker-compose up -d
```

This will start:
- Backend API (http://localhost:8000)
- Frontend (http://localhost:5173)
- Redis (localhost:6379)

4. Access the application:
- Web Interface: http://localhost:5173
- API Documentation: http://localhost:8000/docs

### Manual Installation (Development)

#### Backend Setup

1. Install Python dependencies using uv:
```bash
cd backend
uv sync
```

2. Configure environment variables (create `.env` file as shown above)

3. Start the API server:
```bash
uvicorn app.main:app --reload
```

4. Start Celery workers:
```bash
celery -A app.workers.celery_app worker --loglevel=info
```

5. (Optional) Start Flower for task monitoring:
```bash
celery -A app.workers.celery_app flower
```
Access at http://localhost:5555

#### Frontend Setup

1. Install dependencies:
```bash
cd frontend
npm install
```

2. Start development server:
```bash
npm run dev
```

3. Build for production:
```bash
npm run build
```

## Usage

### Web Interface

1. Open http://localhost:5173 in your browser
2. Select a document from the Sources panel
3. Type your question in the chat input
4. View responses with cited sources
5. Access chat history from the History panel

### API Usage

#### Query Documents

```bash
curl -X POST "http://localhost:8000/rag/query" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "What are the renewable energy targets in PDP8?",
    "mode": "adaptive",
    "document_name": "PDP8_full-with-annexes_EN"
  }'
```

#### Upload Document

```bash
curl -X POST "http://localhost:8000/documents/upload/file" \
  -F "file=@path/to/document.pdf"
```

#### List Documents

```bash
curl -X GET "http://localhost:8000/documents/"
```

#### Delete Document

```bash
curl -X DELETE "http://localhost:8000/documents/{document_name}"
```

### Python Scripts

#### Process Documents

```bash
python scripts/process_pdp8.py --file path/to/document.pdf
```

#### Query via Script

```bash
python scripts/query_rag.py "Your question here"
```

#### Train RAG Models

Train single-hop RAG:
```bash
python scripts/train_rag.py
```

Train multi-hop RAG:
```bash
python scripts/train_multihop_rag.py
```

## Configuration

### Application Settings (`config.yaml`)

#### LLM Configuration

```yaml
llm:
  provider: "gemini"  # or "openai", "anthropic"
  gemini:
    model: "gemini-2.5-pro"
    embedding_model: "gemini-embedding-001"
    temperature: 0.7
    max_tokens: 20000
```

#### RAG Settings

```yaml
rag:
  mode: "adaptive"  # "adaptive", "single-hop", "multi-hop"
  retrieval:
    top_k: 10
    similarity_threshold: 0.7
  multihop:
    enabled: true
    max_hops: 4
    passages_per_hop: 4
```

#### Chunking Settings

```yaml
chunking:
  strategy: "semantic"  # "semantic", "fixed", "recursive"
  chunk_size: 512
  similarity_threshold: 0.5
```

## API Endpoints

### Document Management
- `GET /documents/` - List all available documents
- `POST /documents/upload/file` - Upload PDF via file upload
- `POST /documents/upload/path` - Upload PDF from server path
- `DELETE /documents/{document_name}` - Delete a document

### RAG Operations
- `POST /rag/query` - Query the RAG system
- `GET /rag/health` - Health check endpoint

### Chat Interface
- `GET /chat` - Web chat interface (legacy)
- `POST /chat/message` - Send chat message (legacy)
- `GET /chat/history/{session_id}` - Get chat history (legacy)

## Database Schema

### Documents Table
```sql
CREATE TABLE documents (
  id BIGSERIAL PRIMARY KEY,
  document_name TEXT NOT NULL,
  chunk_id INTEGER NOT NULL,
  content TEXT NOT NULL,
  embedding vector(3072),
  metadata JSONB,
  pages INTEGER[],
  page_range TEXT,
  created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_documents_name ON documents(document_name);
CREATE INDEX idx_documents_embedding ON documents USING ivfflat (embedding vector_cosine_ops);
```

### Processing Status Table
```sql
CREATE TABLE document_processing_status (
  document_name TEXT PRIMARY KEY,
  status TEXT NOT NULL,
  task_id TEXT,
  total_chunks INTEGER,
  processed_chunks INTEGER,
  error_message TEXT,
  completed_at TIMESTAMP,
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW()
);
```

## Project Structure

```
pdp8-rag/
├── app/                      # Backend application
│   ├── api/                  # API routes
│   ├── core/                 # Core configuration
│   ├── db/                   # Database repositories
│   │   ├── dependencies.py   # DB dependency injection
│   │   ├── repository.py     # Document repository
│   │   └── processing_status.py
│   ├── models/               # Data models
│   ├── routers/              # FastAPI routers
│   │   ├── documents.py      # Document endpoints
│   │   ├── rag.py            # RAG endpoints
│   │   └── chat.py           # Chat endpoints
│   ├── schemas/              # Pydantic schemas
│   ├── services/             # Business logic
│   │   ├── chat/             # Chat session management
│   │   ├── documents/        # Document processing
│   │   ├── embedding/        # Embedding generation
│   │   ├── pdf_processor/    # PDF processing with Marker
│   │   ├── rag/              # RAG implementation
│   │   └── storage/          # Vector storage
│   ├── static/               # Static files (CSS, JS)
│   ├── templates/            # HTML templates
│   ├── workers/              # Celery workers
│   └── main.py               # FastAPI application entry
├── frontend/                 # React frontend
│   ├── src/
│   │   ├── components/       # React components
│   │   │   ├── ChatInput/
│   │   │   ├── ChatMessages/
│   │   │   ├── Citation/
│   │   │   ├── Header/
│   │   │   ├── HistoryPanel/
│   │   │   ├── Message/
│   │   │   └── SourcesPanel/
│   │   ├── hooks/            # Custom React hooks
│   │   │   ├── useChat.js
│   │   │   ├── useDocuments.js
│   │   │   ├── useHistory.js
│   │   │   └── useTheme.js
│   │   ├── services/         # API services
│   │   │   ├── api.js
│   │   │   ├── chatService.js
│   │   │   └── documentService.js
│   │   ├── App.jsx           # Main app component
│   │   └── main.jsx          # Entry point
│   ├── public/               # Public assets
│   └── package.json          # NPM dependencies
├── models/                   # Trained model artifacts
├── scripts/                  # Utility scripts
│   ├── process_pdp8.py       # Document processing
│   ├── query_rag.py          # Query script
│   ├── train_rag.py          # Train single-hop
│   └── train_multihop_rag.py # Train multi-hop
├── tests/                    # Test suite
├── uploads/                  # Document uploads directory
├── config.yaml               # Application configuration
├── docker-compose.yml        # Docker services configuration
├── Dockerfile                # Backend Docker image
└── pyproject.toml            # Python dependencies
```

## Development

### Running Tests

```bash
pytest tests/
```

### Type Checking

```bash
pyright
```

### Code Formatting

Backend:
```bash
ruff format app/
ruff check app/ --fix
```

Frontend:
```bash
npm run lint
```

## Performance Optimizations

- Circuit breaker pattern for API resilience
- Distributed locking for concurrent processing
- Rate limiting for API endpoints
- Connection pooling for database
- Embedding caching in Redis
- Pagination for large document lists
- Optimized vector similarity search with indexes

## Monitoring

### Celery Flower
Access task monitoring dashboard at http://localhost:5555

### Processing Status
Check document processing status:
```bash
python check_status.py
```

### Health Checks
- API Health: http://localhost:8000/rag/health
- Backend Status: http://localhost:8000/docs

## Troubleshooting

### Backend Issues

**Check Docker logs:**
```bash
docker logs pdp8-backend
docker logs pdp8-frontend
docker logs pdp8-redis
```

**Restart services:**
```bash
docker-compose restart
```

**Reset circuit breakers:**
```bash
python scripts/reset_circuit_breakers.py
```

### Database Issues

**Check Supabase connection:**
```bash
python -c "from app.db.dependencies import get_supabase_client; print(get_supabase_client())"
```

**View documents in database:**
```bash
python -c "from app.db.dependencies import get_supabase_client; from app.db.repository import get_document_repository; repo = get_document_repository(get_supabase_client()); print(repo.list_documents())"
```

### Frontend Issues

**Clear cache and rebuild:**
```bash
cd frontend
rm -rf node_modules/.vite
npm run dev
```

**Check API connection:**
```bash
curl http://localhost:8000/documents/
```

## Docker Commands

### Start all services
```bash
docker-compose up -d
```

### Stop all services
```bash
docker-compose down
```

### View logs
```bash
docker-compose logs -f
```

### Rebuild containers
```bash
docker-compose build
docker-compose up -d
```

### Access backend shell
```bash
docker exec -it pdp8-backend bash
```

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

[Add your license here]

## Acknowledgments

- Built with [DSPy](https://github.com/stanfordnlp/dspy) for optimized prompting
- PDF processing powered by [Marker](https://github.com/VikParuchuri/marker)
- Vector search using [pgvector](https://github.com/pgvector/pgvector)
- Frontend built with [React](https://react.dev/) and [Vite](https://vitejs.dev/)
- Backend powered by [FastAPI](https://fastapi.tiangolo.com/)
