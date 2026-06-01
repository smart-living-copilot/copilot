FROM python:3.12-slim AS base

WORKDIR /app

COPY pyproject.toml ./
COPY src/ src/
RUN pip install --no-cache-dir .

EXPOSE 8123

CMD ["copilot", "serve"]
