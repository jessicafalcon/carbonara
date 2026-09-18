"""Serve the review console on localhost: upload → drift gate → review → re-run.

Lives outside ``carbonara/`` because it binds a socket and does file I/O; the
request handling itself is the pure :func:`webapp.app.handle`. State is one
in-process :class:`~webapp.session.Session` (one reviewer, one machine) over a
temporary store; cross-restart persistence is out of scope (backlog item 4).

Run ``uv run python scripts/serve.py [port]`` (default 8000) and open the printed
URL. Stop with Ctrl-C.
"""

from __future__ import annotations

import datetime
import pathlib
import sys
import tempfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from webapp.app import handle
from webapp.session import Session


class _Handler(BaseHTTPRequestHandler):
    """Read the request, delegate to the pure router, write its response."""

    # ponytail: one shared session, not concurrency-safe; fine for a single local
    # reviewer. Give each browser its own session (by cookie) if it grows.
    session: Session

    def _dispatch(self, method: str) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b""
        path = self.path.split("?", 1)[0]
        now = datetime.datetime.now(datetime.UTC).isoformat()  # the boundary owns the clock, not the router
        response = handle(
            method, path, self.session, now=now, content_type=self.headers.get("Content-Type", ""), body=body
        )
        payload = response.body.encode("utf-8")
        self.send_response(response.status)
        self.send_header("Content-Type", response.content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:  # noqa: N802 (http.server's required method name)
        self._dispatch("GET")

    def do_POST(self) -> None:  # noqa: N802
        self._dispatch("POST")

    def log_message(self, format: str, *args: object) -> None:  # keep the console quiet
        pass


def main(port: int) -> None:
    store = pathlib.Path(tempfile.mkdtemp(prefix="carbonara-review-"))
    _Handler.session = Session(store_root=store)
    server = ThreadingHTTPServer(("127.0.0.1", port), _Handler)
    print(f"review console on http://127.0.0.1:{port}  ·  store {store}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        server.server_close()


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 8000)
