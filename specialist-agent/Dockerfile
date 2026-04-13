FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

COPY pyproject.toml /app/
COPY specialist_agent /app/specialist_agent

# Install uv alongside the package so `uvx` is available for stdio MCP servers
# (e.g. uvx mcp-server-fetch).  Node.js / npx is NOT included by default; add
# `apt-get install nodejs npm` here if you need npx-based MCP packages.
RUN pip install --no-cache-dir uv .

EXPOSE 8140

CMD ["uvicorn", "specialist_agent.app:app", "--host", "0.0.0.0", "--port", "8140"]
