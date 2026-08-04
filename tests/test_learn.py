import json
from pathlib import Path

import pytest
from gridreport.learn import learn_command


class FakeArgs:
    def __init__(self, url, name=None, primary=None, secondary=None, accent=None, logo=None):
        self.url = url
        self.name = name
        self.primary = primary
        self.secondary = secondary
        self.accent = accent
        self.logo = logo


def test_learn_writes_template_from_fixture_html(monkeypatch, tmp_path):
    monkeypatch.setattr("gridreport.learn.TEMPLATES_ROOT", tmp_path)
    fixture_html = (
        '<div style="color:#004E42">a</div>' * 5
        + '<div style="color:#FD7BDF">b</div>' * 3
        + '<img src="/logo.png" alt="logo">'
    )
    monkeypatch.setattr("gridreport.learn.fetch_site", lambda url: (fixture_html, [], "https://example.com"))
    monkeypatch.setattr("gridreport.learn.download_binary", lambda url, origin: None)

    exit_code = learn_command(FakeArgs(url="https://example.com", name="testbrand"))

    assert exit_code == 0
    meta = json.loads((tmp_path / "testbrand" / "meta.json").read_text())
    assert meta["colors"]["primary"] == "#004e42"
    assert (tmp_path / "testbrand" / "theme.css").exists()


def test_learn_fails_clearly_when_too_few_colors_detected(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr("gridreport.learn.TEMPLATES_ROOT", tmp_path)
    monkeypatch.setattr("gridreport.learn.fetch_site", lambda url: ("<div>no colors</div>", [], "https://example.com"))

    exit_code = learn_command(FakeArgs(url="https://example.com", name="sparse"))

    assert exit_code == 1
    assert "Could not detect" in capsys.readouterr().err
    assert not (tmp_path / "sparse").exists()


def test_learn_accepts_manual_color_override_even_with_no_detected_colors(monkeypatch, tmp_path):
    monkeypatch.setattr("gridreport.learn.TEMPLATES_ROOT", tmp_path)
    monkeypatch.setattr("gridreport.learn.fetch_site", lambda url: ("<div>no colors</div>", [], "https://example.com"))

    exit_code = learn_command(FakeArgs(url="https://example.com", name="manual", primary="#123456"))

    assert exit_code == 0
    meta = json.loads((tmp_path / "manual" / "meta.json").read_text())
    assert meta["colors"]["primary"] == "#123456"


def test_learn_rejects_a_path_traversal_name_cleanly(monkeypatch, tmp_path, capsys):
    # must be a clean exit code, not an uncaught ValueError traceback
    monkeypatch.setattr("gridreport.learn.TEMPLATES_ROOT", tmp_path)
    monkeypatch.setattr("gridreport.learn.fetch_site", lambda url: pytest.fail("must not fetch"))

    for hostile in ("../../etc", "foo/../../bar", ".", "et\x00c"):
        assert learn_command(FakeArgs(url="https://example.com", name=hostile)) == 1
        assert "Invalid --name" in capsys.readouterr().err
    assert list(tmp_path.iterdir()) == []


# --- functional audit (task 10) regression tests ---

@pytest.mark.parametrize("url,expected", [
    ("https://manucurist.com", "manucurist"),
    ("https://www.manucurist.com/en", "manucurist"),
    ("https://shopy-science.io", "shopy-science"),
    ("http://localhost:8000/index.html", "localhost"),
    # a capitalized URL must still derive a lowercase brand: a case-sensitive
    # removeprefix leaves 'WWW.' in place, and a 'Manucurist' template dir would
    # not match `render --brand manucurist` on a case-sensitive filesystem
    ("https://Manucurist.com", "manucurist"),
    ("https://WWW.Manucurist.com", "manucurist"),
])
def test_derive_name_yields_a_name_the_sanitizer_accepts(url, expected):
    # the bare netloc keeps the TLD's dot, which sanitize_brand_name rejects - so
    # `learn <url>` with no --name used to fail on every real domain
    from gridreport.learn import _derive_name
    from gridreport.template import sanitize_brand_name

    assert _derive_name(url) == expected
    assert sanitize_brand_name(_derive_name(url)) == expected


def test_learn_without_a_name_flag_derives_the_brand_from_the_url(monkeypatch, tmp_path):
    monkeypatch.setattr("gridreport.learn.TEMPLATES_ROOT", tmp_path)
    html = '<div style="color:#004E42">a</div>' * 5 + '<div style="color:#FD7BDF">b</div>' * 3
    monkeypatch.setattr("gridreport.learn.fetch_site", lambda url: (html, [], "https://manucurist.com"))

    assert learn_command(FakeArgs(url="https://www.manucurist.com/")) == 0
    assert (tmp_path / "manucurist" / "theme.css").exists()


def test_a_malformed_logo_href_continues_without_a_logo(monkeypatch, tmp_path, capsys):
    # the scanned page supplies the logo href, and urljoin raises out of urlsplit
    # on a bad IPv6 literal - it must degrade to the existing warning path, not
    # crash the scan with a raw ValueError
    monkeypatch.setattr("gridreport.learn.TEMPLATES_ROOT", tmp_path)
    html = (
        '<img src="http://[::1/logo.png" alt="logo">'
        + '<div style="color:#004E42">a</div>' * 5
        + '<div style="color:#FD7BDF">b</div>' * 3
    )
    monkeypatch.setattr("gridreport.learn.fetch_site", lambda url: (html, [], "https://example.com"))

    assert learn_command(FakeArgs(url="https://example.com", name="badlogo")) == 0
    assert "continuing without a logo" in capsys.readouterr().err
    # the template is still written, just logo-less
    assert json.loads((tmp_path / "badlogo" / "meta.json").read_text())["logo_file"] is None
    assert not list((tmp_path / "badlogo").glob("logo.*"))
