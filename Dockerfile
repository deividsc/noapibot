FROM python:3.12-slim

# System deps + Node.js 22 (for opencode CLI)
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl gnupg ca-certificates \
    && curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# Install opencode CLI (model manager — supports Anthropic via ANTHROPIC_API_KEY)
# Docs: https://opencode.ai — set ANTHROPIC_API_KEY to use Claude models
RUN npm install -g opencode-ai

WORKDIR /app

# Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App source
COPY . .

# Persistent data dir (mounted to Cloud Storage FUSE or local volume)
RUN mkdir -p /data/sessions /data/agents /data/skills /data/personas

ENV NOAPIBOT_DATA_DIR=/data
ENV NOAPIBOT_DEFAULT_ENGINE=opencode
ENV PYTHONUNBUFFERED=1

# Cloud Run sets PORT; default to 8080
EXPOSE 8080
CMD ["sh", "-c", "uvicorn server:app --host 0.0.0.0 --port ${PORT:-8080}"]
