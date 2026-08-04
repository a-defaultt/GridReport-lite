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
