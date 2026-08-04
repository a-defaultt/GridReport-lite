# reporting-lite core engine — design spec

**Date**: 2026-08-04
**Status**: Approved for implementation
**Scope**: Core `gridreport` CLI only (`learn` + `render`). The web UI, Claude Code skill, and gridscan plugin are separate, later sub-projects that will each consume this core — not designed or built here.

## Background

This project exists because doing this by hand once (curl a site, grep hex colors, download a logo, hand-write a CSS theme, wire it into a pandoc+weasyprint pipeline) worked well for two real brands (Manucurist, shopy-science.io) during the development of an earlier Claude Code skill (`md-to-pdf`). This project automates that manual process into a standalone, reusable tool.

It intentionally supersedes the pre-existing `/home/ahmed/Documents/GridReport` folder's scope for now. That folder describes an enterprise "report compiler platform" (custom IR, compiler passes, plugin SDK, multi-language SDKs, Postgres/Redis/MinIO infra, 19 RFCs) with zero actual implementation. That vision is deferred to a separate "reporting-pro" project plan, meant to be picked up in a different Claude session only if/when real usage of reporting-lite justifies that scale. This project lives in a fresh folder (`GridReport-lite`) and does not touch or depend on the old `GridReport` folder's docs or scaffolding.

## Goals

- `gridreport learn <url>`: scan a live site, extract its brand colors and logo, save a reusable PDF theme.
- `gridreport render <file.md>`: turn any markdown file into a well-typeset PDF, optionally styled with a learned brand theme.
- Both distributed as one pip-installable CLI.

## Non-goals (v1)

- Font detection/extraction (colors + logo only — see rationale below).
- Recursive site crawling (only the homepage + same-origin linked CSS, one level deep).
- A web UI, Claude Code skill wrapper, or gridscan integration (separate future sub-projects).
- Any compatibility with the old GridReport RFCs/IR/compiler concepts.

## Architecture

```
GridReport-lite/
├── gridreport/
│   ├── __init__.py
│   ├── cli.py           # argparse entry point: `gridreport learn|render`
│   ├── learn.py         # site -> brand template extraction
│   ├── render.py        # md -> PDF (ported from md-to-pdf skill's scripts/convert.py)
│   └── themes/
│       └── default.css  # fallback theme, ships with the package
├── pyproject.toml       # console_scripts entry point: gridreport = gridreport.cli:main
├── tests/
│   ├── fixtures/        # saved local HTML snapshots, no live network calls in tests
│   └── ...
└── docs/superpowers/specs/   # this file and future design docs
```

Two commands sharing one rendering engine:

- **`gridreport learn <url> [--name <brand>] [--primary '#hex'] [--secondary '#hex'] [--accent '#hex'] [--logo <path>]`**
  Fetches the site, extracts colors + logo (unless overridden by flags), writes `~/.gridreport/templates/<brand>/{theme.css, logo.{png,svg}, meta.json}`. `--name` defaults to the domain name if omitted.

- **`gridreport render <file.md> [--brand <name>] [-o output.pdf]`**
  Same pandoc + weasyprint pipeline validated in today's `md-to-pdf` skill (table page-break handling via `thead`/`tr` rules, running header/footer via CSS Paged Media, code-block wrapping, etc.), pointed at a learned theme's `theme.css` instead of one of a fixed set of 3 bundled themes. Omitting `--brand` uses the packaged `themes/default.css`.

`render.py` is a near-direct port of `scripts/convert.py` from the `md-to-pdf` skill — that logic is already validated against a real long report and two synthetic edge-case fixtures, so this is relocation into an installable package, not a rewrite. The one generalization: "which theme directory" goes from a fixed choice of 3 bundled themes to "any folder under `~/.gridreport/templates/`."

## `learn` extraction heuristic

**Colors**: fetch the homepage HTML; regex for `#[0-9a-fA-F]{6}` across the raw HTML *and* any same-origin linked `.css` files (one level deep, no recursive crawling). Exclude near-white/near-black/pure-grayscale noise (`#fff`/`#000` and anything within a small perceptual distance of pure gray), since those dominate every site's hex count without being brand-distinctive. Rank the remainder by frequency; take the top 1–3 distinct hues as primary/secondary/accent.

