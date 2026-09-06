FROM python:3.11-slim

WORKDIR /app

# Install system dependencies (including libpq for psycopg2)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install python packages
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source code
COPY . .

# Expose FastAPI port
EXPOSE 8000

# Command to run application
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
