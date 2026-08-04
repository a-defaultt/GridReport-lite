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
