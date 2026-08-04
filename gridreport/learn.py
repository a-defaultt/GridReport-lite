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
    try:
        brand = sanitize_brand_name(args.name or _derive_name(args.url))
    except ValueError as exc:
        print(f"Invalid --name: {exc}", file=sys.stderr)
        return 1

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
