from pathlib import Path

import pytest
from gridreport.fetch import fetch_site, download_binary, FetchError

FIXTURES = Path(__file__).parent / "fixtures"


def test_fetch_site_rejects_non_http_schemes():
    with pytest.raises(FetchError, match="scheme"):
        fetch_site("file:///etc/passwd")


def test_download_binary_rejects_non_http_schemes():
    with pytest.raises(FetchError, match="scheme"):
        download_binary("file:///etc/passwd", allowed_origin="https://example.com")


def test_download_binary_rejects_cross_origin_urls():
    with pytest.raises(FetchError, match="origin"):
        download_binary("https://evil.example/logo.png", allowed_origin="https://example.com")


def test_fetch_site_rejects_domain_suffix_spoofing(monkeypatch):
    # a URL whose netloc merely starts with the same string as the real origin
    # must NOT be treated as same-origin
    def fake_get(url):
        if url == "https://example.com":
            return b'<link rel="stylesheet" href="https://example.com.evil.com/style.css">'
        raise AssertionError(f"should never fetch the spoofed stylesheet URL: {url}")
    import gridreport.fetch as fetch_module
    monkeypatch.setattr(fetch_module, "_get", fake_get)
    html, css_texts, base_origin = fetch_site("https://example.com")
    assert css_texts == []  # the spoofed stylesheet must be skipped, not fetched


def test_download_binary_rejects_domain_suffix_spoofing():
    with pytest.raises(FetchError, match="origin"):
        download_binary("https://example.com.evil.com/logo.png", allowed_origin="https://example.com")


# --- security audit (task 9) regression tests ---

PRIVATE_URLS = [
    "http://169.254.169.254/latest/meta-data/",  # cloud metadata endpoint
    "http://127.0.0.1/",
    "http://localhost/",
    "http://192.168.1.1/",
    "http://10.0.0.5/",
    "http://172.16.0.1/",
    "http://[::1]/",
]


@pytest.mark.parametrize("url", PRIVATE_URLS)
def test_get_refuses_non_public_addresses(url):
    from gridreport.fetch import _get
    with pytest.raises(FetchError, match="non-public address"):
        _get(url)


def test_allow_private_env_var_overrides_the_block(monkeypatch):
    from gridreport.fetch import _check_url
    with pytest.raises(FetchError, match="non-public address"):
        _check_url("http://127.0.0.1/")
    monkeypatch.setenv("GRIDREPORT_ALLOW_PRIVATE", "1")
    _check_url("http://127.0.0.1/")  # must not raise


def test_redirect_to_private_address_is_blocked():
    # a page we scan controls the stylesheet/logo URLs we follow, so a 302 must
    # be re-checked - the pre-flight check on the original URL is not enough
    from gridreport.fetch import _GuardedRedirectHandler
    handler = _GuardedRedirectHandler()
    with pytest.raises(FetchError, match="non-public address"):
        handler.redirect_request(None, None, 302, "Found", {}, "http://169.254.169.254/")


def test_download_binary_ignores_a_hostile_url_suffix(monkeypatch):
    # the remote page controls the logo path, and the suffix becomes a filename
    # that render.py interpolates into HTML - only plain extensions may survive
    import gridreport.fetch as fetch_module
    monkeypatch.setattr(fetch_module, "_get", lambda url: b"data")
    for path in ('/logo."onerror=alert(1)', "/logo.%2e%2e%2f%2e%2e%2fetc%2fpasswd", "/logo.<script>"):
        result = download_binary(f"https://example.com{path}", allowed_origin="https://example.com")
        assert result.name == "logo.png", result.name
        assert result.parent.is_dir()

    keeps = download_binary("https://example.com/brand.svg", allowed_origin="https://example.com")
    assert keeps.name == "logo.svg"


