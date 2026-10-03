"""Save an official page as clean text, so facts can be quoted and checked.

    python data/tools/save_page.py cie                  # download the URL in sources.csv
    python data/tools/save_page.py cie --html page.html # use a page you saved from the browser

comune.milano.it blocks many scripts and cloud machines (HTTP 403). If the
download fails: open the page in your browser, Ctrl+S / Cmd+S ("Web page, HTML
only"), then run the second form. Either way the result is data/pages/<id>.md,
with the URL and the retrieval date on top, and sources.csv is updated.
"""
import argparse
import csv
import datetime as dt
import hashlib
import html
import pathlib
import re
import sys
import urllib.request
from html.parser import HTMLParser

DATA = pathlib.Path(__file__).resolve().parents[1]
SOURCES = DATA / "sources.csv"
SKIP = {"script", "style", "noscript", "svg", "nav", "header", "footer", "form", "button"}
BLOCK = {"p", "div", "li", "br", "tr", "section", "article", "h1", "h2", "h3", "h4", "h5", "h6", "dt", "dd"}


class TextOnly(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out, self.skip = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in SKIP:
            self.skip += 1
        elif tag in BLOCK:
            self.out.append("\n")
            if tag in {"h1", "h2", "h3", "h4"}:
                self.out.append("#" * int(tag[1]) + " ")
            if tag == "li":
                self.out.append("- ")

    def handle_endtag(self, tag):
        if tag in SKIP and self.skip:
            self.skip -= 1
        elif tag in BLOCK:
            self.out.append("\n")

    def handle_data(self, data):
        if not self.skip:
            self.out.append(data)


def to_text(raw_html: str) -> str:
    p = TextOnly()
    p.feed(raw_html)
    text = html.unescape("".join(p.out))
    lines = [re.sub(r"[ \t\xa0]+", " ", line).strip() for line in text.splitlines()]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip() + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("source_id")
    ap.add_argument("--html", help="a page saved from your browser")
    ap.add_argument("--url", help="set or replace the URL in sources.csv")
    a = ap.parse_args()

    with SOURCES.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        fields, rows = reader.fieldnames, list(reader)
    row = next((r for r in rows if r["id"] == a.source_id), None)
    if row is None:
        print(f"No source '{a.source_id}' in sources.csv. Add a row first.")
        return 1
    if a.url:
        row["url"] = a.url
    if not row["url"]:
        print("This source has no URL yet. Pass --url https://...")
        return 1

    if a.html:
        raw = pathlib.Path(a.html).read_text(encoding="utf-8", errors="replace")
    else:
        req = urllib.request.Request(row["url"], headers={
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128 Safari/537.36",
            "Accept-Language": "it-IT,it;q=0.9"})
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read().decode(resp.headers.get_content_charset() or "utf-8", errors="replace")
        except Exception as e:
            print(f"Download failed ({e}). Save the page from your browser and rerun with --html <file>.")
            return 1

    today = dt.date.today().isoformat()
    out = DATA / "pages" / f"{a.source_id}.md"
    out.parent.mkdir(exist_ok=True)
    header = (f"<!-- source_id: {a.source_id} | url: {row['url']} | retrieved: {today} | "
              f"html_sha256: {hashlib.sha256(raw.encode()).hexdigest()[:16]} -->\n\n")
    out.write_text(header + to_text(raw), encoding="utf-8")

    row.update(snapshot=f"pages/{a.source_id}.md", retrieved_at=today, status="ok")
    with SOURCES.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    print(f"Saved {out.relative_to(DATA.parent)} ({out.stat().st_size} bytes). Now copy quotes from it into data/services/.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
