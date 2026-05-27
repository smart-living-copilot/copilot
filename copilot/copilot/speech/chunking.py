"""Text chunking helpers for low-latency speech synthesis."""

from __future__ import annotations

import re


_BOUNDARY_PATTERN = re.compile(r"[.!?](?:[\"')\]]+)?(?:\s+|$)|\n+")


class SemanticTextChunker:
    """Collect streamed text into phrase-sized chunks for TTS.

    The chunker prefers sentence boundaries, but it will split long text on a
    nearby whitespace boundary so streaming speech does not wait indefinitely
    for punctuation.
    """

    def __init__(self, *, min_chars: int = 32, max_chars: int = 220) -> None:
        self._min_chars = max(1, min_chars)
        self._max_chars = max(self._min_chars, max_chars)
        self._buffer = ""

    def accept(self, text: str) -> list[str]:
        if not text:
            return []
        self._buffer += text
        return self._pop_ready(final=False)

    def flush(self) -> str | None:
        chunks = self._pop_ready(final=True)
        if not chunks:
            return None
        return " ".join(chunks)

    def _pop_ready(self, *, final: bool) -> list[str]:
        chunks: list[str] = []
        while True:
            self._buffer = self._buffer.lstrip()
            if not self._buffer:
                return chunks

            split_at = self._semantic_boundary()
            if split_at is None and len(self._buffer) >= self._max_chars:
                split_at = self._fallback_boundary()
            if split_at is None:
                if final:
                    chunks.append(self._buffer.strip())
                    self._buffer = ""
                return chunks

            if not final and split_at < self._min_chars and len(self._buffer) < self._max_chars:
                return chunks

            chunk = self._buffer[:split_at].strip()
            self._buffer = self._buffer[split_at:]
            if chunk:
                chunks.append(chunk)

    def _semantic_boundary(self) -> int | None:
        matches = list(_BOUNDARY_PATTERN.finditer(self._buffer))
        if not matches:
            return None
        for match in matches:
            if match.end() >= self._min_chars:
                return match.end()
        return matches[-1].end()

    def _fallback_boundary(self) -> int:
        window = self._buffer[: self._max_chars]
        split_at = max(window.rfind(" "), window.rfind(","), window.rfind(";"), window.rfind(":"))
        if split_at >= self._min_chars:
            return split_at + 1
        return self._max_chars
