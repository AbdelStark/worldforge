"""Asset helpers for HTTP-backed provider adapters."""

from __future__ import annotations

import base64
import mimetypes
from pathlib import Path

from .base import ProviderError


def asset_to_uri(value: str | None, *, default_content_type: str) -> str | None:
    """Return a URL or data URI suitable for provider APIs."""

    if value is None:
        return None
    if value.startswith(("http://", "https://", "data:")):
        return value

    path = Path(value).expanduser().resolve()
    try:
        data = path.read_bytes()
    except FileNotFoundError as exc:
        raise ProviderError(f"Local asset path does not exist: {path}") from exc
    except IsADirectoryError as exc:
        raise ProviderError(f"Local asset path is not a file: {path}") from exc
    except OSError as exc:
        raise ProviderError(f"Could not read local asset {path}: {exc}") from exc

    content_type = mimetypes.guess_type(path.name)[0] or default_content_type
    payload = base64.b64encode(data).decode("ascii")
    return f"data:{content_type};base64,{payload}"
