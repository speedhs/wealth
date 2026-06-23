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
COPY order-manager/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy common shared files
COPY commons /app/commons

# Copy application files
COPY order-manager/app /app/app
COPY order-manager/.env /app/.env

# Default command
CMD ["python", "-m", "app.workers.order_manager"]
