# reporting-lite Core Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the `gridreport` CLI's core engine: `gridreport learn <url>` (scan a site, extract brand colors + logo, save a reusable PDF theme) and `gridreport render <file.md>` (turn any markdown file into a styled PDF, optionally using a learned theme).

**Architecture:** A pip-installable Python package (`gridreport`) with two subcommands sharing one rendering engine. `render` is a near-direct port of the already-validated `md-to-pdf` skill's `scripts/convert.py`, generalized to look up themes from `~/.gridreport/templates/<brand>/` instead of a fixed set of 3 bundled themes. `learn` fetches a site (stdlib `urllib`, no new HTTP dependency), extracts colors via regex + frequency ranking and a logo via URL pattern matching, then writes a theme in the same CSS-custom-properties format already proven in the skill's theme files.

**Tech Stack:** Python 3.10+, stdlib only for the package itself (`urllib`, `re`, `json`, `argparse`, `pathlib`), external binaries `pandoc` + `weasyprint` (already required by the reference implementation), `pytest` for tests.

## Global Constraints

- No new pip dependencies beyond `weasyprint` and `pytest` (dev only) — HTTP fetching uses stdlib `urllib`, not `requests`.
- No live network calls in the test suite — all HTTP-dependent code paths are tested via saved HTML fixtures under `tests/fixtures/` or by monkeypatching the fetch layer.
- `--name`/brand values are restricted to `[a-zA-Z0-9_-]+` before ever being used in a filesystem path (path traversal prevention — see Task 5).
- Only `http`/`https` URL schemes are ever fetched (see Task 4).
- Every externally-visible error (`render --brand <unknown>`, `learn` on a site with too few detected colors) prints an actionable message and exits non-zero — never a silent fallback when the user was explicit about what they wanted.

---

### Task 1: Project scaffolding

**Files:**
- Create: `pyproject.toml`
- Create: `gridreport/__init__.py`
- Create: `gridreport/cli.py`
- Create: `gridreport/themes/default.css` (copy of the validated skill theme)
- Test: `tests/test_cli.py`

**Interfaces:**
- Produces: `gridreport.cli.main() -> int`, installable console script `gridreport`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_cli.py
import subprocess
import sys


