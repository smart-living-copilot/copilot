# Data Replay

`data-replay` serves offline versions of the REFIT and Dudopark history endpoints.
It replays a captured fixture window on a loop and exposes WoT Thing Descriptions
that point at the local replay server.

## Files

- `build_fixtures.py`: downloads history data and builds `fixtures.db`
- `replay_server.py`: FastAPI server that replays history and `/latest` responses
- `td_generator.py`: generates Thing Descriptions for the replayed devices
- `tests/test_replay_server.py`: endpoint tests for the replay logic

## Build Fixtures

Create a local `sources.yaml` in this directory, then build the fixture database:

```bash
python build_fixtures.py --force-overwrite
```

Device entries in `sources.yaml` can include a `metadata` block, which is copied
into the generated Thing Descriptions.

The generated `fixtures.db` is ignored in git.

## Run

Run the service with Docker Compose from the repo root:

```bash
docker compose up data-replay
```

The service reads its database path and public base URL from environment
variables configured in Compose.

## Test

Run the replay tests in the service container:

```bash
docker compose run --rm --entrypoint python \
  -v "$(pwd)/data-replay/tests:/app/tests:ro" \
  data-replay \
  -m unittest discover -s /app/tests -p 'test_*.py'
```
