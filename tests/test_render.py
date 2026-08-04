import subprocess
import sys
from pathlib import Path

import pytest
from gridreport.render import resolve_theme
from gridreport.template import TEMPLATES_ROOT


def test_resolve_theme_returns_bundled_default_when_no_brand():
    css_path, logo_path = resolve_theme(None)
    assert css_path.name == "default.css"
    assert logo_path is None


def test_resolve_theme_unknown_brand_exits_with_available_list(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr("gridreport.render.TEMPLATES_ROOT", tmp_path)
    (tmp_path / "known-brand").mkdir()
    (tmp_path / "known-brand" / "theme.css").write_text("/* css */")

    with pytest.raises(SystemExit) as exc_info:
        resolve_theme("does-not-exist")
    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    assert "known-brand" in captured.err


def test_resolve_theme_rejects_path_traversal_in_brand():
    with pytest.raises(ValueError, match="only letters, numbers"):
        resolve_theme("../../etc")


def test_render_produces_valid_multipage_pdf(tmp_path):
    md_file = tmp_path / "sample.md"
    md_file.write_text("# Title\n\n" + ("Paragraph text.\n\n" * 200))
    out_pdf = tmp_path / "sample.pdf"

    result = subprocess.run(
        [sys.executable, "-m", "gridreport.cli", "render", str(md_file), "-o", str(out_pdf)],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    assert out_pdf.exists()

    pdfinfo = subprocess.run(["pdfinfo", str(out_pdf)], capture_output=True, text=True)
    assert pdfinfo.returncode == 0
    assert "Pages:" in pdfinfo.stdout
