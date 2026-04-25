# PDP8 RAG Frontend

React frontend for the PDP8 RAG Chat application.

## Development

```bash
# Install dependencies
npm install

# Start development server (with proxy to backend)
npm run dev

# Build for production
npm run build

# Preview production build
npm run preview
```

## Environment Configuration

The project uses environment variables for flexible configuration across different deployment scenarios.

### Environment Variables

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `VITE_BACKEND_URL` | Backend API URL for Vite dev server proxy | `http://localhost:8009` | No |
| `VITE_API_URL` | Direct API URL for production builds | _(empty, uses proxy)_ | Production only |

### Environment Files

- **`.env`** - Local development defaults (gitignored)
- **`.env.example`** - Template with documentation (tracked in git)
- **`.env.production`** - Production configuration template (tracked in git)
- **`.env.local`** - Local overrides for any environment (gitignored)
- **`.env.production.local`** - Local production overrides (gitignored)

### Setup Instructions

#### Local Development

1. Copy the example environment file:
   ```bash
   cp .env.example .env
   ```

2. The default configuration works with Docker backend (port 8009):
   ```bash
   VITE_BACKEND_URL=http://localhost:8009
   VITE_API_URL=
   ```

3. Start the development server:
   ```bash
   npm run dev
   ```

The Vite dev server will proxy `/chat`, `/documents`, and `/rag` routes to the backend URL.

#### Docker Development

When running with docker-compose, use the default configuration:
```bash
VITE_BACKEND_URL=http://localhost:8009
VITE_API_URL=
```

The backend container exposes port 8009 (mapped from internal port 8000).

#### Production Deployment

1. Create a `.env.production.local` file with your production API URL:
   ```bash
   VITE_BACKEND_URL=https://api.yourdomain.com
   VITE_API_URL=https://api.yourdomain.com
   ```

2. Build for production:
   ```bash
   npm run build
   ```

The `VITE_API_URL` value will be embedded in the production JavaScript bundle.

### How It Works

- **Development Mode**: The Vite dev server proxies API requests to `VITE_BACKEND_URL`, allowing you to avoid CORS issues
- **Production Mode**: The application makes direct requests to `VITE_API_URL` (no proxy available in production builds)
- **Environment Precedence**: `.env.[mode].local` > `.env.[mode]` > `.env.local` > `.env`

## Project Structure

```
src/
├── components/         
│   ├── chat/           
│   ├── history/        
│   ├── layout/         
│   ├── shared/         
│   └── sources/        
├── hooks/              # Custom React hooks
│   ├── useChatManager.ts
│   ├── useDocuments.ts
│   ├── usePopupPosition.ts
│   ├── usePortal.ts
│   ├── useScrollToBottom.ts
│   ├── useTheme.ts
│   └── useTypewriter.ts
├── services/           # API services
│   ├── api.ts
│   ├── chatService.ts
│   └── documentService.ts
├── styles/             # Global CSS
│   ├── global.css
│   └── variables.css
├── types/              # TypeScript definitions
│   └── index.ts
├── App.tsx             # Main App component
├── main.tsx            # Entry point
```

## Features

- Real-time chat with streaming responses
- Document management
- Chat history
- Dark/Light theme
- Citation popups with source information
- Responsive design

## Tech Stack

- React 18
- Vite
- Marked (Markdown parsing)
- EventSource (SSE streaming)
