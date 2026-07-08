FROM python:3.12-slim AS base

WORKDIR /app

COPY pyproject.toml ./
COPY src/ src/
RUN pip install --no-cache-dir .
# alembic.ini and migrations/ ship inside the installed package (see
# pyproject force-include), so no separate COPY is needed.

EXPOSE 8123

CMD ["wotbot", "serve"]
