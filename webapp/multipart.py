"""Parse one ``multipart/form-data`` body into fields and uploaded files (stdlib only).

The stdlib ``cgi`` module that used to do this was removed in Python 3.13, and a
file upload from a plain HTML form is the only multipart the surface receives, so a
small deterministic parser is lighter than a new dependency. It splits on the
boundary, reads each part's ``Content-Disposition`` for its name (and filename),
and returns text fields as ``str`` and file parts as ``(filename, bytes)``.
"""

from __future__ import annotations

__all__ = ["parse_multipart"]


def _boundary(content_type: str) -> bytes:
    """The multipart boundary token from a ``Content-Type`` header value."""
    for token in content_type.split(";"):
        key, _, value = token.strip().partition("=")
        if key.lower() == "boundary":
            return value.strip('"').encode("latin-1")
    raise ValueError("multipart/form-data content type carries no boundary")


def _disposition(head: bytes) -> dict[str, str]:
    """Parse a part's headers into the ``Content-Disposition`` parameters.

    >>> _disposition(b'Content-Disposition: form-data; name="file"; filename="a.csv"')
    {'name': 'file', 'filename': 'a.csv'}
    """
    params: dict[str, str] = {}
    for line in head.split(b"\r\n"):
        if not line.lower().startswith(b"content-disposition:"):
            continue
        for token in line.decode("latin-1").split(";")[1:]:
            key, _, value = token.strip().partition("=")
            params[key.lower()] = value.strip('"')
    return params


def parse_multipart(content_type: str, body: bytes) -> tuple[dict[str, str], dict[str, tuple[str, bytes]]]:
    """Split a ``multipart/form-data`` body into (text fields, uploaded files).

    Text fields map name → decoded value; files map name → (filename, raw bytes).
    Parsing is deterministic: parts are read in body order, and exactly one framing
    CRLF is trimmed from each part's content (never bytes the sender put there).
    """
    delimiter = b"--" + _boundary(content_type)
    fields: dict[str, str] = {}
    files: dict[str, tuple[str, bytes]] = {}
    for part in body.split(delimiter):
        part = part[2:] if part.startswith(b"\r\n") else part  # strip the CRLF that precedes the headers
        if not part or part.startswith(b"--"):  # preamble, closing delimiter, or epilogue
            continue
        head, separator, content = part.partition(b"\r\n\r\n")
        if not separator:
            continue
        content = content[:-2] if content.endswith(b"\r\n") else content  # the CRLF before the next delimiter
        disposition = _disposition(head)
        name = disposition.get("name")
        if name is None:
            continue
        if "filename" in disposition:
            files[name] = (disposition["filename"], content)
        else:
            fields[name] = content.decode("utf-8")
    return fields, files
