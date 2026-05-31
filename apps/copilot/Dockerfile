FROM python:3.12-slim AS base

WORKDIR /app

ARG PYTORCH_CPU_INDEX_URL=https://download.pytorch.org/whl/cpu

# silero-vad depends on torch/torchaudio. The default Linux wheels from PyPI
# pull CUDA runtime packages, so install CPU-only wheels before resolving the app.
RUN pip install --no-cache-dir --index-url "${PYTORCH_CPU_INDEX_URL}" \
    "torch>=2.2,<2.9" \
    "torchaudio>=2.2,<2.9"

COPY pyproject.toml ./
COPY src/ src/
RUN pip install --no-cache-dir .

EXPOSE 8123

CMD ["copilot", "serve"]
