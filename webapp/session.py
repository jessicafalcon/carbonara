"""The in-process state of one review loop: upload → confirmed mapping → queue.

A single mutable holder passed through the router. State lives only in memory for
the running server (cross-restart persistence is out of scope for item 4); nothing
here reads a clock or the network. The values are the connector's own results —
the session stores them, it does not compute them.
"""

from __future__ import annotations

import dataclasses
import pathlib

from carbonara.ingest import IngestResult
from carbonara.review import ReviewQueue

__all__ = ["Session"]


@dataclasses.dataclass(slots=True)
class Session:
    """What one loop has produced so far; ``None`` fields are steps not yet taken.

    ``rows`` caches the parsed source once at upload so ``confirm`` and each
    ``rerun`` reuse it rather than re-parsing the bytes; the content hash lives on
    ``ingest`` and is read from there, not duplicated here.
    """

    store_root: pathlib.Path
    raw: bytes | None = None
    rows: list[dict[str, str]] | None = None
    ingest: IngestResult | None = None
    mapping: dict[str, str] | None = None
    queue: ReviewQueue | None = None

    def reset(self) -> None:
        """Drop everything but the store root, so the next upload starts clean."""
        self.raw = None
        self.rows = None
        self.ingest = None
        self.mapping = None
        self.queue = None