**Logo**: check `img`/`link` tags whose `src`/`href` contains the substring "logo" first (this alone found the correct logo for both sites tested manually). If none found, fall back in order to `apple-touch-icon` → standard `favicon` → `og:image` meta tag. Prefer `.svg` over `.png` when both are available (scales better in PDF output).

**Known limitation (v1, stated explicitly rather than silently papered over)**: this approach only works when a site exposes real hex color values in fetched HTML/CSS. It will not reliably work on sites built with CSS-in-JS or compiled utility-class frameworks (e.g. Tailwind), where colors never appear as literal hex strings in what gets fetched via a plain HTTP GET. `learn` must detect this failure mode — fewer than 2 distinct non-grayscale hex colors found — and **exit with a clear, actionable error** rather than silently generating a template from whatever noise it happened to find.

**Manual override**: the `--primary`/`--secondary`/`--accent`/`--logo` flags on `learn` let a user supply values directly, either to work around detection failure or to correct a wrong auto-detected value. Supplying a flag skips auto-detection for that specific field only.

## Storage format

`~/.gridreport/templates/<brand>/meta.json`:
```json
{
  "brand": "manucurist",
  "source_url": "https://manucurist.com",
  "learned_at": "2026-08-04T09:00:00Z",
  "colors": {"primary": "#004E42", "secondary": "#20124d", "accent": "#FD7BDF"},
  "logo_file": "logo.png"
}
```

`theme.css` in the same folder is the real stylesheet: CSS custom properties driven by the colors above, plus the fixed structural rules that don't vary by brand (table `page-break-inside`/`thead` repeat behavior, running header/footer via CSS Paged Media, code-block wrapping via `overflow-wrap`, etc. — the same rules validated in the `md-to-pdf` skill's theme CSS files).

## Error handling

- `render --brand <name>` where `<name>` doesn't exist under `~/.gridreport/templates/`: exit with an error that **lists the brands that do exist** (e.g. `Unknown brand 'foo'. Learned brands: manucurist, shopy-science. Run 'gridreport learn <url>' first, or omit --brand for the default theme.`). No silent fallback to the default theme when a brand was explicitly requested — that would hide a typo as a styling problem instead of surfacing a clear, correct error.
- `learn` on a URL where fewer than 2 distinct brand-like colors are found: exit with an error explaining the limitation (see above) and pointing at the manual-override flags.
- Missing `pandoc`/`weasyprint` at render time: same check-and-instruct behavior as the `md-to-pdf` skill (print the exact install command, don't auto-install).

## Testing

- Unit tests for the extraction heuristic run against **saved local HTML fixtures** (snapshots of the Manucurist and shopy-science.io homepages already fetched during today's manual work, plus one synthetic "no hex colors, Tailwind-style" fixture to verify the failure-detection path). No live network calls in the test suite — tests aren't flaky or dependent on those real sites staying unchanged.
- One integration test: run `learn` against a fixture, then `render` against a sample `.md` file, and check the output is a valid multi-page PDF (`pdfinfo` exit 0 + expected page count) — mirroring the verification approach already used during the `md-to-pdf` skill's development.

## Relationship to future sub-projects (not designed here)

- **Web UI**: a small local web app in the style of the eval-viewer tool (clean, minimal, no heavy framework) that lets someone upload a `.md` file, pick or learn a brand, and download the rendered PDF. Calls the core engine; does not duplicate its logic.
- **Claude Code skill**: lets Claude invoke `learn`/`render` conversationally. Supersedes today's `md-to-pdf` skill, since this core engine does everything that skill did plus brand-learning.
- **gridscan plugin**: an optional post-scan step so any `shopyscan` run can auto-render its `.report.md` as a branded PDF, by calling `gridreport render` on the scan's own report output.

Each of the above gets its own short brainstorm-and-build cycle once the core engine exists and works.
