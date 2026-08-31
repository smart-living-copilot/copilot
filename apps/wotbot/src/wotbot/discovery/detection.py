"""Shared state for probing one URL against every detecting provider.

Detection used to be a hardcoded if-chain that imported each provider directly,
so ``capabilities = ("detect", ...)`` described nothing the code actually read.
Providers now declare that they detect, declare how specific their probe is,
and receive this context; the registry decides the order.

The context exists because the probes are not independent: recognizing a uData
or DCAT portal needs the site's homepage, and fetching it once per provider
would multiply requests against a stranger's server. It is fetched lazily, at
most once, and shared.
"""

from __future__ import annotations

import html.parser
import re
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlparse, urlunparse

from wotbot.discovery.http import BoundedHttpClient, HttpPayload


def origin(url: str) -> str:
    """Return the scheme-and-authority prefix of a URL, without a trailing slash."""

    parsed = urlparse(url)
    return urlunparse((parsed.scheme, parsed.netloc, "", "", "", "")).rstrip("/")


class LinkParser(html.parser.HTMLParser):
    """Collects the few homepage signals the portal probes rely on."""

    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []
        self.title = ""
        self.description = ""
        self.language = ""
        self.identity_labels: list[str] = []
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag == "html" and values.get("lang"):
            self.language = str(values["lang"])[:40]
        if tag == "title":
            self._in_title = True
        if tag == "meta" and str(values.get("name") or "").casefold() == "description":
            self.description = str(values.get("content") or "")[:1000]
        identity_marker = f"{values.get('id') or ''} {values.get('class') or ''}".casefold()
        if any(
            marker in identity_marker
            for marker in ("brand", "logo", "site-name", "site_name", "slogan")
        ):
            for attribute in ("title", "alt", "aria-label"):
                label = re.sub(r"\s+", " ", str(values.get(attribute) or "")).strip()
                if label and label not in self.identity_labels:
                    self.identity_labels.append(label[:160])
        if tag not in {"a", "link"}:
            return
        href = values.get("href")
        if href and len(href) <= 2048:
            self.links.append(href)

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._in_title and len(self.title) < 300:
            self.title += data


@dataclass
class Homepage:
    """The parsed homepage, fetched once and shared by every portal probe."""

    payload: HttpPayload
    parser: LinkParser

    @property
    def ok(self) -> bool:
        return 200 <= self.payload.status < 300

    @property
    def root(self) -> str:
        return origin(self.payload.url)

    @property
    def links(self) -> list[str]:
        return [urljoin(self.payload.url, href) for href in self.parser.links]

    def metadata(self) -> dict[str, object]:
        """Title, description, and tags to carry onto a detected source."""

        title = re.sub(r"\s+", " ", self.parser.title).strip()[:300] or self.root
        parts = [
            re.sub(r"\s+", " ", self.parser.description).strip(),
            *self.parser.identity_labels[:4],
        ]
        description = ". ".join(dict.fromkeys(part for part in parts if part))[:1000]
        return {
            "title": title,
            "description": description,
            "tags": tuple(
                value for value in ("external source", "open data", self.parser.language) if value
            ),
        }


@dataclass
class DetectionContext:
    """One URL being probed, plus everything the probes share."""

    url: str
    http: BoundedHttpClient
    evidence: list[str] = field(default_factory=list)
    _homepage: Homepage | None = field(default=None, repr=False)

    @property
    def root(self) -> str:
        return origin(self.url)

    def note(self, message: str) -> None:
        self.evidence.append(message)

    async def homepage(self) -> Homepage:
        """Fetch and parse the site's homepage, at most once per detection."""

        if self._homepage is None:
            payload = await self.http.get(
                self.url, headers={"Accept": "text/html,application/xhtml+xml"}
            )
            parser = LinkParser()
            if 200 <= payload.status < 300:
                parser.feed(payload.text())
            self._homepage = Homepage(payload=payload, parser=parser)
            self.note(
                f"Fetched {payload.url} (HTTP {payload.status}, "
                f"{payload.content_type or 'unknown'})"
            )
        return self._homepage
