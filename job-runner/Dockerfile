FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml /app/
COPY job_runner /app/job_runner

RUN pip install --no-cache-dir .

EXPOSE 8890

CMD ["uvicorn", "job_runner.api:app", "--host", "0.0.0.0", "--port", "8890"]