def test_cli_help_runs():
    result = subprocess.run(
        [sys.executable, "-m", "gridreport.cli", "--help"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0
    assert "learn" in result.stdout
    assert "render" in result.stdout
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_cli.py -v`
Expected: FAIL (no module named gridreport, or ModuleNotFoundError)

- [ ] **Step 3: Write the package files**

```toml
# pyproject.toml
[project]
name = "gridreport"
version = "0.1.0"
description = "Scan a site for brand identity, then render Markdown reports as branded PDFs"
requires-python = ">=3.10"

[project.scripts]
gridreport = "gridreport.cli:main"

[project.optional-dependencies]
dev = ["pytest>=7.0"]

[build-system]
requires = ["setuptools>=61.0"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
include = ["gridreport*"]

[tool.setuptools.package-data]
gridreport = ["themes/*.css"]
```

```python
# gridreport/__init__.py
__version__ = "0.1.0"
```

```python
# gridreport/cli.py
import argparse
import sys


def main() -> int:
    parser = argparse.ArgumentParser(prog="gridreport")
    subparsers = parser.add_subparsers(dest="command", required=True)

    learn_parser = subparsers.add_parser("learn", help="Scan a site and save a brand template")
    learn_parser.add_argument("url")
    learn_parser.add_argument("--name", help="Template name (default: derived from the URL's domain)")
    learn_parser.add_argument("--primary", help="Override the auto-detected primary color (hex)")
    learn_parser.add_argument("--secondary", help="Override the auto-detected secondary color (hex)")
    learn_parser.add_argument("--accent", help="Override the auto-detected accent color (hex)")
    learn_parser.add_argument("--logo", help="Override the auto-detected logo with a local image path")

    render_parser = subparsers.add_parser("render", help="Render a Markdown file to PDF")
    render_parser.add_argument("input")
    render_parser.add_argument("-o", "--output", help="Output PDF path (default: same name, .pdf extension)")
    render_parser.add_argument("--brand", help="Learned brand template to style with (default: bundled default theme)")

    args = parser.parse_args()

    if args.command == "learn":
        from .learn import learn_command
        return learn_command(args)
    if args.command == "render":
        from .render import render_command
        return render_command(args)
    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
```

Copy the validated default theme (exact content from `/home/ahmed/.claude/skills/md-to-pdf/assets/themes/default.css`) to `gridreport/themes/default.css` verbatim — it is already tested and working, no changes needed.

```bash
mkdir -p gridreport/themes
cp /home/ahmed/.claude/skills/md-to-pdf/assets/themes/default.css gridreport/themes/default.css
```

- [ ] **Step 4: Install in editable mode and run test to verify it passes**

Run: `pip install -e ".[dev]" && pytest tests/test_cli.py -v`
Expected: PASS (this will fail at the `import` inside `main()` for `learn`/`render` until Tasks 7/6 exist, but `--help` itself doesn't trigger those imports, so this specific test passes now)

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml gridreport/ tests/test_cli.py
git commit -m "Scaffold gridreport package with CLI skeleton and bundled default theme"
```

---

### Task 2: Color extraction

**Files:**
- Create: `gridreport/extract.py`
- Test: `tests/test_extract.py`

**Interfaces:**
- Produces: `extract_colors(texts: list[str], max_colors: int = 3) -> list[str]` (lowercase hex strings, most frequent non-grayscale first)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_extract.py
from gridreport.extract import extract_colors


def test_extract_colors_ranks_by_frequency_and_excludes_grayscale():
    texts = [
        '<div style="color: #004E42">A</div>' * 5,
        '<div style="color: #FD7BDF">B</div>' * 3,
        '<div style="color: #FFFFFF">white noise</div>' * 20,
        '<div style="color: #000000">black noise</div>' * 20,
        '<div style="color: #20124d">C</div>' * 1,
    ]
    result = extract_colors(texts, max_colors=3)
    assert result == ["#004e42", "#fd7bdf", "#20124d"]


def test_extract_colors_returns_fewer_than_max_when_input_is_sparse():
    result = extract_colors(["#111827 body text only"], max_colors=3)
    assert result == []  # #111827 is near-grayscale (low r/g/b spread), correctly excluded


def test_extract_colors_handles_no_colors_at_all():
    result = extract_colors(["<div class=\"bg-brand-600\">no hex here</div>"], max_colors=3)
    assert result == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_extract.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'gridreport.extract'`

- [ ] **Step 3: Write minimal implementation**

```python
# gridreport/extract.py
import re
from collections import Counter

HEX_COLOR_RE = re.compile(r"#[0-9a-fA-F]{6}\b")
LOGO_IMG_LINK_RE = re.compile(r'<(?:img|link)[^>]+(?:src|href)="([^"]*logo[^"]*)"', re.IGNORECASE)
APPLE_TOUCH_ICON_RE = re.compile(r'<link[^>]+rel="apple-touch-icon"[^>]+href="([^"]+)"', re.IGNORECASE)
FAVICON_RE = re.compile(r'<link[^>]+rel="(?:shortcut )?icon"[^>]+href="([^"]+)"', re.IGNORECASE)
OG_IMAGE_RE = re.compile(r'<meta[^>]+property="og:image"[^>]+content="([^"]+)"', re.IGNORECASE)

GRAYSCALE_THRESHOLD = 12  # max channel spread (r,g,b) below which a color counts as "grayscale noise"


def _is_grayscale(hex_color: str) -> bool:
    hex_color = hex_color.lstrip("#")
    r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
    return max(r, g, b) - min(r, g, b) <= GRAYSCALE_THRESHOLD


def extract_colors(texts: list[str], max_colors: int = 3) -> list[str]:
    counts: Counter[str] = Counter()
    for text in texts:
        for match in HEX_COLOR_RE.findall(text):
            normalized = match.lower()
            if not _is_grayscale(normalized):
                counts[normalized] += 1
    return [color for color, _ in counts.most_common(max_colors)]


def extract_logo_url(html: str) -> str | None:
    match = LOGO_IMG_LINK_RE.search(html)
    if match:
        return match.group(1)
    for pattern in (APPLE_TOUCH_ICON_RE, FAVICON_RE, OG_IMAGE_RE):
        match = pattern.search(html)
        if match:
            return match.group(1)
    return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_extract.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add gridreport/extract.py tests/test_extract.py
git commit -m "Add color and logo extraction from HTML/CSS text"
```

---

### Task 3: Logo URL extraction against real fixtures

**Files:**
- Modify: `tests/test_extract.py`

**Interfaces:**
- Consumes: `extract_logo_url` from Task 2 (already implemented — this task adds coverage against real-world HTML, which may surface bugs the synthetic tests in Task 2 didn't catch, e.g. attribute ordering).

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_extract.py
from pathlib import Path
from gridreport.extract import extract_logo_url, extract_colors

FIXTURES = Path(__file__).parent / "fixtures"


def test_extract_logo_url_finds_real_manucurist_logo():
    html = (FIXTURES / "manucurist_home.html").read_text(encoding="utf-8", errors="replace")
    logo_url = extract_logo_url(html)
    assert logo_url is not None
    assert "logo" in logo_url.lower()


def test_extract_logo_url_finds_real_shopy_science_logo():
    html = (FIXTURES / "shopy_science_home.html").read_text(encoding="utf-8", errors="replace")
    logo_url = extract_logo_url(html)
    assert logo_url is not None
    assert "logo" in logo_url.lower()


def test_extract_colors_finds_real_manucurist_palette():
    html = (FIXTURES / "manucurist_home.html").read_text(encoding="utf-8", errors="replace")
    colors = extract_colors([html], max_colors=3)
    assert "#004e42" in colors  # the real brand green, confirmed by hand on 2026-08-03


def test_extract_colors_finds_nothing_on_tailwind_style_site():
    html = (FIXTURES / "no_colors_home.html").read_text(encoding="utf-8", errors="replace")
    colors = extract_colors([html], max_colors=3)
    assert colors == []
```

- [ ] **Step 2: Run test to verify it fails or passes**

Run: `pytest tests/test_extract.py -v`
Expected: these should PASS immediately since Task 2's implementation already handles this — this task exists to lock in real-world behavior as a regression test, not to add new code. If any of these fail, the extraction regexes need adjusting to handle the real fixture's actual markup before moving on.

- [ ] **Step 3: (only if Step 2 failed) fix `extract.py` until all fixture-based tests pass, then re-run**

- [ ] **Step 4: Commit**

```bash
git add tests/test_extract.py
git commit -m "Lock in extraction behavior against real site fixtures"
```

---

### Task 4: Safe site fetching

**Files:**
- Create: `gridreport/fetch.py`
- Test: `tests/test_fetch.py`

**Interfaces:**
- Produces: `FetchError(Exception)`, `fetch_site(url: str) -> tuple[str, list[str], str]` (html, css_texts, base_origin), `download_binary(url: str, allowed_origin: str) -> Path`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_fetch.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_fetch.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'gridreport.fetch'`

- [ ] **Step 3: Write minimal implementation**

```python
# gridreport/fetch.py
import re
import tempfile
import urllib.parse
import urllib.request
from pathlib import Path

ALLOWED_SCHEMES = {"http", "https"}
MAX_RESPONSE_BYTES = 5_000_000
REQUEST_TIMEOUT = 10
USER_AGENT = "gridreport-learn/0.1"

CSS_LINK_RE = re.compile(r'<link[^>]+rel="stylesheet"[^>]+href="([^"]+)"', re.IGNORECASE)


class FetchError(Exception):
    pass


def _get(url: str) -> bytes:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ALLOWED_SCHEMES:
        raise FetchError(f"unsupported URL scheme {parsed.scheme!r} (only http/https allowed)")
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as response:
            data = response.read(MAX_RESPONSE_BYTES + 1)
    except OSError as exc:
        raise FetchError(f"request to {url} failed: {exc}") from exc
    if len(data) > MAX_RESPONSE_BYTES:
        raise FetchError(f"response from {url} exceeded {MAX_RESPONSE_BYTES} bytes, aborting")
    return data


def fetch_site(url: str) -> tuple[str, list[str], str]:
    """Fetch homepage HTML and same-origin linked CSS (one level deep, max 5 stylesheets)."""
    html = _get(url).decode("utf-8", errors="replace")
    parsed = urllib.parse.urlparse(url)
    base_origin = f"{parsed.scheme}://{parsed.netloc}"

    css_texts = []
    for css_url in CSS_LINK_RE.findall(html)[:5]:
        absolute = urllib.parse.urljoin(url, css_url)
        if not absolute.startswith(base_origin):
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
    if not url.startswith(allowed_origin):
        raise FetchError(f"refusing to download from a different origin than {allowed_origin}: {url}")
    data = _get(url)
    suffix = Path(parsed.path).suffix or ".png"
    tmp_path = Path(tempfile.mkdtemp()) / f"logo{suffix}"
    tmp_path.write_bytes(data)
    return tmp_path
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_fetch.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add gridreport/fetch.py tests/test_fetch.py
git commit -m "Add safe site fetching (scheme allowlist, same-origin CSS, size/timeout caps)"
```

*(Note for Task 9, the security audit: this task deliberately does not yet block requests to private/internal IP ranges (e.g. `http://192.168.1.1/`, `http://169.254.169.254/` cloud metadata, `http://localhost/`) — only URL *scheme* is checked, not the resolved IP a hostname points to. The audit task verifies whether that gap matters for this tool's actual usage and adds resolution-based blocking if so.)*

---

### Task 5: Brand name sanitization and template storage

**Files:**
- Create: `gridreport/template.py`
- Test: `tests/test_template.py`

**Interfaces:**
- Produces: `TEMPLATES_ROOT: Path`, `sanitize_brand_name(name: str) -> str` (raises `ValueError`), `write_template(template_dir: Path, brand: str, source_url: str, colors: dict, logo_src: Path | None) -> None`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_template.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_template.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'gridreport.template'`

- [ ] **Step 3: Write minimal implementation**

```python
# gridreport/template.py
import json
import re
from datetime import datetime, timezone
from pathlib import Path

TEMPLATES_ROOT = Path.home() / ".gridreport" / "templates"

BRAND_NAME_RE = re.compile(r"[a-zA-Z0-9_-]+")

THEME_CSS_TEMPLATE = """/* {brand} — generated by gridreport learn on {learned_at} from {source_url} */
:root {{
  --primary: {primary};
  --secondary: {secondary};
  --accent: {accent};
  --text: #262626;
  --muted: #6b7280;
  --border: #dcdfe3;
  --code-bg: #f4f5f7;
}}

@page {{
  size: A4;
  margin: 3cm 2cm 2.4cm 2cm;
  @top-center {{ content: element(pageHeader); }}
  @bottom-center {{
    content: "Page " counter(page) " of " counter(pages);
    font-family: -apple-system, "Helvetica Neue", Arial, sans-serif;
    font-size: 8.5pt;
    color: var(--muted);
  }}
}}

#page-header {{
  position: running(pageHeader);
  border-bottom: 1.5pt solid var(--accent);
  padding-bottom: 6pt;
  width: 100%;
  overflow: hidden;
}}
#page-header img {{ height: 20pt; float: left; }}
#page-header .doc-title {{
  float: right;
  max-width: 70%;
  line-height: 20pt;
  font-family: -apple-system, "Helvetica Neue", Arial, sans-serif;
  font-size: 9pt;
  color: var(--primary);
  font-weight: 600;
  text-align: right;
}}

body {{
  font-family: -apple-system, "Helvetica Neue", Arial, sans-serif;
  font-size: 10.5pt;
  line-height: 1.55;
  color: var(--text);
}}

h1, h2, h3, h4 {{ page-break-after: avoid; break-after: avoid; }}
h1 {{
  color: var(--primary);
  font-size: 21pt;
  border-bottom: 2.5pt solid var(--accent);
  padding-bottom: 6pt;
  margin-top: 0;
}}
h2 {{
  color: var(--primary);
  font-size: 14.5pt;
  margin-top: 22pt;
  border-bottom: 0.75pt solid var(--border);
  padding-bottom: 3pt;
}}
h3 {{ color: var(--secondary); font-size: 12pt; margin-top: 16pt; }}
h4 {{ color: var(--primary); font-size: 10.5pt; margin-top: 12pt; }}

p {{ orphans: 3; widows: 3; }}
a {{ color: var(--secondary); text-decoration: none; }}

table {{
  width: 100%;
  table-layout: auto;
  border-collapse: collapse;
  margin: 12pt 0;
  font-size: 9.5pt;
}}
thead {{ display: table-header-group; }}
tr {{ page-break-inside: avoid; break-inside: avoid; }}
th {{
  background: var(--primary);
  color: #ffffff;
  text-align: left;
  padding: 6pt 8pt;
  font-weight: 600;
  overflow-wrap: break-word;
}}
td {{ padding: 5pt 8pt; border-bottom: 0.5pt solid var(--border); vertical-align: top; overflow-wrap: break-word; }}
td code, th code {{ overflow-wrap: anywhere; word-break: break-all; }}
tr:nth-child(even) td {{ background: #fafafa; }}

code {{
  font-family: "SF Mono", "Consolas", "Menlo", monospace;
  font-size: 9pt;
  background: var(--code-bg);
  padding: 1.5pt 4pt;
  border-radius: 3pt;
}}
pre {{
  background: var(--code-bg);
  border-left: 3pt solid var(--accent);
  padding: 8pt 10pt;
  font-size: 8.5pt;
  line-height: 1.4;
  overflow-wrap: break-word;
  white-space: pre-wrap;
  page-break-inside: avoid;
  break-inside: avoid;
  border-radius: 0 4pt 4pt 0;
}}
pre code {{ background: none; padding: 0; }}

blockquote {{
  border-left: 3pt solid var(--accent);
  margin: 10pt 0;
  padding: 4pt 12pt;
  color: var(--muted);
  font-style: italic;
}}

hr {{ border: none; border-top: 0.75pt solid var(--border); margin: 18pt 0; }}
ul, ol {{ margin: 6pt 0; padding-left: 20pt; }}
li {{ margin: 3pt 0; }}
strong {{ color: var(--primary); }}
"""


def sanitize_brand_name(name: str) -> str:
    if not BRAND_NAME_RE.fullmatch(name):
        raise ValueError(
            f"invalid brand name {name!r}: only letters, numbers, hyphens, and underscores are allowed"
        )
    return name


def write_template(
    template_dir: Path,
    brand: str,
    source_url: str,
    colors: dict,
    logo_src: Path | None,
) -> None:
    template_dir.mkdir(parents=True, exist_ok=True)
    learned_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    logo_filename = None
    if logo_src is not None:
        logo_filename = f"logo{logo_src.suffix}"
        (template_dir / logo_filename).write_bytes(logo_src.read_bytes())

    css = THEME_CSS_TEMPLATE.format(brand=brand, learned_at=learned_at, source_url=source_url, **colors)
    (template_dir / "theme.css").write_text(css, encoding="utf-8")

    meta = {
        "brand": brand,
        "source_url": source_url,
        "learned_at": learned_at,
        "colors": colors,
        "logo_file": logo_filename,
    }
    (template_dir / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_template.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add gridreport/template.py tests/test_template.py
git commit -m "Add brand name sanitization and template file writer"
```

---

### Task 6: Render command (port from md-to-pdf skill)

**Files:**
- Create: `gridreport/render.py`
- Test: `tests/test_render.py`

**Interfaces:**
- Consumes: `TEMPLATES_ROOT` from Task 5 (`gridreport.template`)
- Produces: `render_command(args) -> int`, `resolve_theme(brand: str | None) -> tuple[Path, Path | None]`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_render.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_render.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'gridreport.render'`

- [ ] **Step 3: Write minimal implementation**

```python
# gridreport/render.py
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from .template import TEMPLATES_ROOT, sanitize_brand_name

PACKAGE_DIR = Path(__file__).resolve().parent
DEFAULT_THEME_CSS = PACKAGE_DIR / "themes" / "default.css"

HEADER_TEMPLATE = """<div id="page-header">{logo_html}<span class="doc-title">{title}</span></div>"""


def check_deps() -> None:
    missing = []
    if not shutil.which("pandoc"):
        missing.append(("pandoc", "sudo apt-get install -y pandoc"))
    if not shutil.which("weasyprint"):
        missing.append(("weasyprint", "pip install --user weasyprint"))
    if missing:
        print("Missing required tools:", file=sys.stderr)
        for name, cmd in missing:
            print(f"  {name}: install with `{cmd}`", file=sys.stderr)
        sys.exit(1)


def extract_title(md_path: Path) -> str:
    for line in md_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped[2:].strip()
    return md_path.stem.replace("-", " ").replace("_", " ").title()


def resolve_theme(brand: str | None) -> tuple[Path, Path | None]:
    if brand is None:
        return DEFAULT_THEME_CSS, None

    brand = sanitize_brand_name(brand)  # raises ValueError on path-traversal-shaped input, before it ever touches a path
    brand_dir = TEMPLATES_ROOT / brand
    css_path = brand_dir / "theme.css"
    if not css_path.exists():
        available = []
        if TEMPLATES_ROOT.exists():
            available = sorted(p.name for p in TEMPLATES_ROOT.iterdir() if (p / "theme.css").exists())
        available_str = ", ".join(available) if available else "(none learned yet)"
        print(
            f"Unknown brand {brand!r}. Learned brands: {available_str}. "
            f"Run 'gridreport learn <url> --name {brand}' first, or omit --brand for the default theme.",
            file=sys.stderr,
        )
        sys.exit(1)

    logo_path = next(brand_dir.glob("logo.*"), None)
    return css_path, logo_path


def build_header_html(logo_path: Path | None, title: str, tmp_dir: Path) -> Path:
    logo_html = f'<img src="file://{logo_path}" alt="logo" />' if logo_path and logo_path.exists() else ""
    header_html = HEADER_TEMPLATE.format(logo_html=logo_html, title=title)
    header_file = tmp_dir / "header.html"
    header_file.write_text(header_html, encoding="utf-8")
    return header_file


def convert(md_path: Path, out_path: Path, brand: str | None) -> None:
    css_path, logo_path = resolve_theme(brand)
    title = extract_title(md_path)

    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        header_file = build_header_html(logo_path, title, tmp_dir)

        cmd = [
            "pandoc", str(md_path),
            "-o", str(out_path),
            "--pdf-engine=weasyprint",
            "-f", "gfm",
            "--css", str(css_path),
            "--include-before-body", str(header_file),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print("pandoc/weasyprint failed:", file=sys.stderr)
            print(result.stderr, file=sys.stderr)
            sys.exit(1)


def render_command(args) -> int:
    check_deps()
    md_path = Path(args.input).resolve()
    if not md_path.exists():
        print(f"Input file not found: {md_path}", file=sys.stderr)
        return 1
    out_path = Path(args.output).resolve() if args.output else md_path.with_suffix(".pdf")
    try:
        convert(md_path, out_path, args.brand)
    except ValueError as exc:
        print(f"Invalid --brand: {exc}", file=sys.stderr)
        return 1
    print(f"Wrote {out_path}")
    return 0
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_render.py -v`
Expected: PASS (requires `pandoc` and `weasyprint` installed, same as the reference skill — if missing, install per `check_deps()`'s printed instructions before re-running)

- [ ] **Step 5: Commit**

```bash
git add gridreport/render.py tests/test_render.py
git commit -m "Add render command, ported from the validated md-to-pdf skill pipeline"
```

---

### Task 7: Learn command

**Files:**
- Create: `gridreport/learn.py`
- Test: `tests/test_learn.py`

**Interfaces:**
- Consumes: `extract_colors`, `extract_logo_url` (Task 2), `fetch_site`, `download_binary`, `FetchError` (Task 4), `sanitize_brand_name`, `write_template`, `TEMPLATES_ROOT` (Task 5)
- Produces: `learn_command(args) -> int`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_learn.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_learn.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'gridreport.learn'`

- [ ] **Step 3: Write minimal implementation**

```python
# gridreport/learn.py
import sys
import urllib.parse
from pathlib import Path

from .extract import extract_colors, extract_logo_url
from .fetch import fetch_site, download_binary, FetchError
from .template import sanitize_brand_name, write_template, TEMPLATES_ROOT

MIN_DISTINCT_COLORS = 2


def _derive_name(url: str) -> str:
    netloc = urllib.parse.urlparse(url).netloc
    return netloc.replace("www.", "").split(":")[0]


def learn_command(args) -> int:
    brand = sanitize_brand_name(args.name or _derive_name(args.url))

    try:
        html, css_texts, base_origin = fetch_site(args.url)
    except FetchError as exc:
        print(f"Could not fetch {args.url}: {exc}", file=sys.stderr)
        return 1

    detected = extract_colors([html, *css_texts])
    manual_count = sum(1 for v in (args.primary, args.secondary, args.accent) if v)
    if manual_count == 0 and len(detected) < MIN_DISTINCT_COLORS:
        print(
            f"Could not detect at least {MIN_DISTINCT_COLORS} distinct brand colors from {args.url}. "
            "This usually means the site's colors are compiled into a CSS-in-JS bundle or utility-class "
            "framework rather than exposed as literal hex values. Supply colors manually instead:\n"
            f"  gridreport learn {args.url} --name {brand} --primary '#hex' --secondary '#hex'",
            file=sys.stderr,
        )
        return 1

    primary = args.primary or (detected[0] if len(detected) > 0 else "#1e3a5f")
    secondary = args.secondary or (detected[1] if len(detected) > 1 else primary)
    accent = args.accent or (detected[2] if len(detected) > 2 else secondary)

    logo_path = None
    if args.logo:
        logo_path = Path(args.logo).resolve()
        if not logo_path.exists():
            print(f"Logo file not found: {logo_path}", file=sys.stderr)
            return 1
    else:
        logo_url = extract_logo_url(html)
        if logo_url:
            absolute_logo_url = urllib.parse.urljoin(args.url, logo_url)
            try:
                logo_path = download_binary(absolute_logo_url, base_origin)
            except FetchError as exc:
                print(f"Warning: found a logo URL but couldn't download it ({exc}); continuing without a logo.", file=sys.stderr)

    write_template(
        TEMPLATES_ROOT / brand,
        brand=brand,
        source_url=args.url,
        colors={"primary": primary, "secondary": secondary, "accent": accent},
        logo_src=logo_path,
    )
    print(f"Learned brand {brand!r} from {args.url} -> {TEMPLATES_ROOT / brand}")
    return 0
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_learn.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add gridreport/learn.py tests/test_learn.py
git commit -m "Add learn command wiring fetch, extraction, and template writing"
```

---

### Task 8: End-to-end integration test against real fixtures

**Files:**
- Create: `tests/test_integration.py`

**Interfaces:**
- Consumes: everything from Tasks 1–7.

- [ ] **Step 1: Write the failing test**

The `render` half of this test runs `gridreport.cli` in a **separate subprocess**, so monkeypatching `gridreport.render.TEMPLATES_ROOT` in the test process has no effect on it — that module attribute is only ever read inside the subprocess's own fresh import. Instead, point the subprocess's `HOME` at `tmp_path`, so `render.py`'s real `TEMPLATES_ROOT = Path.home() / ".gridreport" / "templates"` resolves under it, and write the learned template to that same `.gridreport/templates` path so both halves agree on where the brand lives:

```python
# tests/test_integration.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_integration.py -v`
Expected: FAIL initially — likely at the `learn_command` assertion if the `templates_root` monkeypatch path doesn't yet match what `render`'s subprocess resolves via `HOME`. Compare the two paths directly if it fails and adjust until they match exactly, then re-run.

- [ ] **Step 3: Fix any remaining path mismatches until the test passes** (this task is integration wiring, not new production code — Tasks 1-7 already contain all the real logic)

- [ ] **Step 4: Run full test suite to verify everything still passes together**

Run: `pytest -v`
Expected: PASS (all tests from Tasks 1-8)

- [ ] **Step 5: Commit**

```bash
git add tests/test_integration.py
git commit -m "Add end-to-end learn-then-render integration test against real site fixtures"
```

---

### Task 9: Security audit (subagent checkpoint)

This is a review-and-fix task, not a new-feature task — dispatch a fresh subagent with no prior context on this conversation, pointed at the codebase, with this exact brief:

> Review the `gridreport` package at `GridReport-lite/gridreport/` for security issues, specifically:
> 1. **SSRF risk in `learn`**: `fetch.py`'s `_get()` checks URL *scheme* (http/https only) but does not check what IP address the hostname actually resolves to. A user (or an automated caller) could point `gridreport learn` at `http://169.254.169.254/` (cloud metadata endpoints), `http://localhost/`, or an internal `192.168.x.x`/`10.x.x.x`/`172.16-31.x.x` address, and the tool will fetch it. Determine whether this matters for how the tool is actually used (a local CLI a user runs against sites *they* choose) versus a real risk (e.g. if this is ever exposed as a service where an untrusted caller supplies the URL). If it's a real risk, add resolution-based blocking: resolve the hostname via `socket.gethostbyname`, check the result against `ipaddress.ip_address(...).is_private`, `.is_loopback`, and `.is_link_local`, and raise `FetchError` if any are true, before connecting.
> 2. **Path traversal**: confirm `sanitize_brand_name` (`template.py`) is actually called on every code path that turns a user-supplied string into a filesystem path — both `--name` in `learn.py` and `--brand` in `render.py`'s `resolve_theme` should reject something shaped like `--brand ../../etc` before it ever reaches `TEMPLATES_ROOT / brand`. Verify this end-to-end through the actual CLI (`python -m gridreport.cli render x.md --brand ../../etc`), not just via the unit tests in isolation, in case the sanitization call and the CLI wiring have drifted apart.
> 3. **Unsafe parsing of untrusted content**: confirm nothing in `extract.py` or `fetch.py` ever evaluates, executes, or otherwise treats fetched HTML/CSS as code (it shouldn't — everything should be plain regex/string matching) — verify this holds, don't just assume it.
> 4. **File write safety**: confirm `write_template` and `download_binary` only ever write inside their intended directories (`~/.gridreport/templates/<sanitized-brand>/` and a fresh `tempfile.mkdtemp()` respectively) and can't be tricked into writing elsewhere.
>
> Fix anything you find. Write your findings and fixes as a short report, and add regression tests for anything you fix.

- [ ] **Step 1: Dispatch the subagent with the brief above**
- [ ] **Step 2: Review its report and the diff it produces**
- [ ] **Step 3: Run the full test suite to confirm nothing broke**

Run: `pytest -v`
Expected: PASS, including any new regression tests the audit added

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "Security audit: SSRF/path-traversal fixes for learn and render"
```

---

### Task 10: Functional audit (subagent checkpoint)

Dispatch a second fresh subagent, no prior context, with this brief:

> Verify the `gridreport` package at `GridReport-lite/gridreport/` actually implements the design spec at `GridReport-lite/docs/superpowers/specs/2026-08-04-reporting-lite-core-design.md`. Specifically check:
> 1. Both commands (`gridreport learn <url>`, `gridreport render <file.md>`) work as specified, including all documented flags (`--name`, `--primary`/`--secondary`/`--accent`/`--logo` overrides on `learn`; `--brand`/`-o` on `render`).
> 2. Error-handling behavior matches the spec exactly: unknown `--brand` lists available brands and exits 1; too-few-detected-colors on `learn` exits 1 with the documented message and does NOT write a partial template directory; missing `pandoc`/`weasyprint` prints install instructions rather than a raw traceback.
> 3. The full test suite passes (`pytest -v`) and actually covers what the spec describes (colors+logo extraction against real fixtures, path-traversal prevention, SSRF scheme checks, end-to-end learn-then-render).
> 4. No scope drift: confirm nothing implements font detection, recursive multi-level crawling, a database/SQLite store, or any web UI/skill/gridscan-plugin code — those are explicitly out of scope per the spec's Non-goals section and belong to separate future sub-projects.
>
> Report any gaps found. Fix them if they're small; if a gap is large enough to need real design discussion, stop and report it rather than improvising a fix.

- [ ] **Step 1: Dispatch the subagent with the brief above**
- [ ] **Step 2: Review its report**
- [ ] **Step 3: Apply any small fixes it made or recommended; flag anything that needs a design discussion instead of surfacing it as already resolved**
- [ ] **Step 4: Run the full test suite one more time**

Run: `pytest -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "Functional audit: verify implementation matches design spec"
```

---

### Task 11: README and packaging check

**Files:**
- Create: `README.md`

- [ ] **Step 1: Write the README**

```markdown
# gridreport

Scan a live site for its brand identity (colors + logo), save it as a reusable
PDF theme, then render any Markdown file into a styled PDF using that theme.

## Install

    pip install -e .

## Usage

    gridreport learn https://example.com --name example
    gridreport render report.md --brand example -o report.pdf

Omit `--brand` to use the bundled generic theme. Override auto-detected
colors/logo with `--primary`/`--secondary`/`--accent`/`--logo` on `learn`,
either to work around a site whose colors couldn't be auto-detected (see the
error message `learn` prints in that case) or to correct a wrong guess.

Templates are saved under `~/.gridreport/templates/<brand>/`.

## Requirements

`pandoc` and `weasyprint` must be installed and on `PATH`. `gridreport render`
prints the exact install command if either is missing.
```

- [ ] **Step 2: Verify a clean install works end to end**

Run:
```bash
python3 -m venv /tmp/gridreport-check
/tmp/gridreport-check/bin/pip install -e /home/ahmed/Documents/GridReport-lite
/tmp/gridreport-check/bin/gridreport --help
```
Expected: help output showing both `learn` and `render` subcommands, no errors.

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "Add README"
```
