"""Run public source detection against a corpus of real URLs and report.

This measures the detection chain instead of asserting on it: it contacts the
live internet, so it is a tool rather than a test. The point is to size the
four buckets before deciding what to build next -- correct, false positive,
missed-but-findable, and genuinely undiscoverable.

    uv run python scripts/probe_sources.py
    uv run python scripts/probe_sources.py --apis-guru 40
    uv run python scripts/probe_sources.py --json results.json

A false positive is the result that matters most: a source detected as
something it is not gets registered and then never returns anything, which is
worse for a user than an honest "unsupported".
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from wotbot.discovery.http import BoundedHttpClient
from wotbot.discovery.providers.public import resolve_public_source

CORPUS = Path(__file__).with_name("detection_corpus.yaml")
APIS_GURU_LIST = "https://api.apis.guru/v2/list.json"


@dataclass
class Result:
    url: str
    expect: str
    detected: str | None = None
    title: str = ""
    error: str = ""
    evidence: list[str] = field(default_factory=list)

    @property
    def verdict(self) -> str:
        if self.error:
            return "ERROR"
        if self.expect == "unknown":
            return "INFO" if self.detected else "MISS"
        if self.expect == "none":
            return "OK" if self.detected is None else "FALSE-POSITIVE"
        if self.detected == self.expect:
            return "OK"
        return "FALSE-POSITIVE" if self.detected else "MISS"


async def probe(url: str, expect: str) -> Result:
    result = Result(url=url, expect=expect)
    try:
        source, evidence, supported = await asyncio.wait_for(resolve_public_source(url), timeout=60)
        result.evidence = list(evidence)
        if supported and source is not None:
            result.detected = source.provider
            result.title = source.title
    except Exception as exc:  # noqa: BLE001 - a tool: report anything, crash on nothing
        result.error = f"{type(exc).__name__}: {exc}"
    return result


async def apis_guru_sample(count: int) -> list[dict[str, str]]:
    """Sample real OpenAPI documents from the APIs.guru directory."""

    client = BoundedHttpClient(mode="public", max_requests=4, max_bytes=32 * 1024 * 1024)
    payload = await client.get(APIS_GURU_LIST, max_bytes=32 * 1024 * 1024)
    catalogue = payload.json()
    urls: list[str] = []
    for entry in catalogue.values():
        versions = entry.get("versions") or {}
        preferred = versions.get(entry.get("preferred")) or next(iter(versions.values()), None)
        swagger_url = (preferred or {}).get("swaggerUrl")
        if swagger_url:
            urls.append(swagger_url)
    random.shuffle(urls)
    return [{"url": url, "expect": "openapi", "note": "APIs.guru sample"} for url in urls[:count]]


def report(results: list[Result]) -> int:
    width = max((len(r.url) for r in results), default=20)
    print()
    for result in results:
        detected = result.detected or ("-" if not result.error else "!")
        print(f"  {result.verdict:<15} {result.url:<{width}}  {detected:<9} {result.title[:40]}")

    counts: dict[str, int] = {}
    for result in results:
        counts[result.verdict] = counts.get(result.verdict, 0) + 1
    print("\n  " + "  ".join(f"{name}={count}" for name, count in sorted(counts.items())))

    problems = [r for r in results if r.verdict in {"FALSE-POSITIVE", "ERROR"}]
    if problems:
        print("\n  --- evidence for false positives and errors ---")
        for result in problems:
            print(f"\n  {result.url}  [{result.verdict}]")
            if result.error:
                print(f"    error: {result.error}")
            for line in result.evidence:
                print(f"    - {line}")
    return len([r for r in results if r.verdict == "FALSE-POSITIVE"])


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, default=CORPUS)
    parser.add_argument(
        "--apis-guru",
        type=int,
        default=0,
        metavar="N",
        help="also sample N real OpenAPI specs from the APIs.guru directory",
    )
    parser.add_argument("--json", type=Path, help="write full results, including evidence")
    parser.add_argument("--concurrency", type=int, default=4, help="parallel probes (be polite)")
    args = parser.parse_args()

    entries: list[dict[str, Any]] = yaml.safe_load(args.corpus.read_text()) or []
    if args.apis_guru:
        entries += await apis_guru_sample(args.apis_guru)
    print(f"Probing {len(entries)} URLs...")

    semaphore = asyncio.Semaphore(max(1, args.concurrency))

    async def bounded(entry: dict[str, Any]) -> Result:
        async with semaphore:
            return await probe(str(entry["url"]), str(entry.get("expect", "unknown")))

    results = await asyncio.gather(*(bounded(entry) for entry in entries))
    false_positives = report(list(results))

    if args.json:
        args.json.write_text(
            json.dumps([result.__dict__ for result in results], indent=2, default=str)
        )
        print(f"\n  wrote {args.json}")
    return 1 if false_positives else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
