import pytest
from gridreport.fetch import fetch_site, download_binary, FetchError


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
