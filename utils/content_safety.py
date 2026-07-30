import html
import re
from urllib.parse import urlsplit, urlunsplit


_MARKDOWN_IMAGE_MARKER = re.compile(r"!(?=\[)")


def sanitize_untrusted_markdown(value) -> str:
    """Keep text formatting while preventing browser-initiated remote embeds.

    Raw HTML is escaped and every Markdown image marker is converted to an
    entity before the Markdown parser sees it. Normal links remain clickable,
    but images and HTML media elements are displayed only as inert text.
    """
    escaped = html.escape(str(value or ""), quote=False)
    return _MARKDOWN_IMAGE_MARKER.sub("&#33;", escaped)


def safe_external_url(value) -> str:
    """Return a normalized HTTP(S) URL or an empty string."""
    candidate = str(value or "").strip()

    if not candidate or len(candidate) > 2048:
        return ""

    try:
        parsed = urlsplit(candidate)
        port = parsed.port
    except ValueError:
        return ""

    if parsed.scheme.lower() not in ("http", "https") or not parsed.hostname:
        return ""

    if parsed.username is not None or parsed.password is not None:
        return ""

    try:
        hostname = parsed.hostname.encode("idna").decode("ascii").lower()
    except UnicodeError:
        return ""
    netloc = f"[{hostname}]" if ":" in hostname else hostname

    if port is not None:
        netloc = f"{netloc}:{port}"

    return urlunsplit(
        (
            parsed.scheme.lower(),
            netloc,
            parsed.path or "",
            parsed.query or "",
            parsed.fragment or "",
        )
    )
