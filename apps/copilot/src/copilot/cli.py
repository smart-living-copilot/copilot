"""Command line entrypoint for copilot process roles."""

from __future__ import annotations

import argparse
import os
from collections.abc import Sequence


def _exec(args: Sequence[str]) -> None:
    os.execvp(args[0], list(args))


def _serve(args: argparse.Namespace) -> None:
    command = [
        "uvicorn",
        "copilot.api.main:app",
        "--host",
        args.host,
        "--port",
        str(args.port),
    ]
    if args.reload:
        command.extend(["--reload", "--reload-dir", "src/copilot"])
    _exec(command)


def _job_worker(_args: argparse.Namespace) -> None:
    _exec(
        [
            "taskiq",
            "worker",
            "--ack-type",
            "when_saved",
            "copilot.workers.job_worker:broker",
        ]
    )


def _job_scheduler(_args: argparse.Namespace) -> None:
    _exec(
        [
            "taskiq",
            "scheduler",
            "--update-interval",
            os.environ.get("JOB_SCHEDULER_UPDATE_INTERVAL_SECONDS", "2"),
            "--loop-interval",
            "1",
            "copilot.workers.job_scheduler:scheduler",
        ]
    )


def _thing_indexer(_args: argparse.Namespace) -> None:
    from copilot.workers.thing_indexer import run

    run()


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="copilot")
    subparsers = parser.add_subparsers(dest="command", required=True)

    serve = subparsers.add_parser("serve", help="Run the FastAPI service")
    serve.add_argument("--host", default="0.0.0.0")
    serve.add_argument("--port", type=int, default=8123)
    serve.add_argument("--reload", action="store_true")
    serve.set_defaults(func=_serve)

    worker = subparsers.add_parser("job-worker", help="Run the Taskiq job worker")
    worker.set_defaults(func=_job_worker)

    scheduler = subparsers.add_parser("job-scheduler", help="Run the Taskiq scheduler")
    scheduler.set_defaults(func=_job_scheduler)

    thing_indexer = subparsers.add_parser(
        "thing-indexer",
        help="Run the thing search indexer worker",
    )
    thing_indexer.set_defaults(func=_thing_indexer)

    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
