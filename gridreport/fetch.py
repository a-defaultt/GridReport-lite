import ipaddress
import os
import re
import socket
import tempfile
import urllib.parse
import urllib.request
from pathlib import Path

from .extract import iter_tags

ALLOWED_SCHEMES = {"http", "https"}
MAX_RESPONSE_BYTES = 5_000_000
REQUEST_TIMEOUT = 10
USER_AGENT = "gridreport-learn/0.1"
ALLOW_PRIVATE_ENV = "GRIDREPORT_ALLOW_PRIVATE"
SAFE_SUFFIX_RE = re.compile(r"\.[A-Za-z0-9]{1,8}")


class FetchError(Exception):
    pass


def _same_origin(url: str, origin: str) -> bool:
    """Check if url has the same scheme and netloc as origin."""
    parsed_url = urllib.parse.urlparse(url)
    parsed_origin = urllib.parse.urlparse(origin)
    return (parsed_url.scheme, parsed_url.netloc) == (parsed_origin.scheme, parsed_origin.netloc)


def _check_url(url: str) -> None:
    """Allow only http(s) URLs whose hostname resolves to a public address.

    Applied to the initial URL *and* every redirect target: the page being
    scanned supplies the stylesheet and logo URLs we follow, so a 302 to
    169.254.169.254 would otherwise sail straight past the same-origin check.
    """
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ALLOWED_SCHEMES:
        raise FetchError(f"unsupported URL scheme {parsed.scheme!r} (only http/https allowed)")
    # require an explicit truthy value: plain get() would treat "0" as "bypass"
    if os.environ.get(ALLOW_PRIVATE_ENV, "").strip().lower() in {"1", "true", "yes"}:
        return
    host = parsed.hostname
    if not host:
        raise FetchError(f"no hostname in URL {url!r}")
    try:
        # ponytail: resolve-then-connect leaves a DNS-rebinding window, since
        # urllib resolves the name again itself. Closing it means connecting to
        # the pinned IP with a manual Host header - do that if this ever becomes
        # a service where an untrusted caller supplies the URL.
        addrinfo = socket.getaddrinfo(host, parsed.port or 80, proto=socket.IPPROTO_TCP)
    except ValueError as exc:
        # parsed.port raises on a malformed/out-of-range port, and _check_url is
        # called outside _get's try/except - so it has to convert its own errors
        raise FetchError(f"invalid URL {url!r}: {exc}") from exc
    except socket.gaierror as exc:
        raise FetchError(f"could not resolve {host!r}: {exc}") from exc
    for info in addrinfo:
        ip = ipaddress.ip_address(info[4][0])
        if not ip.is_global:
            raise FetchError(
                f"refusing to fetch {url}: {host} resolves to non-public address {ip}. "
                f"Set {ALLOW_PRIVATE_ENV}=1 to scan an internal or local site on purpose."
            )


class _GuardedRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _check_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


_opener = urllib.request.build_opener(_GuardedRedirectHandler)


def _get(url: str) -> bytes:
    _check_url(url)
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with _opener.open(request, timeout=REQUEST_TIMEOUT) as response:
            data = response.read(MAX_RESPONSE_BYTES + 1)
    except (OSError, ValueError) as exc:
        raise FetchError(f"request to {url} failed: {exc}") from exc
    if len(data) > MAX_RESPONSE_BYTES:
        raise FetchError(f"response from {url} exceeded {MAX_RESPONSE_BYTES} bytes, aborting")
    return data


def find_stylesheet_urls(html: str, limit: int = 5) -> list[str]:
    hrefs = [
        attrs["href"]
        for _, attrs in iter_tags(html, "link")
        if attrs.get("rel", "").lower() == "stylesheet" and attrs.get("href")
    ]
    # dedupe before slicing: Shopify-style themes emit preload+real <link> pairs
    # for the same asset, and duplicates would otherwise eat the sample budget
    return list(dict.fromkeys(hrefs))[:limit]


def fetch_site(url: str) -> tuple[str, list[str], str]:
    """Fetch homepage HTML and same-origin linked CSS (one level deep, max 5 stylesheets)."""
    html = _get(url).decode("utf-8", errors="replace")
    parsed = urllib.parse.urlparse(url)
    base_origin = f"{parsed.scheme}://{parsed.netloc}"

    css_texts = []
    for css_url in find_stylesheet_urls(html):
        absolute = urllib.parse.urljoin(url, css_url)
        if not _same_origin(absolute, base_origin):
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
    if not _same_origin(url, allowed_origin):
        raise FetchError(f"refusing to download from a different origin than {allowed_origin}: {url}")
    data = _get(url)
    # the remote page controls this path, and the suffix becomes a filename that
    # render.py later interpolates into HTML - keep it to boring extensions
    suffix = Path(parsed.path).suffix
    if not SAFE_SUFFIX_RE.fullmatch(suffix):
        suffix = ".png"
    tmp_path = Path(tempfile.mkdtemp()) / f"logo{suffix}"
    tmp_path.write_bytes(data)
    return tmp_path
