FROM python:3.12-slim

WORKDIR /app

# System deps for asyncpg/greenlet compilation
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Python deps — cached layer unless requirements.txt changes
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Application code
COPY config/ config/
COPY src/ src/
COPY scripts/ scripts/
COPY shared/ shared/

# Runtime dirs (ephemeral — not mounted as volumes)
RUN mkdir -p data logs

ENV PYTHONPATH=/app

CMD ["python", "scripts/run_system.py"]
