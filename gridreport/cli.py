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
