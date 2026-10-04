"""Prepare an official page for `onevisit ingest --html`: keep only the article text.

    .venv/bin/python data/tools/clean_html.py raw.html clean.html                 # <main>, else <article>
    .venv/bin/python data/tools/clean_html.py raw.html clean.html --select article
    .venv/bin/python data/tools/clean_html.py raw.html clean.html --unescape-inner # elixForms pages
    .venv/bin/python data/tools/clean_html.py file.pdf clean.html --pdf            # needs pdftotext

    .venv/bin/onevisit ingest <id> --html clean.html --url <official url>

Why: the saved page must hold the words a requirement quotes, and nothing else.
This script never changes a word. It only:
  - keeps the main content element (menus, banners, cookie notices and "read also"
    lists stay out);
  - removes bold and italic markers (<strong>, <b>, <em>, <i>) so a quote copied
    from the page does not need Markdown asterisks in the middle of a sentence;
  - for the City's online form pages (elixForms), decodes the description that the
    page ships as escaped HTML and renders in the browser;
  - for a PDF, extracts the text with pdftotext and keeps one paragraph per line.
Run it with the kit environment (.venv), which has BeautifulSoup.
"""

import argparse
import html
import pathlib
import subprocess
import sys

from bs4 import BeautifulSoup

EMPHASIS = ("strong", "b", "em", "i")


def from_pdf(path: pathlib.Path) -> str:
    """Text of a PDF as simple HTML, one paragraph per line."""
    text = subprocess.run(
        ["pdftotext", "-raw", "-enc", "UTF-8", str(path), "-"], check=True, capture_output=True, text=True
    ).stdout
    paragraphs = [f"<p>{html.escape(line.strip())}</p>" for line in text.splitlines() if line.strip()]
    return "<main>\n" + "\n".join(paragraphs) + "\n</main>"


def from_html(raw: str, select: str | None, unescape_inner: bool) -> str:
    """The main content element, with emphasis tags unwrapped."""
    soup = BeautifulSoup(raw, "html.parser")
    if unescape_inner:
        # elixForms puts the form description in the page as escaped HTML text.
        for node in soup.find_all(string=lambda s: s and "<p>" in s):
            fragment = BeautifulSoup(html.unescape(str(node)), "html.parser")
            node.replace_with(fragment)
        soup = BeautifulSoup(str(soup), "html.parser")
    root = None
    for selector in [select] if select else ["main", "article"]:
        root = soup.select_one(selector)
        if root is not None:
            break
    if root is None:
        root = soup.body or soup
    for tag in root.find_all(EMPHASIS):
        tag.unwrap()
    return f"<main>\n{root.decode_contents() if root.name == 'main' else str(root)}\n</main>"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("source", type=pathlib.Path, help="HTML saved from the browser or curl, or a PDF")
    ap.add_argument("out", type=pathlib.Path, help="clean HTML to pass to onevisit ingest --html")
    ap.add_argument("--select", help="CSS selector of the main content (default: main, then article)")
    ap.add_argument("--unescape-inner", action="store_true", help="decode escaped HTML (elixForms)")
    ap.add_argument("--pdf", action="store_true", help="the source is a PDF")
    args = ap.parse_args()
    if args.pdf:
        body = from_pdf(args.source)
    else:
        raw = args.source.read_text(encoding="utf-8", errors="replace")
        body = from_html(raw, args.select, args.unescape_inner)
    args.out.write_text(f"<!doctype html>\n<html><body>\n{body}\n</body></html>\n", encoding="utf-8")
    print(f"{args.out}: {len(body)} characters")
    return 0


if __name__ == "__main__":
    sys.exit(main())
