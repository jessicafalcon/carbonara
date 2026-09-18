"""Build multipart/form-data bodies for the webapp tests (shared helper, not a test)."""

from __future__ import annotations

_BOUNDARY = b"X-BOUND"
CONTENT_TYPE = f"multipart/form-data; boundary={_BOUNDARY.decode()}"


def multipart_body(parts: list[tuple[bytes, bytes]]) -> bytes:
    """Assemble a body from (Content-Disposition header, content) parts."""
    chunks = [b"--" + _BOUNDARY + b"\r\n" + head + b"\r\n\r\n" + content + b"\r\n" for head, content in parts]
    return b"".join(chunks) + b"--" + _BOUNDARY + b"--\r\n"


def upload_body(raw: bytes, filename: str = "bom_v1.csv") -> bytes:
    """A single-file upload body — the shape the console's upload form submits."""
    head = f'Content-Disposition: form-data; name="file"; filename="{filename}"'.encode()
    return multipart_body([(head, raw)])
