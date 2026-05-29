FROM python:3.12-slim AS base

WORKDIR /app

COPY pyproject.toml ./
COPY copilot/ copilot/
RUN pip install --no-cache-dir .

EXPOSE 8123

CMD ["uvicorn", "copilot.app:app", "--host", "0.0.0.0", "--port", "8123"]
