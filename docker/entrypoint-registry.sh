#!/bin/sh
set -e

# Start the registry server. The app lifecycle owns the search indexer.
exec uvicorn copilot.registry_app:app --host 0.0.0.0 --port 8000 "$@"
