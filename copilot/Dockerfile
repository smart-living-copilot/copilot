FROM python:3.12-slim AS base

WORKDIR /app

COPY pyproject.toml ./
RUN pip install --no-cache-dir .

COPY copilot/ copilot/

EXPOSE 8123

CMD ["uvicorn", "copilot.server:app", "--host", "0.0.0.0", "--port", "8123"]
