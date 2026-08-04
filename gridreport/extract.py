import re
from collections import Counter

HEX_COLOR_RE = re.compile(r"#[0-9a-fA-F]{6}\b")

TAG_NAME_RE = re.compile(r"<([a-zA-Z][a-zA-Z0-9]*)\b")
# the lookbehind stops the engine from re-trying every position inside an
# attribute name, which is what makes this linear instead of quadratic
ATTR_RE = re.compile(r'(?<![-\w:.])([-\w:.]+)="([^"]*)"')

ICON_RELS = ("apple-touch-icon", "icon", "shortcut icon")

GRAYSCALE_THRESHOLD = 30  # max channel spread (r,g,b) below which a color counts as "grayscale noise"


def iter_tags(html: str, *names: str):
    """Yield (tag_name, {attr: value}) for each named tag in `html`.

    Splitting on ">" first bounds every regex to one tag's worth of text.
    Matching whole-tag patterns like `<link[^>]+rel="x"[^>]+href="y"` straight
    against a document is O(n^2) in the length of an unclosed tag, so a single
    5 MB page with no ">" in it hangs the scan for hours. This stays linear.
    """
    wanted = {name.lower() for name in names}
    for chunk in html.split(">"):
        start = chunk.rfind("<")
        if start < 0:
            continue
        match = TAG_NAME_RE.match(chunk, start)
        if match is None:
            continue
        tag = match.group(1).lower()
        if tag not in wanted:
            continue
        yield tag, {k.lower(): v for k, v in ATTR_RE.findall(chunk, match.end())}


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
    tags = list(iter_tags(html, "img", "link", "meta"))

    named = [
        value
        for tag, attrs in tags if tag != "meta"
        for key, value in attrs.items()
        if key.endswith(("src", "href")) and "logo" in value.lower()
    ]
    if named:
        # prefer .svg over .png — it scales in PDF output. min() is stable, so
        # among same-format candidates the first in document order still wins.
        # substring, not suffix: real logo URLs carry query strings (?v=1644506438)
        return min(named, key=lambda v: 0 if ".svg" in v.lower() else 1)

    for rel in ICON_RELS:
        for tag, attrs in tags:
            if tag == "link" and attrs.get("rel", "").lower() == rel and attrs.get("href"):
                return attrs["href"]

    for tag, attrs in tags:
        if tag == "meta" and attrs.get("property") == "og:image" and attrs.get("content"):
            return attrs["content"]

    return None
