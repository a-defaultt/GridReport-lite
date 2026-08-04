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
