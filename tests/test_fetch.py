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