def test_redirect_to_private_address_is_blocked_through_the_real_opener(monkeypatch):
    """End-to-end: a real 302 from a real server must not be followed to an internal IP.

    This is the test that defends the *wiring*. The sibling test above calls
    redirect_request() directly, so it stays green even if _get() is reverted to
    plain urllib.request.urlopen() - which reopens the hole completely.

    The test server has to live on loopback, which the guard itself blocks on the
    first hop, and GRIDREPORT_ALLOW_PRIVATE is global so it would disable the
    redirect check too. So we wave through only the *first* _check_url call and
    let every redirect target hit the real implementation.
    """
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer
    import gridreport.fetch as fetch_module

    metadata_url = "http://169.254.169.254/latest/meta-data/"
    requests_seen = []

    class Redirector(BaseHTTPRequestHandler):
        def do_GET(self):
            requests_seen.append(self.path)
            self.send_response(302)
            self.send_header("Location", metadata_url)
            self.end_headers()

        def log_message(self, *args):
            pass

    real_check = fetch_module._check_url
    checked = []

    def check_all_but_the_first_hop(url):
        checked.append(url)
        if len(checked) > 1:
            real_check(url)

    monkeypatch.setattr(fetch_module, "_check_url", check_all_but_the_first_hop)

    server = HTTPServer(("127.0.0.1", 0), Redirector)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        origin = f"http://127.0.0.1:{server.server_port}"
        # must fail specifically on the address check, not on a timeout talking to
        # 169.254.169.254 - a timeout would also raise FetchError and mask a revert
        with pytest.raises(FetchError, match="non-public address"):
            fetch_module._get(f"{origin}/logo.png")
    finally:
        server.shutdown()
        server.server_close()

    assert requests_seen == ["/logo.png"], "only the initial request may reach the network"
    assert checked == [f"{origin}/logo.png", metadata_url], checked


@pytest.mark.parametrize("url", [
    "http://example.com:99999/",   # out of range
    "http://example.com:abc/",     # not an integer
    "http://example.com:-1/",
])
def test_malformed_port_raises_fetcherror_not_a_raw_valueerror(url):
    # _check_url runs outside _get's try/except, so parsed.port must not leak
    from gridreport.fetch import _check_url
    with pytest.raises(FetchError, match="invalid URL"):
        _check_url(url)


@pytest.mark.parametrize("value", ["0", "false", "no", "", " "])
def test_allow_private_env_var_requires_an_explicit_truthy_value(monkeypatch, value):
    from gridreport.fetch import _check_url
    monkeypatch.setenv("GRIDREPORT_ALLOW_PRIVATE", value)
    with pytest.raises(FetchError, match="non-public address"):
        _check_url("http://127.0.0.1/")


def test_stylesheet_sampling_dedupes_before_applying_the_limit():
    # Shopify-style themes emit preload+real <link> pairs for the same href;
    # without dedupe the 5-slot budget is spent on duplicates and real
    # stylesheets get dropped, which shifts frequency-ranked color detection
    from gridreport.fetch import find_stylesheet_urls

    html = (
        '<link rel="stylesheet" href="/a.css">'
        '<link rel="stylesheet" href="/a.css">'
        '<link rel="stylesheet" href="/b.css">'
        '<link rel="stylesheet" href="/b.css">'
        '<link rel="stylesheet" href="/c.css">'
    )
    assert find_stylesheet_urls(html, limit=3) == ["/a.css", "/b.css", "/c.css"]

    fixture = (FIXTURES / "manucurist_home.html").read_text(encoding="utf-8", errors="replace")
    sampled = find_stylesheet_urls(fixture)
    assert len(sampled) == 5
    assert len(set(sampled)) == 5, f"duplicates consumed the budget: {sampled}"


# --- functional audit (task 10) regression tests ---

@pytest.mark.parametrize("url", ["http://[::1/", "http://[not-an-ip]/", "https://[:::]/x.css"])
def test_a_malformed_url_is_a_fetcherror_not_a_traceback(url):
    # urlparse raises out of urlsplit on a bad IPv6 literal; the CLI must report
    # it, not print a ValueError traceback
    from gridreport.fetch import _check_url, _same_origin, download_binary

    with pytest.raises(FetchError, match="invalid URL"):
        _check_url(url)
    with pytest.raises(FetchError, match="invalid URL"):
        _same_origin(url, "https://example.com")
    with pytest.raises(FetchError, match="invalid URL"):
        download_binary(url, allowed_origin="https://example.com")


def test_a_broken_stylesheet_href_skips_that_sheet_not_the_whole_scan(monkeypatch):
    import gridreport.fetch as fetch_module

    def fake_get(url):
        if url == "https://example.com/":
            return (
                b'<link rel="stylesheet" href="http://[::1/bad.css">'
                b'<link rel="stylesheet" href="/good.css">'
            )
        return b".x{color:#004e42}"

    monkeypatch.setattr(fetch_module, "_get", fake_get)
    html, css_texts, _ = fetch_site("https://example.com/")
    assert css_texts == [".x{color:#004e42}"]
