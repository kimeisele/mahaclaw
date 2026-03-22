FROM python:3.11-slim

WORKDIR /app
COPY . .

# curl needed for llm.py (stdlib-only project, no pip deps)
RUN apt-get update && apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/*

EXPOSE 18789

CMD ["python3", "-m", "mahaclaw.gateway", "--web"]
