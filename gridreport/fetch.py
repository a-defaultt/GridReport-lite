import re
import tempfile
import urllib.parse
import urllib.request
from pathlib import Path

ALLOWED_SCHEMES = {"http", "https"}
MAX_RESPONSE_BYTES = 5_000_000
REQUEST_TIMEOUT = 10
USER_AGENT = "gridreport-learn/0.1"

CSS_LINK_RE = re.compile(r'<link[^>]+rel="stylesheet"[^>]+href="([^"]+)"', re.IGNORECASE)


class FetchError(Exception):
    pass


def _get(url: str) -> bytes:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ALLOWED_SCHEMES:
        raise FetchError(f"unsupported URL scheme {parsed.scheme!r} (only http/https allowed)")
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as response:
            data = response.read(MAX_RESPONSE_BYTES + 1)
    except OSError as exc:
        raise FetchError(f"request to {url} failed: {exc}") from exc
    if len(data) > MAX_RESPONSE_BYTES:
        raise FetchError(f"response from {url} exceeded {MAX_RESPONSE_BYTES} bytes, aborting")
    return data


def fetch_site(url: str) -> tuple[str, list[str], str]:
    """Fetch homepage HTML and same-origin linked CSS (one level deep, max 5 stylesheets)."""
    html = _get(url).decode("utf-8", errors="replace")
    parsed = urllib.parse.urlparse(url)
    base_origin = f"{parsed.scheme}://{parsed.netloc}"

    css_texts = []
    for css_url in CSS_LINK_RE.findall(html)[:5]:
        absolute = urllib.parse.urljoin(url, css_url)
        if not absolute.startswith(base_origin):
            continue
        try:
            css_texts.append(_get(absolute).decode("utf-8", errors="replace"))
        except FetchError:
            continue
    return html, css_texts, base_origin


def download_binary(url: str, allowed_origin: str) -> Path:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ALLOWED_SCHEMES:
        raise FetchError(f"unsupported URL scheme {parsed.scheme!r} (only http/https allowed)")
    if not url.startswith(allowed_origin):
        raise FetchError(f"refusing to download from a different origin than {allowed_origin}: {url}")
    data = _get(url)
    suffix = Path(parsed.path).suffix or ".png"
    tmp_path = Path(tempfile.mkdtemp()) / f"logo{suffix}"
    tmp_path.write_bytes(data)
    return tmp_path
