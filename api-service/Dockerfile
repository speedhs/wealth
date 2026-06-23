# Use Python 3.10 slim image
FROM python:3.10-slim

# Set working directory
WORKDIR /app

# Install system dependencies needed for compiling certain packages (like psycopg2)
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install
COPY api-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy common shared files
COPY commons /app/commons

# Copy application files and frontend static files
COPY api-service/app /app/app
COPY frontend /app/frontend
COPY api-service/.env /app/.env

# Expose API port
EXPOSE 8000

# Default command
CMD ["uvicorn", "app.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
