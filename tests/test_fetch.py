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
