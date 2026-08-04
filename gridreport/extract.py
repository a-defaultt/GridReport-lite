import re
from collections import Counter

HEX_COLOR_RE = re.compile(r"#[0-9a-fA-F]{6}\b")
LOGO_IMG_LINK_RE = re.compile(r'<(?:img|link)[^>]+(?:src|href)="([^"]*logo[^"]*)"', re.IGNORECASE)
APPLE_TOUCH_ICON_RE = re.compile(r'<link[^>]+rel="apple-touch-icon"[^>]+href="([^"]+)"', re.IGNORECASE)
FAVICON_RE = re.compile(r'<link[^>]+rel="(?:shortcut )?icon"[^>]+href="([^"]+)"', re.IGNORECASE)
OG_IMAGE_RE = re.compile(r'<meta[^>]+property="og:image"[^>]+content="([^"]+)"', re.IGNORECASE)

GRAYSCALE_THRESHOLD = 30  # max channel spread (r,g,b) below which a color counts as "grayscale noise"


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
