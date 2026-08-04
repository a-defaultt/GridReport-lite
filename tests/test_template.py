import json
import pytest
from gridreport.template import sanitize_brand_name, write_template


def test_sanitize_brand_name_accepts_normal_names():
    assert sanitize_brand_name("manucurist") == "manucurist"
    assert sanitize_brand_name("shopy-science") == "shopy-science"


def test_sanitize_brand_name_rejects_path_traversal():
    with pytest.raises(ValueError, match="only letters, numbers"):
        sanitize_brand_name("../../etc/passwd")


def test_sanitize_brand_name_rejects_path_separators():
    with pytest.raises(ValueError):
        sanitize_brand_name("foo/bar")


def test_write_template_creates_css_and_meta(tmp_path):
    template_dir = tmp_path / "acme"
    write_template(
        template_dir,
        brand="acme",
        source_url="https://acme.example",
        colors={"primary": "#111111", "secondary": "#222222", "accent": "#333333"},
        logo_src=None,
    )
    assert (template_dir / "theme.css").exists()
    css = (template_dir / "theme.css").read_text()
    assert "--primary: #111111;" in css
    meta = json.loads((template_dir / "meta.json").read_text())
    assert meta["brand"] == "acme"
    assert meta["colors"]["primary"] == "#111111"
    assert meta["logo_file"] is None
