from pathlib import Path
from gridreport.extract import extract_colors, extract_logo_url

FIXTURES = Path(__file__).parent / "fixtures"


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
