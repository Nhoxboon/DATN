# Backend with Gunicorn for production
FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user with home directory
RUN groupadd -r appuser && useradd -r -g appuser -m -d /home/appuser appuser

# Install uv via pip
RUN pip install uv

# Copy dependency files
COPY pyproject.toml uv.lock ./

# Install dependencies
RUN uv sync --frozen

# Copy application code
COPY app ./app
COPY config.yaml ./
COPY models ./models
COPY uploads ./uploads

# Change ownership to non-root user
RUN chown -R appuser:appuser /app /home/appuser

# Switch to non-root user
USER appuser

EXPOSE 8000

# Use Gunicorn with Uvicorn workers for production
CMD ["uv", "run", "gunicorn", "app.main:app", \
     "--workers", "1", \
     "--worker-class", "uvicorn.workers.UvicornWorker", \
     "--bind", "0.0.0.0:8000", \
     "--timeout", "120", \
     "--access-logfile", "-", \
     "--error-logfile", "-"]
