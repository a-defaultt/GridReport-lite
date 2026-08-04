import json
import os
import subprocess
import sys
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"


def test_learn_then_render_end_to_end(monkeypatch, tmp_path):
    templates_root = tmp_path / ".gridreport" / "templates"
    monkeypatch.setattr("gridreport.learn.TEMPLATES_ROOT", templates_root)

    manucurist_html = (FIXTURES / "manucurist_home.html").read_text(encoding="utf-8", errors="replace")
    monkeypatch.setattr("gridreport.learn.fetch_site", lambda url: (manucurist_html, [], "https://manucurist.com"))
    monkeypatch.setattr("gridreport.learn.download_binary", lambda url, origin: None)

    from gridreport.learn import learn_command

    class FakeArgs:
        url = "https://manucurist.com"
        name = "manucurist"
        primary = secondary = accent = logo = None

    assert learn_command(FakeArgs()) == 0
    assert (templates_root / "manucurist" / "theme.css").exists()

    meta = json.loads((templates_root / "manucurist" / "meta.json").read_text())
    assert meta["colors"]["primary"] == "#004e42"

    md_file = tmp_path / "report.md"
    md_file.write_text("# A Real Report\n\n" + ("Some paragraph content.\n\n" * 100) + "\n| a | b |\n|---|---|\n| 1 | 2 |\n")
    out_pdf = tmp_path / "report.pdf"

    result = subprocess.run(
        [sys.executable, "-m", "gridreport.cli", "render", str(md_file), "-o", str(out_pdf), "--brand", "manucurist"],
        capture_output=True, text=True,
        env={**os.environ, "HOME": str(tmp_path)},
    )
    assert result.returncode == 0, result.stderr
    assert out_pdf.exists()

    pdfinfo = subprocess.run(["pdfinfo", str(out_pdf)], capture_output=True, text=True)
    assert pdfinfo.returncode == 0
    pages_line = next(line for line in pdfinfo.stdout.splitlines() if line.startswith("Pages:"))
    assert int(pages_line.split(":")[1].strip()) >= 2
