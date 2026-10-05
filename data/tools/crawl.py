"""Find, re-check and save the official pages behind a topic (the knowledge OneVisit answers from).

    .venv/bin/python data/tools/crawl.py discover --topic carta-identita --out /tmp/crawl
    .venv/bin/python data/tools/crawl.py refresh --topic carta-identita [--from-crawl DIR] [--out DIR]
    .venv/bin/python data/tools/crawl.py ingest --from-crawl /tmp/crawl --ids cie-faq-00411,cie-x=cie-y
    .venv/bin/python data/tools/crawl.py approve --ids cie-faq-00411

discover  Breadth-first from the topic's seeds (crawl_seeds.json, plus the topic's sources already in
          data/sources.csv), the hosts' sitemaps and the City support centre's search, up to --depth
          links away and --max-pages pages. It only follows links whose words look relevant (a host
          all about the topic only breaks ties), keeps a page only if the text ingest would save of
          it (clean_rules) and its title without the site's name score on the topic keywords, never
          leaves the domain allowlist, and writes the raw files and manifest.json to --out. It never
          writes in the repository.
refresh   Downloads again every saved source (or reuses a discover run with --from-crawl), cleans it
          the way clean_html.py + `onevisit ingest` did, and compares the content_hash with
          data/pages/<id>.md: unchanged, changed (with a diff in --out) or failed.
ingest    Saves the manifest entries a person picked (--ids): clean_html.py, a new row in
          sources.csv, then `onevisit ingest`. It re-checks each entry against the repository as
          it is now (id, URL already saved under another id, data/pages/<id>.md already there
          unless --force, the current crawl policy) and leaves the row in status "review".
approve   After a person has read the saved Markdown: status "ok", and the search
          (onevisit/search.py) quotes the page from the next query. A searchable page is still
          not a verified fact: a requirement needs a quote that validate.py finds in the page.

Politeness: robots.txt of every host (urllib.robotparser, plus the * and $ wildcards it ignores),
at least 1 s between two requests to the same host (3 s for yesmilano.it and the support centre,
more if robots.txt asks), one retry after 30 s on 403, 429 or a dropped connection, a page cap,
the plain browser headers of our earlier curl downloads (the City's firewall answers 403 to script
user agents; nothing else is imitated: no cookies, no JavaScript), TLS verification on with the
default CA bundle, and the environment's HTTPS_PROXY.

discover uses only the standard library (any Python 3.11+; PDFs are scored with pdftotext when it
is installed). refresh and ingest clean pages like clean_html.py, so they need the kit environment
(.venv), which has BeautifulSoup and markdownify. See docs/knowledge.md.
"""

from __future__ import annotations

import argparse
import csv
import dataclasses
import datetime as dt
import difflib
import hashlib
import heapq
import http.client
import io
import json
import re
import shutil
import ssl
import subprocess
import sys
import tempfile
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser
import xml.etree.ElementTree as ET
from collections.abc import Callable, Iterable
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

TOOLS_DIR = Path(__file__).resolve().parent
REPO = TOOLS_DIR.parents[1]
DEFAULT_DATA_DIR = REPO / "data"
DEFAULT_SEEDS = TOOLS_DIR / "crawl_seeds.json"
CLEAN_HTML = TOOLS_DIR / "clean_html.py"

# The headers of the curl downloads the City's firewall accepts (a script user agent gets 403).
BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/129.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "it-IT,it;q=0.9,en;q=0.8",
}
# Our token for robots.txt groups: rules for "*" apply, and rules that name us.
ROBOTS_AGENT = "OneVisitCrawler"
REDIRECT_STATUSES = (301, 302, 303, 307, 308)
# Words of a dropped connection, worth one retry after the wait.
_RETRYABLE_ERRORS = ("reset", "remotedisconnected", "timed out", "timeout", "aborted", "broken pipe", "eof")
# Below this many characters, the <main> (or <article>) text is a shell: score the whole body.
MIN_MAIN_CHARS = 200
SAVE_MANIFEST_EVERY = 20
MAX_LINKS_FROM = 20
MAX_NOT_FETCHED = 3000
# Status of a page ingest saved and nobody has read yet: onevisit/search.py skips it.
REVIEW_STATUS = "review"


def log(message: str) -> None:
    """Progress goes to stderr, so stdout stays a clean report."""
    print(message, file=sys.stderr, flush=True)


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


# ----------------------------------------------------------------------------- configuration


def host_matches(host: str, domain: str) -> bool:
    """True for the domain itself and any of its subdomains."""
    host, domain = host.lower(), domain.lower()
    return host == domain or host.endswith("." + domain)


def _params_for(host: str, table: dict[str, list[str]]) -> set[str]:
    names = set(table.get("*", []))
    for domain, params in table.items():
        if domain != "*" and host_matches(host, domain):
            names.update(params)
    return names


@dataclasses.dataclass
class Policy:
    """Where the crawler may go and how fast (crawl_seeds.json, "policy")."""

    allowed_domains: list[str]
    blocked_hosts: list[str] = dataclasses.field(default_factory=list)
    blocked_url_patterns: list[str] = dataclasses.field(default_factory=list)
    skip_extensions: list[str] = dataclasses.field(default_factory=list)
    default_interval_s: float = 1.0
    host_intervals_s: dict[str, float] = dataclasses.field(default_factory=dict)
    retry_statuses: list[int] = dataclasses.field(default_factory=lambda: [403, 429])
    retry_wait_s: float = 30.0
    timeout_s: float = 40.0
    max_bytes: int = 15_000_000
    max_redirects: int = 5
    drop_query_params: dict[str, list[str]] = dataclasses.field(default_factory=dict)
    match_ignore_params: dict[str, list[str]] = dataclasses.field(default_factory=dict)
    canonical_rules: list[dict[str, str]] = dataclasses.field(default_factory=list)
    publishers: dict[str, str] = dataclasses.field(default_factory=dict)
    kind_rules: list[dict[str, str]] = dataclasses.field(default_factory=list)
    clean_rules: list[dict[str, Any]] = dataclasses.field(default_factory=list)
    title_suffixes: list[str] = dataclasses.field(default_factory=list)

    def __post_init__(self) -> None:
        self._blocked = [re.compile(p) for p in self.blocked_url_patterns]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Policy:
        names = {f.name for f in dataclasses.fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in names})

    def block_reason(self, url: str, *, page_filters: bool = True) -> str | None:
        """Why this URL must not be fetched, or None. Sitemaps and searches skip the page filters."""
        parts = urllib.parse.urlsplit(url)
        host = (parts.hostname or "").lower()
        if not any(host_matches(host, d) for d in self.allowed_domains):
            return f"outside the allowlist ({host or 'no host'})"
        if any(host_matches(host, h) for h in self.blocked_hosts):
            return f"blocked host ({host})"
        if not page_filters:
            return None
        path = parts.path.lower()
        if any(path.endswith(ext) for ext in self.skip_extensions):
            return "not a page or a PDF"
        for pattern in self._blocked:
            if pattern.search(url):
                return f"blocked pattern {pattern.pattern}"
        return None

    def publisher(self, url: str) -> str:
        host = urllib.parse.urlsplit(url).hostname or ""
        for domain, name in sorted(self.publishers.items(), key=lambda kv: -len(kv[0])):
            if host_matches(host, domain):
                return name
        return host

    def kind(self, url: str, is_pdf: bool) -> str:
        if is_pdf:
            return "pdf"
        for rule in self.kind_rules:
            if re.search(rule["pattern"], url):
                return rule["kind"]
        return "page"

    def clean_rule(self, url: str) -> dict[str, Any]:
        for rule in self.clean_rules:
            if re.search(rule["pattern"], url):
                return {k: v for k, v in rule.items() if k != "pattern"}
        return {}


@dataclasses.dataclass
class Topic:
    """Seeds and relevance of one topic (crawl_seeds.json, "topics.<name>")."""

    name: str
    title: str = ""
    service_id: str = ""
    id_prefix: str = ""
    seed_sources: dict[str, Any] = dataclasses.field(default_factory=dict)
    seeds: list[str] = dataclasses.field(default_factory=list)
    keywords: dict[str, list[str]] = dataclasses.field(default_factory=dict)
    weights: dict[str, int] = dataclasses.field(default_factory=lambda: {"strong": 3, "medium": 2, "weak": 1})
    count_cap: int = 5
    title_bonus: int = 2
    min_score: int = 10
    min_strong_hits: int = 1
    link_keywords: dict[str, list[str]] = dataclasses.field(default_factory=dict)
    topic_hosts: list[str] = dataclasses.field(default_factory=list)
    search_endpoints: list[dict[str, Any]] = dataclasses.field(default_factory=list)
    sitemaps: dict[str, Any] = dataclasses.field(default_factory=dict)
    id_rules: list[dict[str, str]] = dataclasses.field(default_factory=list)

    @classmethod
    def from_dict(cls, name: str, data: dict[str, Any]) -> Topic:
        names = {f.name for f in dataclasses.fields(cls)} - {"name"}
        return cls(name=name, **{k: v for k, v in data.items() if k in names})


def load_config(path: Path, topic_name: str | None) -> tuple[Policy, Topic | None]:
    """Policy and topic from crawl_seeds.json; a missing topic is an error with the known names."""
    data = json.loads(path.read_text(encoding="utf-8"))
    policy = Policy.from_dict(data["policy"])
    if topic_name is None:
        return policy, None
    topics = data.get("topics", {})
    if topic_name not in topics:
        raise SystemExit(f"Unknown topic '{topic_name}'. Topics in {path.name}: {', '.join(topics)}")
    return policy, Topic.from_dict(topic_name, topics[topic_name])


# ----------------------------------------------------------------------------- URLs


def normalize_url(url: str, base: str | None = None, policy: Policy | None = None) -> str | None:
    """Absolute https URL without fragment, default port or dropped parameters; None if not a web link."""
    url = (url or "").strip()
    if not url or url.startswith(("#", "mailto:", "tel:", "javascript:", "data:")):
        return None
    if base:
        url = urllib.parse.urljoin(base, url)
    try:
        parts = urllib.parse.urlsplit(url)
        port = parts.port
    except ValueError:
        return None
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return None
    host = parts.hostname.lower().rstrip(".")
    netloc = host if port in (None, 80, 443) else f"{host}:{port}"
    path = urllib.parse.quote(parts.path or "/", safe="/%:@!$&'()*+,;=-._~")
    # "?a=1&amp;b=2" written twice-escaped in a page: the parameter is "b", not "amp;b".
    query = re.sub(r"(^|&)amp;", r"\1", parts.query)
    query = urllib.parse.quote(query, safe="=&%+:/?@!$'()*,;~-._")  # spaces and controls are not URLs
    if policy is not None and query:
        drop = _params_for(host, policy.drop_query_params)
        pairs = urllib.parse.parse_qsl(query, keep_blank_values=True)
        if any(name in drop for name, _ in pairs):
            query = urllib.parse.urlencode([(n, v) for n, v in pairs if n not in drop])
    # Every allowed host serves https; the proxy only tunnels https.
    return urllib.parse.urlunsplit(("https", netloc, path, query, ""))


def canonical_key(url: str, policy: Policy) -> str:
    """The key two URLs of the same page share (dedup, and matching with sources.csv)."""
    for rule in policy.canonical_rules:
        match = re.search(rule["pattern"], url)
        if match:
            return match.expand(rule["key"])
    parts = urllib.parse.urlsplit(url)
    host = (parts.hostname or "").lower()
    path = urllib.parse.unquote(parts.path).rstrip("/") or "/"
    ignore = _params_for(host, policy.drop_query_params) | _params_for(host, policy.match_ignore_params)
    pairs = sorted(
        (n, v) for n, v in urllib.parse.parse_qsl(parts.query, keep_blank_values=True) if n not in ignore
    )
    query = urllib.parse.urlencode(pairs)
    return f"{host}{path.lower()}" + (f"?{query}" if query else "")


def slugify(text: str, limit: int = 60) -> str:
    text = normalize_text(urllib.parse.unquote(text))
    slug = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    if len(slug) > limit:
        slug = slug[:limit].rsplit("-", 1)[0] or slug[:limit]
    return slug


def suggest_id(url: str, topic: Topic) -> str:
    """A source id from the topic's id_rules (first match), else <prefix>-<last path segment>."""
    for rule in topic.id_rules:
        match = re.search(rule["pattern"], url)
        if match:
            return slugify(match.expand(rule["id"]), limit=70)
    parts = urllib.parse.urlsplit(url)
    segment = parts.path.rstrip("/").rsplit("/", 1)[-1]
    if not segment:  # a home page: name it after the host
        segment = re.sub(r"^www\.", "", parts.hostname or "home") + "-home"
    return f"{topic.id_prefix or topic.name}-{slugify(segment)}"


# ----------------------------------------------------------------------------- text and relevance

_QUOTES = str.maketrans({"’": "'", "‘": "'", "“": '"', "”": '"', "`": "'", "´": "'"})


def normalize_text(text: str) -> str:
    """Lower case, no accents, plain apostrophes, single spaces: what keywords are matched on."""
    text = unicodedata.normalize("NFKD", text.translate(_QUOTES))
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", text).strip().lower()


def url_words(url: str) -> str:
    """The words of a URL's path and query ("carta-d-identita" -> "carta d identita")."""
    parts = urllib.parse.urlsplit(url)
    text = urllib.parse.unquote_plus(f"{parts.hostname or ''} {parts.path} {parts.query}")
    return re.sub(r"[^a-z0-9]+", " ", normalize_text(text)).strip()


def _word_regex(phrase: str) -> re.Pattern[str]:
    return re.compile(r"(?<![a-z0-9])" + re.escape(normalize_text(phrase)) + r"(?![a-z0-9])")


class Relevance:
    """Keyword score of a page, and how promising a link looks."""

    def __init__(self, topic: Topic, title_suffixes: Iterable[str] = ()) -> None:
        self.topic = topic
        self.page_terms = [(tier, kw, _word_regex(kw)) for tier, kws in topic.keywords.items() for kw in kws]
        self.link_terms = [
            (tier, kw, _word_regex(kw)) for tier, kws in topic.link_keywords.items() for kw in kws
        ]
        # Longest first: " - Carta di Identità Elettronica (CIE)" before " - CIE".
        self.title_suffixes = sorted((normalize_text(x) for x in title_suffixes), key=len, reverse=True)

    def clean_title(self, title: str) -> str:
        """The title without the site's name ("Cookie policy - Carta di Identità Elettronica
        (CIE)" is "cookie policy"): on a site named after the topic, the name is no evidence."""
        head = normalize_text(title)
        changed = True
        while changed and head:
            changed = False
            for suffix in self.title_suffixes:
                if suffix and head.endswith(suffix):
                    head, changed = head[: -len(suffix)].strip(" -|:"), True
        return head

    def score(self, text: str, title: str = "") -> tuple[int, dict[str, int], int]:
        """(score, hits per keyword, hits of strong keywords) of a page's main text and title.

        The title (without the site's name) adds title_bonus per keyword it holds, but only
        the text counts toward min_strong_hits: a page needs its own words on the topic."""
        body, head = normalize_text(text), self.clean_title(title)
        score, hits, strong = 0, {}, 0
        for tier, kw, regex in self.page_terms:
            weight = self.topic.weights.get(tier, 1)
            count = len(regex.findall(body))
            in_title = bool(head and regex.search(head))
            if count:
                hits[kw] = count
                score += weight * min(count, self.topic.count_cap)
            if in_title:
                score += weight * self.topic.title_bonus
            if tier == "strong":
                strong += count
        return score, hits, strong

    def is_relevant(self, score: int, strong: int) -> bool:
        return score >= self.topic.min_score and strong >= self.topic.min_strong_hits

    def link_score(self, url: str, anchor: str = "") -> int:
        """3 per strong link keyword, 1 per weak one (a link that scores 0 is not followed)."""
        words = f"{re.sub(r'[^a-z0-9]+', ' ', normalize_text(anchor))} {url_words(url)}"
        score = 0
        for tier, _kw, regex in self.link_terms:
            if regex.search(words):
                score += 3 if tier == "strong" else 1
        return score

    def on_topic_host(self, url: str) -> bool:
        """A host all about the topic: its links go first among links of the same score (a
        tie-breaker, never a reason to follow a link)."""
        host = urllib.parse.urlsplit(url).hostname or ""
        return any(host_matches(host, h) for h in self.topic.topic_hosts)


# ----------------------------------------------------------------------------- HTML (standard library)

_SKIP_TAGS = {
    "script",
    "style",
    "noscript",
    "template",
    "svg",
    "nav",
    "header",
    "footer",
    "form",
    "button",
    "select",
    "iframe",
    "head",
}
_BLOCK_TAGS = {
    "p",
    "div",
    "li",
    "ul",
    "ol",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "tr",
    "td",
    "th",
    "table",
    "section",
    "article",
    "main",
    "dd",
    "dt",
    "dl",
    "blockquote",
    "aside",
    "figure",
    "figcaption",
}
_VOID_TAGS = {
    "area",
    "base",
    "br",
    "col",
    "embed",
    "hr",
    "img",
    "input",
    "link",
    "meta",
    "param",
    "source",
    "track",
    "wbr",
}


@dataclasses.dataclass
class ParsedPage:
    title: str
    h1: str
    text: str
    links: list[tuple[str, str]]
    canonical: str | None = None
    main_text: str = ""  # the text of <main>, of <article>: what clean rules select
    article_text: str = ""


class _PageParser(HTMLParser):
    """Title, first h1, links with their anchor text, and the text of <main>, <article> and <body>."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title: list[str] = []
        self.h1: list[str] = []
        self.links: list[tuple[str, str]] = []
        self.canonical: str | None = None
        self.main: list[str] = []
        self.article: list[str] = []
        self.body: list[str] = []
        self._stack: list[str] = []
        self._skip = self._in_main = self._in_article = self._in_h1 = 0
        self._in_title = False
        self._h1_done = False
        self._link: tuple[str, list[str]] | None = None

    def _emit(self, text: str) -> None:
        if self._skip or self._in_title:
            return
        self.body.append(text)
        if self._in_main:
            self.main.append(text)
        if self._in_article:
            self.article.append(text)

    def _close_link(self) -> None:
        if self._link is not None:
            href, parts = self._link
            self.links.append((href, re.sub(r"\s+", " ", "".join(parts)).strip()))
            self._link = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = {k: (v or "") for k, v in attrs}
        if tag == "link" and "canonical" in a.get("rel", "").lower().split():
            self.canonical = a.get("href") or None
        if tag == "a":
            self._close_link()
            if a.get("href"):
                self._link = (a["href"], [])
        if tag in _VOID_TAGS:
            if tag == "br":
                self._emit("\n")
            return
        if tag == "body" and "head" in self._stack:
            self.handle_endtag("head")  # an unclosed <head> must not hide the page
        self._stack.append(tag)
        if tag in _SKIP_TAGS:
            self._skip += 1
        elif tag == "main":
            self._in_main += 1
        elif tag == "article":
            self._in_article += 1
        elif tag == "title":
            self._in_title = True
        elif tag == "h1" and not self._h1_done:
            self._in_h1 += 1
        if tag in _BLOCK_TAGS:
            self._emit("\n")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag not in _VOID_TAGS:
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a":
            self._close_link()
        if tag in _VOID_TAGS or tag not in self._stack:
            return
        while self._stack:
            open_tag = self._stack.pop()
            if open_tag in _SKIP_TAGS:
                self._skip -= 1
            elif open_tag == "main":
                self._in_main -= 1
            elif open_tag == "article":
                self._in_article -= 1
            elif open_tag == "title":
                self._in_title = False
            elif open_tag == "h1" and self._in_h1:
                self._in_h1 -= 1
                self._h1_done = True
            if open_tag in _BLOCK_TAGS:
                self._emit("\n")
            if open_tag == tag:
                break

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title.append(data)
        if self._link is not None:
            self._link[1].append(data)
        if self._in_h1 and not self._skip:
            self.h1.append(data)
        self._emit(data)


def _clean_text(parts: Iterable[str]) -> str:
    text = re.sub(r"[ \t\r\f\v ]+", " ", "".join(parts))
    text = re.sub(r" ?\n[ \n]*", "\n", text)
    return text.strip()


def decode_html(raw: bytes, content_type: str = "") -> str:
    match = re.search(r"charset=([\w-]+)", content_type or "", re.I)
    charset = match.group(1) if match else None
    if not charset:
        meta = re.search(rb"<meta[^>]+charset=[\"']?([\w-]+)", raw[:4096], re.I)
        charset = meta.group(1).decode("ascii", "ignore") if meta else "utf-8"
    try:
        return raw.decode(charset, errors="replace")
    except LookupError:
        return raw.decode("utf-8", errors="replace")


def parse_html(raw: bytes | str, content_type: str = "") -> ParsedPage:
    """Parse a page with the standard library: the main text (main, else article, else body)."""
    text = raw if isinstance(raw, str) else decode_html(raw, content_type)
    parser = _PageParser()
    parser.feed(text)
    parser.close()
    parser._close_link()
    main, article = _clean_text(parser.main), _clean_text(parser.article)
    if len(main) >= MIN_MAIN_CHARS:
        body = main
    elif len(article) >= MIN_MAIN_CHARS:
        body = article
    else:
        body = _clean_text(parser.body)
    return ParsedPage(
        title=re.sub(r"\s+", " ", "".join(parser.title)).strip(),
        h1=re.sub(r"\s+", " ", "".join(parser.h1)).strip(),
        text=body,
        links=parser.links,
        canonical=parser.canonical,
        main_text=main,
        article_text=article,
    )


def scoring_text(raw: str, url: str, policy: Policy, page: ParsedPage | None = None) -> str:
    """The text a page is scored on: what ingest would save of it (the policy's clean rule),
    not the whole template. The Ministry's pages keep only their <article>, the support
    centre's only the question, answer and date: a hub or a menu page has no such text, so
    its menus, footer and title don't make it relevant."""
    rule = policy.clean_rule(url)
    if rule.get("select_many"):
        return parse_html(prewrap_selectors(raw, rule["select_many"])).text
    page = page or parse_html(raw)
    selector = str(rule.get("select") or "").strip().lower()
    if selector == "article":
        return page.article_text
    if selector == "main":
        return page.main_text
    return page.text


def pdf_text(raw: bytes) -> str | None:
    """Text of a PDF with pdftotext (as clean_html.py --pdf), or None when it is not installed."""
    if shutil.which("pdftotext") is None:
        return None
    with tempfile.NamedTemporaryFile(suffix=".pdf") as handle:
        handle.write(raw)
        handle.flush()
        result = subprocess.run(
            ["pdftotext", "-raw", "-enc", "UTF-8", handle.name, "-"],
            capture_output=True,
            text=True,
            check=False,
        )
    return result.stdout if result.returncode == 0 else ""


class _ElementCopier(HTMLParser):
    """Copies, verbatim, the elements whose id is wanted (stdlib fallback of prewrap_selectors)."""

    def __init__(self, ids: list[str]) -> None:
        super().__init__(convert_charrefs=False)
        self.wanted = set(ids)
        self.found: dict[str, list[str]] = {}
        self._current: str | None = None
        self._depth = 0

    def _out(self, text: str) -> None:
        if self._current is not None:
            self.found[self._current].append(text)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        element_id = dict(attrs).get("id")
        if self._current is None and element_id in self.wanted and element_id not in self.found:
            self._current, self._depth = element_id, 0
            self.found[element_id] = []
        self._out(self.get_starttag_text() or "")
        if self._current is not None and tag not in _VOID_TAGS:
            self._depth += 1

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._out(self.get_starttag_text() or "")

    def handle_endtag(self, tag: str) -> None:
        if self._current is None or tag in _VOID_TAGS:
            return
        self._out(f"</{tag}>")
        self._depth -= 1
        if self._depth <= 0:
            self._current = None

    def handle_data(self, data: str) -> None:
        self._out(data)

    def handle_entityref(self, name: str) -> None:
        self._out(f"&{name};")

    def handle_charref(self, name: str) -> None:
        self._out(f"&#{name};")


def prewrap_selectors(raw: str, selectors: list[str]) -> str:
    """Only the selected elements, in order, inside <main> (how the support-centre pages were saved)."""
    try:
        from bs4 import BeautifulSoup  # the kit environment: same serialisation as the first ingest
    except ImportError:
        BeautifulSoup = None  # noqa: N806 - optional import
    if BeautifulSoup is not None:
        soup = BeautifulSoup(raw, "html.parser")
        parts = [str(node) for node in (soup.select_one(sel) for sel in selectors) if node is not None]
    else:
        ids = [sel[1:] for sel in selectors if sel.startswith("#")]
        if len(ids) != len(selectors):
            raise ValueError("without BeautifulSoup only #id selectors are supported")
        copier = _ElementCopier(ids)
        copier.feed(raw)
        copier.close()
        parts = ["".join(copier.found[i]) for i in ids if i in copier.found]
    return "<!doctype html><html><body><main>\n" + "\n".join(parts) + "\n</main></body></html>\n"


# ----------------------------------------------------------------------------- HTTP


@dataclasses.dataclass
class Response:
    url: str
    status: int  # 0 when no HTTP answer arrived
    headers: dict[str, str]
    body: bytes = b""
    error: str = ""
    final_url: str = ""
    redirects: list[str] = dataclasses.field(default_factory=list)
    retried: bool = False
    blocked: bool = False  # not fetched on purpose (allowlist, filter, robots.txt)

    def header(self, name: str) -> str:
        return self.headers.get(name.lower(), "")

    @property
    def content_type(self) -> str:
        return self.header("content-type")

    @property
    def is_pdf(self) -> bool:
        return "pdf" in self.content_type.lower() or self.body[:5] == b"%PDF-"

    @property
    def is_html(self) -> bool:
        ctype = self.content_type.lower()
        return not self.is_pdf and ("html" in ctype or (not ctype and b"<html" in self.body[:2048].lower()))


Transport = Callable[[str, dict[str, str], float, int], Response]


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Redirects are followed by PoliteClient, which checks every hop against the allowlist."""

    def redirect_request(self, *args: Any, **kwargs: Any) -> None:  # noqa: ANN401
        return None


_OPENER: urllib.request.OpenerDirector | None = None


def urllib_transport(url: str, headers: dict[str, str], timeout: float, max_bytes: int) -> Response:
    """One GET with the standard library: proxy from the environment, TLS verified, no redirects."""
    global _OPENER
    if _OPENER is None:
        _OPENER = urllib.request.build_opener(
            urllib.request.ProxyHandler(),  # reads HTTPS_PROXY / NO_PROXY
            urllib.request.HTTPSHandler(context=ssl.create_default_context()),
            _NoRedirect(),
        )
    request = urllib.request.Request(url, headers=headers)
    try:
        with _OPENER.open(request, timeout=timeout) as answer:
            body = answer.read(max_bytes + 1)
            hdrs = {k.lower(): v for k, v in answer.headers.items()}
            error = "truncated at --max-bytes" if len(body) > max_bytes else ""
            return Response(url, answer.status, hdrs, body[:max_bytes], error=error)
    except urllib.error.HTTPError as exc:
        try:
            body = exc.read(max_bytes)
        except (OSError, http.client.HTTPException):
            body = b""
        hdrs = {k.lower(): v for k, v in exc.headers.items()} if exc.headers else {}
        return Response(url, exc.code, hdrs, body)
    except (urllib.error.URLError, http.client.HTTPException, OSError, ValueError) as exc:
        reason = getattr(exc, "reason", exc)
        return Response(url, 0, {}, b"", error=f"{type(reason).__name__}: {reason}")


class HostThrottle:
    """At least the configured interval between two requests to the same host (or domain group)."""

    def __init__(
        self,
        policy: Policy,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.policy = policy
        self.clock, self.sleep = clock, sleep
        self._last: dict[str, float] = {}
        self.crawl_delays: dict[str, float] = {}

    def key(self, host: str) -> str:
        matches = [d for d in self.policy.host_intervals_s if host_matches(host, d)]
        return max(matches, key=len) if matches else host

    def interval(self, host: str) -> float:
        key = self.key(host)
        base = self.policy.host_intervals_s.get(key, self.policy.default_interval_s)
        return max(base, self.crawl_delays.get(host, 0.0))

    def wait(self, host: str) -> None:
        key, gap = self.key(host), self.interval(host)
        last = self._last.get(key)
        now = self.clock()
        if last is not None and now - last < gap:
            self.sleep(gap - (now - last))
        self._last[key] = self.clock()


def _robots_pattern(value: str) -> re.Pattern[str]:
    anchored = value.endswith("$")
    body = re.escape(value[:-1] if anchored else value).replace(r"\*", ".*")
    return re.compile(body + ("$" if anchored else ""))


@dataclasses.dataclass
class RobotsRules:
    """robots.txt of one origin: urllib.robotparser, plus the wildcard rules it reads literally."""

    status: int
    note: str = ""
    parser: urllib.robotparser.RobotFileParser | None = None
    allow_all: bool = False
    disallow_all: bool = False
    wildcard_rules: list[tuple[bool, re.Pattern[str], int]] = dataclasses.field(default_factory=list)
    crawl_delay: float | None = None
    sitemaps: list[str] = dataclasses.field(default_factory=list)

    def allows(self, url: str) -> bool:
        if self.disallow_all:
            return False
        if self.allow_all or self.parser is None:
            return True
        if not self.parser.can_fetch(ROBOTS_AGENT, url):
            return False
        parts = urllib.parse.urlsplit(url)
        target = (parts.path or "/") + (f"?{parts.query}" if parts.query else "")
        best: tuple[int, bool] | None = None  # RFC 9309: the longest match wins, allow on a tie
        for allow, pattern, length in self.wildcard_rules:
            if pattern.match(target) and (best is None or (length, allow) > best):
                best = (length, allow)
        return best is None or best[1]

    def summary(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "note": self.note,
            "crawl_delay": self.crawl_delay,
            "sitemaps": self.sitemaps,
        }


def parse_robots(text: str, status: int = 200) -> RobotsRules:
    """Rules for our agent from a robots.txt body (groups naming us win over "*")."""
    lines = text.splitlines()
    parser = urllib.robotparser.RobotFileParser()
    parser.parse(lines)
    ours: list[tuple[bool, str]] = []
    star: list[tuple[bool, str]] = []
    agents: list[str] = []
    in_rules = False
    for raw in lines:
        line = raw.split("#", 1)[0].strip()
        if ":" not in line:
            continue
        field, value = (part.strip() for part in line.split(":", 1))
        field = field.lower()
        if field == "user-agent":
            if in_rules:
                agents, in_rules = [], False
            agents.append(value.lower())
        elif field in ("allow", "disallow"):
            in_rules = True
            if not value or ("*" not in value and not value.endswith("$")):
                continue  # plain prefixes are handled by RobotFileParser
            if any(a != "*" and a in ROBOTS_AGENT.lower() for a in agents):
                ours.append((field == "allow", value))
            elif "*" in agents:
                star.append((field == "allow", value))
    delay = parser.crawl_delay(ROBOTS_AGENT)
    return RobotsRules(
        status=status,
        note="parsed",
        parser=parser,
        wildcard_rules=[(allow, _robots_pattern(v), len(v)) for allow, v in (ours or star)],
        crawl_delay=float(delay) if delay is not None else None,
        sitemaps=list(parser.site_maps() or []),
    )


class PoliteClient:
    """Fetches within the policy: allowlist on every redirect hop, robots.txt, pacing, one retry."""

    def __init__(
        self,
        policy: Policy,
        transport: Transport = urllib_transport,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        logger: Callable[[str], None] = log,
    ) -> None:
        self.policy = policy
        self.transport = transport
        self.sleep = sleep
        self.log = logger
        self.throttle = HostThrottle(policy, clock, sleep)
        self.robots: dict[str, RobotsRules] = {}
        self.requests = 0

    def _request(self, url: str) -> Response:
        host = urllib.parse.urlsplit(url).hostname or ""
        self.throttle.wait(host)
        self.requests += 1
        answer = self.transport(url, dict(BROWSER_HEADERS), self.policy.timeout_s, self.policy.max_bytes)
        dropped = answer.status == 0 and any(w in answer.error.lower() for w in _RETRYABLE_ERRORS)
        if answer.status in self.policy.retry_statuses or dropped:
            self.log(
                f"  {answer.status or answer.error} on {url}: "
                f"waiting {self.policy.retry_wait_s:g} s, then one retry"
            )
            self.sleep(self.policy.retry_wait_s)
            self.throttle.wait(host)
            self.requests += 1
            answer = self.transport(url, dict(BROWSER_HEADERS), self.policy.timeout_s, self.policy.max_bytes)
            answer.retried = True
        return answer

    def robots_for(self, url: str) -> RobotsRules:
        parts = urllib.parse.urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        if origin in self.robots:
            return self.robots[origin]
        target = origin + "/robots.txt"
        answer = self._request(target)
        hops = 0
        while answer.status in REDIRECT_STATUSES and hops < self.policy.max_redirects:
            nxt = normalize_url(answer.header("location"), base=target)
            if not nxt or self.policy.block_reason(nxt, page_filters=False):
                break
            target, hops = nxt, hops + 1
            answer = self._request(target)
        if answer.status == 200:
            rules = parse_robots(answer.body.decode("utf-8", errors="replace"))
        elif answer.status in (401, 403):
            rules = RobotsRules(
                answer.status, "access to robots.txt refused: nothing fetched", disallow_all=True
            )
        elif 400 <= answer.status < 500:
            rules = RobotsRules(answer.status, "no robots.txt: everything allowed", allow_all=True)
        else:
            rules = RobotsRules(
                answer.status,
                f"robots.txt unreachable ({answer.error or answer.status}): nothing fetched",
                disallow_all=True,
            )
        if rules.crawl_delay:
            self.throttle.crawl_delays[parts.hostname or ""] = rules.crawl_delay
        self.robots[origin] = rules
        return rules

    def get(self, url: str, *, page_filters: bool = True) -> Response:
        """GET following redirects by hand; every hop must pass the allowlist, filters and robots.txt."""
        current, redirects = url, []
        for _ in range(self.policy.max_redirects + 1):
            reason = self.policy.block_reason(current, page_filters=page_filters)
            if reason:
                note = f"redirected to {current}: {reason}" if redirects else reason
                return Response(
                    url,
                    0,
                    {},
                    error=f"not fetched: {note}",
                    final_url=current,
                    redirects=redirects,
                    blocked=True,
                )
            if not self.robots_for(current).allows(current):
                return Response(
                    url,
                    0,
                    {},
                    error="not fetched: robots.txt disallows it",
                    final_url=current,
                    redirects=redirects,
                    blocked=True,
                )
            answer = self._request(current)
            if answer.status in REDIRECT_STATUSES:
                nxt = normalize_url(answer.header("location"), base=current, policy=self.policy)
                if not nxt:
                    answer.error = "redirect without a usable Location"
                    break
                redirects.append(nxt)
                current = nxt
                continue
            answer.url, answer.final_url, answer.redirects = url, current, redirects
            return answer
        else:
            return Response(url, 0, {}, error="too many redirects", final_url=current, redirects=redirects)
        answer.url, answer.final_url, answer.redirects = url, current, redirects
        return answer


# ----------------------------------------------------------------------------- repository data (read only)


def read_front_matter(text: str) -> tuple[dict[str, Any], str]:
    """Front matter of a saved page (the simple YAML `onevisit ingest` writes) and its body."""
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        return {}, text
    for end in range(1, len(lines)):
        if lines[end].strip() == "---":
            meta: dict[str, Any] = {}
            key = None
            for line in lines[1:end]:
                item = re.match(r"^\s*-\s+(.*)$", line)
                if item and key is not None and isinstance(meta.get(key), list):
                    meta[key].append(item.group(1).strip().strip("'\""))
                    continue
                pair = re.match(r"^([A-Za-z_][\w-]*):\s*(.*)$", line.rstrip("\n"))
                if pair:
                    key, value = pair.group(1), pair.group(2).strip()
                    meta[key] = [] if value in ("", "[]") else value.strip("'\"")
            return meta, "".join(lines[end + 1 :]).lstrip("\n")
    return {}, text


def content_hash(body: str) -> str:
    """Same as onevisit_knowledge.content_hash: sha256 of the Markdown body."""
    return "sha256:" + hashlib.sha256(body.encode("utf-8")).hexdigest()


def read_sources(data_dir: Path) -> list[dict[str, str]]:
    with (data_dir / "sources.csv").open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def topic_source_rows(data_dir: Path, topic: Topic) -> list[dict[str, str]]:
    """Rows of sources.csv that belong to the topic: id pattern, or the saved page's `servizio`."""
    spec = topic.seed_sources or {}
    patterns = [re.compile(p) for p in spec.get("id_patterns", [])]
    excluded = set(spec.get("exclude_kinds", []))
    service = spec.get("servizio") or topic.service_id
    rows = []
    for row in read_sources(data_dir):
        if row.get("kind") in excluded or not row.get("url"):
            continue
        hit = any(p.search(row["id"]) for p in patterns)
        if not hit and service and (row.get("snapshot") or "").startswith("pages/"):
            page = data_dir / row["snapshot"]
            if page.exists():
                meta, _ = read_front_matter(page.read_text(encoding="utf-8", errors="replace"))
                hit = service in (meta.get("servizio") or [])
        if hit:
            rows.append(row)
    return rows


# ----------------------------------------------------------------------------- discover


def parse_sitemap(raw: bytes) -> tuple[str, list[str]]:
    """("index" | "urlset" | "invalid", the <loc> of each <sitemap> or <url>)."""
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        return "invalid", []

    def local(tag: str) -> str:
        return tag.rsplit("}", 1)[-1]

    kind = "index" if local(root.tag) == "sitemapindex" else "urlset"
    locs = []
    for item in root:
        for child in item:
            if local(child.tag) == "loc" and child.text:
                locs.append(child.text.strip())
    return kind, locs


def _file_name(url: str, ext: str) -> str:
    parts = urllib.parse.urlsplit(url)
    stem = slugify(f"{parts.hostname} {parts.path} {parts.query}", limit=90) or "page"
    return f"{stem}-{hashlib.sha1(url.encode('utf-8')).hexdigest()[:8]}{ext}"


@dataclasses.dataclass(order=True)
class _QueueItem:
    depth: int
    priority: int
    elsewhere: int  # 0 on a topic host: first among links of the same score
    seq: int
    key: str = dataclasses.field(compare=False)


class Crawler:
    """Breadth-first discovery for one topic; writes raw files and manifest.json in out_dir."""

    def __init__(
        self,
        policy: Policy,
        topic: Topic,
        client: PoliteClient,
        out_dir: Path,
        data_dir: Path,
        *,
        max_pages: int = 300,
        max_depth: int = 2,
        use_sitemaps: bool = True,
        use_search: bool = True,
        logger: Callable[[str], None] = log,
    ) -> None:
        self.policy, self.topic, self.client = policy, topic, client
        self.out_dir, self.data_dir = out_dir, data_dir
        self.max_pages, self.max_depth = max_pages, max_depth
        self.use_sitemaps, self.use_search = use_sitemaps, use_search
        self.log = logger
        self.relevance = Relevance(topic, policy.title_suffixes)
        self.entries: dict[str, dict[str, Any]] = {}
        self.pending: dict[str, dict[str, Any]] = {}
        self.not_fetched: dict[str, dict[str, Any]] = {}
        self.heap: list[_QueueItem] = []
        self.seq = 0
        self.pages = 0
        self.searches: list[dict[str, Any]] = []
        self.sitemaps: list[dict[str, Any]] = []
        self.started_at = now_iso()
        self.by_text: dict[str, dict[str, Any]] = {}
        self.earlier_requests = 0  # set by rescore: requests of the run that downloaded the files
        self.earlier_hosts: dict[str, Any] = {}
        self.known: dict[str, str] = {}
        self.source_ids: set[str] = set()
        if (data_dir / "sources.csv").exists():
            for row in read_sources(data_dir):
                self.source_ids.add(row["id"])
                url = normalize_url(row.get("url", ""), policy=policy)
                if url:
                    self.known.setdefault(canonical_key(url, policy), row["id"])

    # -- queue

    def _note_link(self, record: dict[str, Any], source: str, anchor: str) -> None:
        if source not in record["links_from"] and len(record["links_from"]) < MAX_LINKS_FROM:
            record["links_from"].append(source)
        if anchor and anchor not in record["anchors"] and len(record["anchors"]) < 5:
            record["anchors"].append(anchor[:160])

    def enqueue(self, url: str | None, depth: int, source: str, anchor: str = "", *, seed: int = 0) -> bool:
        """Queue a link if it is new, allowed and looks relevant (seeds always look relevant)."""
        if not url:
            return False
        key = canonical_key(url, self.policy)
        if source.startswith("https://") and canonical_key(source, self.policy) == key:
            return False  # a page linking to itself
        for table in (self.entries, self.pending, self.not_fetched):
            if key in table:
                self._note_link(table[key], source, anchor)
                return False
        reason = self.policy.block_reason(url)
        score = seed or self.relevance.link_score(url, anchor)
        if reason is None and depth > self.max_depth:
            reason = "deeper than --depth"
        if reason is None and score < 1:
            return False  # an irrelevant link: not even worth a line in the manifest
        record = {"url": url, "depth": depth, "link_score": score, "links_from": [], "anchors": []}
        self._note_link(record, source, anchor)
        if reason is not None:
            if len(self.not_fetched) < MAX_NOT_FETCHED:
                record["reason"] = reason
                self.not_fetched[key] = record
            return False
        self.pending[key] = record
        self.seq += 1
        elsewhere = 0 if self.relevance.on_topic_host(url) else 1
        heapq.heappush(self.heap, _QueueItem(depth, -score, elsewhere, self.seq, key))
        return True

    # -- discovery sources

    def seed(self) -> None:
        for url in self.topic.seeds:
            self.enqueue(normalize_url(url, policy=self.policy), 0, "seed", seed=100)
        for row in topic_source_rows(self.data_dir, self.topic):
            self.enqueue(
                normalize_url(row["url"], policy=self.policy), 0, f"sources.csv:{row['id']}", seed=50
            )

    def search(self) -> None:
        for endpoint in self.topic.search_endpoints:
            for query in endpoint.get("queries", []):
                url = endpoint["url"].replace("{query}", urllib.parse.quote(query))
                answer = self.client.get(url, page_filters=False)
                found = added = 0
                if answer.status == 200:
                    try:
                        items = json.loads(answer.body.decode("utf-8", errors="replace"))
                    except json.JSONDecodeError:
                        items = []
                    for item in items if isinstance(items, list) else []:
                        if not isinstance(item, dict) or not item.get(endpoint.get("link_field", "link")):
                            continue
                        found += 1
                        link = normalize_url(
                            item[endpoint.get("link_field", "link")], base=url, policy=self.policy
                        )
                        extra = " ".join(str(item.get(f, "")) for f in endpoint.get("extra_fields", []))
                        anchor = f"{item.get(endpoint.get('title_field', 'title'), '')} {extra}"
                        anchor = re.sub(r"<[^>]+>", " ", anchor)
                        added += self.enqueue(
                            link, 1, f"search:{endpoint.get('name', 'search')}:{query}", anchor
                        )
                self.searches.append(
                    {
                        "endpoint": endpoint.get("name", ""),
                        "query": query,
                        "http_status": answer.status,
                        "error": answer.error,
                        "results": found,
                        "queued": added,
                    }
                )
                self.log(
                    f"search {endpoint.get('name', '')} '{query}': {answer.status} "
                    f"{found} results, {added} new"
                )

    def read_sitemaps(self) -> None:
        spec = self.topic.sitemaps or {}
        max_files = int(spec.get("max_files_per_host", 6))
        max_index = int(spec.get("max_index_entries", 200))
        for host in spec.get("hosts", []):
            rules = self.client.robots_for(f"https://{host}/")
            todo = list(rules.sitemaps) or [f"https://{host}/sitemap.xml"]
            done = 0
            while todo and done < max_files:
                url = todo.pop(0)
                answer = self.client.get(url, page_filters=False)
                done += 1
                kind, locs = parse_sitemap(answer.body) if answer.status == 200 else ("invalid", [])
                record = {
                    "url": url,
                    "http_status": answer.status,
                    "kind": kind,
                    "entries": len(locs),
                    "queued": 0,
                    "note": answer.error,
                }
                if kind == "index":
                    relevant = [u for u in locs if self.relevance.link_score(u) >= 1]
                    if len(locs) <= max_index:
                        todo.extend(relevant + [u for u in locs if u not in relevant])
                    elif relevant:
                        todo.extend(relevant)
                    else:
                        record["note"] = (
                            f"index of {len(locs)} sitemaps with no relevant names: not read "
                            f"(more than {max_index}); links are enough there"
                        )
                elif kind == "urlset":
                    for loc in locs:
                        record["queued"] += self.enqueue(
                            normalize_url(loc, policy=self.policy), 1, f"sitemap:{url}"
                        )
                self.sitemaps.append(record)
                self.log(
                    f"sitemap {url}: {answer.status} {kind} {len(locs)} entries, {record['queued']} queued"
                )

    # -- pages

    def fetch_page(self, key: str) -> None:
        record = self.pending.pop(key)
        url, depth = record["url"], record["depth"]
        answer = self.client.get(url)
        self.pages += 1
        final = answer.final_url or url
        entry: dict[str, Any] = {
            "suggested_id": None,
            "url": url,
            "final_url": final,
            "canonical": key,
            "http_status": answer.status,
            "content_type": answer.content_type,
            "sha256": hashlib.sha256(answer.body).hexdigest() if answer.body else None,
            "bytes": len(answer.body),
            "fetched_at": now_iso(),
            "title": "",
            "h1": "",
            "score": 0,
            "strong_hits": 0,
            "keyword_hits": {},
            "kept": False,
            "reason": "",
            "depth": depth,
            "link_score": record["link_score"],
            "links_from": record["links_from"],
            "anchors": record["anchors"],
            "raw_file": None,
            "text_file": None,
            "text_chars": 0,
            "already_saved_as": self.known.get(key) or self.known.get(canonical_key(final, self.policy)),
            "duplicate_of": None,
            "publisher": self.policy.publisher(final),
            "kind": None,
            "retried": answer.retried,
            "redirects": answer.redirects,
            "error": answer.error,
        }
        self.entries[key] = entry
        final_key = canonical_key(final, self.policy)
        if final_key != key and final_key in self.entries:  # redirected to a page already fetched
            self._mark_duplicate(entry, self.entries[final_key])
        elif final_key != key:
            self.entries[final_key] = entry  # a later link to the final URL is the same page
            twin = self.pending.pop(final_key, None)  # already queued under its final URL
            if twin is not None:
                for source in twin["links_from"]:
                    self._note_link(entry, source, "")
        if answer.status != 200:
            entry["reason"] = answer.error or f"HTTP {answer.status}"
        elif not (answer.is_html or answer.is_pdf):
            entry["reason"] = f"not a page or a PDF ({answer.content_type or 'no content type'})"
        else:
            raw_name = _file_name(final, ".pdf" if answer.is_pdf else ".html")
            (self.out_dir / "raw").mkdir(parents=True, exist_ok=True)
            (self.out_dir / "raw" / raw_name).write_bytes(answer.body)
            entry["raw_file"] = f"raw/{raw_name}"
            links = self._analyse(entry, answer.body, answer.is_pdf, answer.content_type)
            if depth < self.max_depth:
                for href, anchor in links:
                    self.enqueue(
                        normalize_url(href, base=final, policy=self.policy), depth + 1, final, anchor
                    )
        mark = "KEEP" if entry["kept"] else "    "
        saved = f" = {entry['already_saved_as']}" if entry["already_saved_as"] else ""
        self.log(
            f"[{self.pages}/{self.max_pages}] d{depth} {answer.status or '---'} "
            f"{entry['score']:>3} {mark} {url}{saved}"
            + ("" if entry["kept"] or not entry["reason"] else f"  ({entry['reason'][:80]})")
        )

    def _mark_duplicate(self, entry: dict[str, Any], twin: dict[str, Any]) -> None:
        entry["duplicate_of"] = twin["final_url"]
        entry["already_saved_as"] = entry["already_saved_as"] or twin["already_saved_as"]

    def _analyse(
        self, entry: dict[str, Any], body: bytes, is_pdf: bool, content_type: str
    ) -> list[tuple[str, str]]:
        """Score a downloaded page, spot duplicates, write its text; returns the page's links."""
        final = entry["final_url"]
        raw_name = entry["raw_file"].split("/", 1)[1]
        entry["kind"] = self.policy.kind(final, is_pdf)
        links: list[tuple[str, str]] = []
        if is_pdf:
            text = pdf_text(body)
            title = urllib.parse.unquote(urllib.parse.urlsplit(final).path.rsplit("/", 1)[-1])
            if text is None:  # no pdftotext: score the words that pointed to the PDF
                entry["error"] = "pdftotext missing: scored on the links' anchor text"
                text = " ".join(entry["anchors"])
            entry["title"] = title
        else:
            page = parse_html(body, content_type)
            links = page.links
            text = scoring_text(decode_html(body, content_type), final, self.policy, page)
            entry["title"], entry["h1"] = page.title, page.h1
        score, hits, strong = self.relevance.score(text, f"{entry['title']} {entry['h1']}")
        entry.update(score=score, keyword_hits=hits, strong_hits=strong, text_chars=len(text))
        text_hash = hashlib.sha256(normalize_text(text).encode("utf-8")).hexdigest()
        entry["text_sha256"] = text_hash
        twin = self.by_text.get(text_hash) if len(text) >= MIN_MAIN_CHARS else None
        if twin is not None and twin is not entry and not entry["duplicate_of"]:
            self._mark_duplicate(entry, twin)  # the same text under another address
        elif twin is None:
            self.by_text[text_hash] = entry
        entry["kept"] = self.relevance.is_relevant(score, strong)
        if entry["kept"]:
            entry["reason"] = "relevant"
            (self.out_dir / "text").mkdir(parents=True, exist_ok=True)
            text_name = raw_name.rsplit(".", 1)[0] + ".txt"
            header = f"{final}\n{entry['title']}\n\n"
            (self.out_dir / "text" / text_name).write_text(header + text + "\n", encoding="utf-8")
            entry["text_file"] = f"text/{text_name}"
        elif strong < self.topic.min_strong_hits:
            entry["reason"] = f"too few strong keywords ({strong} < {self.topic.min_strong_hits})"
        else:
            entry["reason"] = f"score {score} below {self.topic.min_score}"
        return links

    # -- run

    def assign_ids(self) -> None:
        taken = set(self.source_ids)
        seen: set[int] = set()
        for entry in self.entries.values():
            if id(entry) in seen:
                continue
            seen.add(id(entry))
            if entry["already_saved_as"]:
                entry["suggested_id"] = entry["already_saved_as"]
                continue
            if entry["http_status"] != 200 or not entry["raw_file"] or entry.get("duplicate_of"):
                continue
            base = suggest_id(entry["final_url"], self.topic)
            candidate, n = base, 2
            while candidate in taken:
                candidate, n = f"{base}-{n}", n + 1
            taken.add(candidate)
            entry["suggested_id"] = candidate

    def manifest(self, finished: bool) -> dict[str, Any]:
        unique: list[dict[str, Any]] = []
        seen: set[int] = set()
        for entry in self.entries.values():
            if id(entry) not in seen:
                seen.add(id(entry))
                unique.append(entry)
        kept = [e for e in unique if e["kept"]]
        left = [
            dict(self.pending[i.key], reason="page cap reached")
            for i in sorted(self.heap)
            if i.key in self.pending
        ]
        return {
            "tool": "data/tools/crawl.py discover" + (" + rescore" if self.earlier_requests else ""),
            "topic": self.topic.name,
            "started_at": self.started_at,
            "finished_at": now_iso() if finished else None,
            "params": {
                "max_pages": self.max_pages,
                "max_depth": self.max_depth,
                "min_score": self.topic.min_score,
                "min_strong_hits": self.topic.min_strong_hits,
                "sitemaps": self.use_sitemaps,
                "search": self.use_search,
            },
            "counts": {
                "pages_fetched": len(unique),
                "http_requests": self.client.requests + self.earlier_requests,
                "ok": sum(1 for e in unique if e["http_status"] == 200),
                "kept": len(kept),
                "kept_new": sum(1 for e in kept if not e["already_saved_as"] and not e["duplicate_of"]),
                "kept_duplicates": sum(1 for e in kept if e["duplicate_of"] and not e["already_saved_as"]),
                "kept_already_saved": sum(1 for e in kept if e["already_saved_as"]),
                "not_fetched": len(self.not_fetched) + len(left),
            },
            "hosts": self.earlier_hosts
            | {origin: rules.summary() for origin, rules in self.client.robots.items()},
            "kept_new": sorted(
                (e["suggested_id"] for e in kept if not e["already_saved_as"] and e["suggested_id"]),
            ),
            "searches": self.searches,
            "sitemaps": self.sitemaps,
            "entries": unique,
            "not_fetched": list(self.not_fetched.values()) + left,
        }

    def save(self, finished: bool) -> Path:
        self.assign_ids()
        path = self.out_dir / "manifest.json"
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(self.manifest(finished), ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(path)
        return path

    def run(self) -> dict[str, Any]:
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.seed()
        if self.use_search:
            self.search()
        if self.use_sitemaps:
            self.read_sitemaps()
        while self.heap and self.pages < self.max_pages:
            item = heapq.heappop(self.heap)
            if item.key in self.pending:
                self.fetch_page(item.key)
                if self.pages % SAVE_MANIFEST_EVERY == 0:
                    self.save(finished=False)
        self.save(finished=True)
        return self.manifest(finished=True)

    def rescore(self) -> dict[str, Any]:
        """Score again the files of an earlier discover run (new keywords or thresholds), offline."""
        old = json.loads((self.out_dir / "manifest.json").read_text(encoding="utf-8"))
        self.started_at = old.get("started_at", self.started_at)
        self.searches, self.sitemaps = old.get("searches", []), old.get("sitemaps", [])
        self.earlier_requests = old.get("counts", {}).get("http_requests", 0)
        self.earlier_hosts = old.get("hosts", {})
        self.max_pages, self.max_depth = old["params"]["max_pages"], old["params"]["max_depth"]
        self.use_sitemaps, self.use_search = old["params"]["sitemaps"], old["params"]["search"]
        for record in old.get("not_fetched", []):
            self.not_fetched.setdefault(canonical_key(record["url"], self.policy), record)
        for entry in old["entries"]:
            key = canonical_key(entry["url"], self.policy)
            final_key = canonical_key(entry["final_url"], self.policy)
            entry.update(suggested_id=None, duplicate_of=None, text_file=None, kept=False, score=0)
            entry["already_saved_as"] = self.known.get(key) or self.known.get(final_key)
            if final_key != key and final_key in self.entries:
                self._mark_duplicate(entry, self.entries[final_key])
            self.entries[key] = entry
            self.entries.setdefault(final_key, entry)
            if entry.get("raw_file"):
                raw = (self.out_dir / entry["raw_file"]).read_bytes()
                self._analyse(entry, raw, entry["raw_file"].endswith(".pdf"), entry.get("content_type") or "")
        self.pages = len(old["entries"])
        self.save(finished=True)
        return self.manifest(finished=True)


# ----------------------------------------------------------------------------- refresh

Cleaner = Callable[[bytes, bool, str], list[tuple[str, str]]]


def clean_variants(url: str, is_pdf: bool, policy: Policy) -> list[dict[str, Any]]:
    """Cleaning options to try, the configured rule first (pages were saved with one of these)."""
    if is_pdf:
        return [{"pdf": True}]
    variants = [policy.clean_rule(url), {}, {"select": "article"}, {"unescape_inner": True}]
    unique: list[dict[str, Any]] = []
    for v in variants:
        if v not in unique:
            unique.append(v)
    return unique


def variant_args(options: dict[str, Any]) -> list[str]:
    """clean_html.py arguments of a cleaning variant (select_many is applied before, by prewrap)."""
    if options.get("pdf"):
        return ["--pdf"]
    args: list[str] = []
    if options.get("select"):
        args += ["--select", options["select"]]
    if options.get("unescape_inner"):
        args.append("--unescape-inner")
    return args


def variant_name(options: dict[str, Any]) -> str:
    if options.get("select_many"):
        return "only " + " ".join(options["select_many"])
    return " ".join(variant_args(options)) or "main"


def kit_cleaner(policy: Policy) -> Cleaner:
    """The real cleaning: clean_html.py's functions, then onevisit ingest's html_to_markdown."""
    sys.path.insert(0, str(TOOLS_DIR))
    for lib in ("onevisit_cli", "onevisit_knowledge"):
        src = REPO / "libs" / lib / "src"
        if src.exists() and str(src) not in sys.path:
            sys.path.append(str(src))
    try:
        import clean_html  # data/tools/clean_html.py
        from onevisit_cli.ingest import html_to_markdown
    except ImportError as exc:
        raise SystemExit(f"refresh needs the kit environment (.venv/bin/python): {exc}") from exc

    def wrap(body: str) -> str:  # exactly what clean_html.py writes to its output file
        return f"<!doctype html>\n<html><body>\n{body}\n</body></html>\n"

    def clean(raw: bytes, is_pdf: bool, url: str) -> list[tuple[str, str]]:
        out = []
        for options in clean_variants(url, is_pdf, policy):
            if options.get("pdf"):
                with tempfile.NamedTemporaryFile(suffix=".pdf") as handle:
                    handle.write(raw)
                    handle.flush()
                    body = clean_html.from_pdf(Path(handle.name))
            else:
                text = raw.decode("utf-8", errors="replace")  # how clean_html.py reads its input
                if options.get("select_many"):
                    text = prewrap_selectors(text, options["select_many"])
                body = clean_html.from_html(text, options.get("select"), bool(options.get("unescape_inner")))
            out.append((variant_name(options), html_to_markdown(wrap(body))))
        return out

    return clean


def _norm_compare(text: str) -> str:
    """validate.py's normalisation: plain apostrophes and quotes, single spaces, lower case."""
    return re.sub(r"\s+", " ", text.translate(_QUOTES)).strip().lower()


def load_crawl(crawl_dir: Path | None, policy: Policy) -> dict[str, dict[str, Any]]:
    """Entries of a discover run by canonical URL (original and final), to reuse its raw files."""
    if crawl_dir is None:
        return {}
    manifest = json.loads((crawl_dir / "manifest.json").read_text(encoding="utf-8"))
    table: dict[str, dict[str, Any]] = {}
    for entry in manifest["entries"]:
        for url in (entry["url"], entry["final_url"]):
            table.setdefault(canonical_key(url, policy), entry)
    return table


def refresh(
    data_dir: Path,
    policy: Policy,
    client: PoliteClient | None,
    cleaner: Cleaner,
    *,
    topic: Topic | None = None,
    ids: set[str] | None = None,
    crawl_dir: Path | None = None,
    out_dir: Path | None = None,
) -> list[dict[str, Any]]:
    """Compare every saved page with the live one: unchanged, changed, failed or skipped."""
    rows = topic_source_rows(data_dir, topic) if topic else read_sources(data_dir)
    crawl = load_crawl(crawl_dir, policy)
    results = []
    for row in rows:
        sid, url, snapshot = row["id"], row.get("url", ""), row.get("snapshot", "")
        if ids and sid not in ids:
            continue
        result: dict[str, Any] = {"id": sid, "url": url, "status": "", "detail": ""}
        results.append(result)
        if not url or not snapshot.startswith("pages/"):
            result.update(status="skipped", detail="no saved page to compare (open data or no URL)")
            continue
        page = data_dir / snapshot
        if not page.exists():
            result.update(status="failed", detail=f"{snapshot} missing")
            continue
        meta, saved_body = read_front_matter(page.read_text(encoding="utf-8"))
        saved_hash = str(meta.get("content_hash") or content_hash(saved_body))
        norm_url = normalize_url(url, policy=policy) or url
        entry = crawl.get(canonical_key(norm_url, policy))
        if crawl_dir is not None and entry and entry.get("http_status") == 200 and entry.get("raw_file"):
            raw = (crawl_dir / entry["raw_file"]).read_bytes()
            is_pdf = entry["raw_file"].endswith(".pdf")
            result["from"] = "crawl"
        elif client is None:
            result.update(status="failed", detail="not in the crawl, and --offline")
            continue
        else:
            answer = client.get(norm_url, page_filters=False)
            if answer.status != 200:
                result.update(status="failed", detail=answer.error or f"HTTP {answer.status}")
                continue
            raw, is_pdf = answer.body, answer.is_pdf
            result["from"] = "live"
        try:
            variants = cleaner(raw, is_pdf, norm_url)
        except Exception as exc:  # noqa: BLE001 - one broken page must not stop the report
            result.update(status="failed", detail=f"cleaning failed: {type(exc).__name__}: {exc}")
            continue
        same = next((name for name, body in variants if content_hash(body) == saved_hash), None)
        if same is None:
            saved_norm = _norm_compare(saved_body)
            same_text = next((n for n, b in variants if _norm_compare(b) == saved_norm), None)
            if same_text is not None:
                result.update(status="unchanged", detail=f"same text, spacing differs ({same_text})")
                continue
            best_name, best_body, best_ratio = "", "", -1.0
            for name, body in variants:
                ratio = difflib.SequenceMatcher(None, saved_body, body, autojunk=False).ratio()
                if ratio > best_ratio:
                    best_name, best_body, best_ratio = name, body, ratio
            result.update(
                status="changed",
                similarity=round(best_ratio, 3),
                variant=best_name,
                detail=f"similarity {best_ratio:.3f} ({best_name}); re-verify the quotes",
            )
            if out_dir is not None:
                out_dir.mkdir(parents=True, exist_ok=True)
                (out_dir / f"{sid}.md").write_text(best_body, encoding="utf-8")
                diff = difflib.unified_diff(
                    saved_body.splitlines(),
                    best_body.splitlines(),
                    f"data/{snapshot}",
                    f"live {url}",
                    lineterm="",
                    n=1,
                )
                (out_dir / f"{sid}.diff").write_text("\n".join(diff) + "\n", encoding="utf-8")
                result["diff"] = str(out_dir / f"{sid}.diff")
        else:
            result.update(status="unchanged", detail=same)
    return results


# ----------------------------------------------------------------------------- ingest

Runner = Callable[[list[str], Path], "subprocess.CompletedProcess[str]"]


def _run(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, check=False)


def parse_ids(spec: str) -> list[tuple[str, str]]:
    """ "a,b=c" -> [("a", "a"), ("b", "c")]: manifest id, and the source id to save it as."""
    pairs = []
    for item in (part.strip() for part in spec.split(",")):
        if item:
            old, _, new = item.partition("=")
            pairs.append((old.strip(), (new or old).strip()))
    return pairs


def append_source_row(sources_path: Path, row: dict[str, str]) -> bool:
    """Append a row with the file's own line ending; False if the id is already there."""
    text = sources_path.read_text(encoding="utf-8")
    header = next(csv.reader(io.StringIO(text)))
    if any(r.get("id") == row["id"] for r in csv.DictReader(io.StringIO(text))):
        return False
    newline = "\r\n" if "\r\n" in text else "\n"
    buffer = io.StringIO()
    csv.writer(buffer, lineterminator=newline).writerow([row.get(col, "") for col in header])
    if text and not text.endswith(("\n", "\r")):
        text += newline
    sources_path.write_text(text + buffer.getvalue(), encoding="utf-8")
    return True


def set_source_field(sources_path: Path, source_id: str, field: str, value: str) -> bool:
    """Change one field of one row of sources.csv, every other line left byte for byte;
    False when the id is not there."""
    text = sources_path.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)
    reader = csv.reader(io.StringIO(text))
    header = next(reader)
    start = reader.line_num
    for row in reader:
        end = reader.line_num
        if row and row[0] == source_id:
            record = dict(zip(header, row, strict=False))
            record[field] = value
            newline = "\r\n" if lines[end - 1].endswith("\r\n") else "\n"
            buffer = io.StringIO()
            csv.writer(buffer, lineterminator=newline).writerow([record.get(col, "") for col in header])
            lines[start:end] = [buffer.getvalue()]
            sources_path.write_text("".join(lines), encoding="utf-8")
            return True
        start = end
    return False


def select_entries(
    manifest: dict[str, Any], ids: list[tuple[str, str]] | None
) -> tuple[list[tuple[dict[str, Any], str]], list[str]]:
    """Entries to save (with their new source id) and the problems found while choosing them.

    Only the ids a person picked: a score says a page is on the topic, not that it is worth
    quoting (hubs, site maps and chip specifications score high too)."""
    by_id = {e["suggested_id"]: e for e in manifest["entries"] if e.get("suggested_id")}
    chosen, problems = [], []
    for old, new in ids or []:
        entry = by_id.get(old)
        if entry is None:
            problems.append(f"{old}: not in the manifest")
        elif entry.get("already_saved_as"):
            problems.append(f"{old}: already saved as {entry['already_saved_as']} (use refresh)")
        elif entry.get("duplicate_of"):
            problems.append(f"{old}: same page as {entry['duplicate_of']}")
        elif entry.get("http_status") != 200 or not entry.get("raw_file"):
            problems.append(f"{old}: not downloaded ({entry.get('reason')})")
        else:
            chosen.append((entry, new))
    return chosen, problems


def _saved_urls(data_dir: Path, policy: Policy) -> dict[str, str]:
    """Canonical URL -> source id of every row of sources.csv as it is now."""
    saved: dict[str, str] = {}
    for row in read_sources(data_dir):
        url = normalize_url(row.get("url", ""), policy=policy)
        if url:
            saved.setdefault(canonical_key(url, policy), row["id"])
    return saved


def ingest(
    crawl_dir: Path,
    data_dir: Path,
    policy: Policy,
    *,
    ids: list[tuple[str, str]] | None = None,
    python: str = sys.executable,
    onevisit: str | None = None,
    work_dir: Path | None = None,
    runner: Runner = _run,
    dry_run: bool = False,
    force: bool = False,
) -> int:
    """clean_html.py, a sources.csv row and `onevisit ingest` for each approved manifest entry.

    Checked again against the repository as it is now, not as it was when the crawl ran
    (someone may have saved pages since): an id already in sources.csv, a URL already saved
    under another id, a page file already in data/pages (unless `force`) and a URL the
    crawl policy now blocks are skipped. A saved page gets status "review": the search
    leaves it out until a person has read it and run `crawl.py approve`."""
    manifest = json.loads((crawl_dir / "manifest.json").read_text(encoding="utf-8"))
    chosen, problems = select_entries(manifest, ids)
    for problem in problems:
        print(f"skip    {problem}")
    if not chosen:
        print("Nothing to ingest: pass --ids with suggested ids from the manifest.")
        return 1 if problems else 0
    if onevisit is None:
        local = REPO / ".venv" / "bin" / "onevisit"
        onevisit = str(local) if local.exists() else "onevisit"
    work_dir = work_dir or crawl_dir / "ingest-work"
    work_dir.mkdir(parents=True, exist_ok=True)
    taken = {r["id"] for r in read_sources(data_dir)}
    saved_urls = _saved_urls(data_dir, policy)
    failures = 0
    for entry, source_id in chosen:
        url = entry["final_url"]
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", source_id):
            print(f"skip    {source_id}: ids are lower-case letters, digits and hyphens")
            failures += 1
            continue
        if source_id in taken:
            print(f"skip    {source_id}: the id is already in sources.csv; rename it with --ids old=new")
            failures += 1
            continue
        keys = {canonical_key(normalize_url(u, policy=policy) or u, policy) for u in (entry["url"], url)}
        twin = next((saved_urls[k] for k in sorted(keys) if k in saved_urls), None)
        if twin is not None:
            print(f"skip    {source_id}: already saved as {twin} (use refresh)")
            failures += 1
            continue
        blocked = policy.block_reason(url) or policy.block_reason(entry["url"])
        if blocked is not None:
            print(f"skip    {source_id}: the crawl policy now refuses it ({blocked})")
            failures += 1
            continue
        page_path = data_dir / "pages" / f"{source_id}.md"
        if page_path.exists() and not force:
            print(
                f"skip    {source_id}: pages/{source_id}.md already exists; "
                "pass --force to overwrite it"
            )
            failures += 1
            continue
        raw = crawl_dir / entry["raw_file"]
        is_pdf = raw.suffix == ".pdf"
        options = {"pdf": True} if is_pdf else policy.clean_rule(url)
        source = raw
        if options.get("select_many"):
            source = work_dir / f"{source_id}.pre.html"
            source.write_text(
                prewrap_selectors(raw.read_text(encoding="utf-8", errors="replace"), options["select_many"]),
                encoding="utf-8",
            )
        clean = work_dir / f"{source_id}.clean.html"
        clean_cmd = [python, str(CLEAN_HTML), str(source), str(clean), *variant_args(options)]
        ingest_cmd = [
            onevisit,
            "ingest",
            source_id,
            "--html",
            str(clean),
            "--url",
            url,
            "--data-dir",
            str(data_dir),
        ]
        title = entry.get("h1") or entry.get("title") or source_id
        row = {
            "id": source_id,
            "title": title,
            "url": url,
            "publisher": entry.get("publisher") or policy.publisher(url),
            "kind": entry.get("kind") or policy.kind(url, is_pdf),
            "snapshot": "",
            "retrieved_at": "",
            "status": "todo",
            "notes": (
                f"Found by data/tools/crawl.py (topic {manifest.get('topic')}, score {entry['score']}, "
                f"from {(entry.get('links_from') or ['?'])[0]}); cleaned with clean_html.py "
                f"{variant_name(options)}, saved with onevisit ingest. Not yet cited."
            ),
        }
        if dry_run:
            print(
                f"plan    {source_id}  {url}\n        {' '.join(clean_cmd)}\n        {' '.join(ingest_cmd)}"
            )
            continue
        done = runner(clean_cmd, REPO)
        if done.returncode != 0:
            print(f"failed  {source_id}: clean_html.py: {(done.stderr or done.stdout).strip()[-300:]}")
            failures += 1
            continue
        append_source_row(data_dir / "sources.csv", row)
        taken.add(source_id)
        for key in keys:
            saved_urls.setdefault(key, source_id)
        done = runner(ingest_cmd, REPO)
        if done.returncode != 0:
            print(f"failed  {source_id}: onevisit ingest: {(done.stdout + done.stderr).strip()[-300:]}")
            failures += 1
            continue
        # onevisit ingest marks the row "ok", which the search reads as "quote it": not yet.
        set_source_field(data_dir / "sources.csv", source_id, "status", REVIEW_STATUS)
        print(f"saved   {source_id}  {url}  (status {REVIEW_STATUS})")
    if not dry_run:
        print(
            "Next: read each new data/pages/<id>.md; when it is the official text and worth "
            "quoting, `crawl.py approve --ids <id>` makes it searchable. Facts still need a "
            "verbatim quote in data/services/ and validate.py."
        )
    return 1 if failures else 0


def approve(data_dir: Path, ids: list[str]) -> int:
    """Status "ok" for pages a person has read: the search quotes them from the next query."""
    rows = {r["id"]: r for r in read_sources(data_dir)}
    failures = 0
    for source_id in ids:
        row = rows.get(source_id)
        if row is None:
            print(f"skip    {source_id}: not in sources.csv")
        elif row.get("status") != REVIEW_STATUS:
            print(f"skip    {source_id}: status is {row.get('status') or 'empty'}, not {REVIEW_STATUS}")
        elif not (data_dir / (row.get("snapshot") or "-")).is_file():
            print(f"skip    {source_id}: no saved page ({row.get('snapshot') or 'no snapshot'})")
        else:
            set_source_field(data_dir / "sources.csv", source_id, "status", "ok")
            print(f"ok      {source_id}: searchable")
            continue
        failures += 1
    return 1 if failures else 0


# ----------------------------------------------------------------------------- command line


def _no_transport(url: str, headers: dict[str, str], timeout: float, max_bytes: int) -> Response:
    raise RuntimeError(f"rescore is offline: no request to {url}")


def _inside(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--seeds", type=Path, default=DEFAULT_SEEDS, help="configuration (crawl_seeds.json)")
    ap.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR, help="the repository's data/ folder")
    sub = ap.add_subparsers(dest="mode", required=True)

    d = sub.add_parser("discover", help="crawl from the seeds into --out (no repository writes)")
    d.add_argument("--topic", required=True)
    d.add_argument("--out", type=Path, required=True)
    d.add_argument("--depth", type=int, default=2)
    d.add_argument("--max-pages", type=int, default=300)
    d.add_argument("--no-sitemaps", action="store_true")
    d.add_argument("--no-search", action="store_true")
    d.add_argument("--min-score", type=int, help="override the topic's min_score")

    s = sub.add_parser("rescore", help="score a discover run again after changing keywords (offline)")
    s.add_argument("--topic", required=True)
    s.add_argument("--out", type=Path, required=True, help="the --out folder of discover")
    s.add_argument("--min-score", type=int, help="override the topic's min_score")

    r = sub.add_parser("refresh", help="compare saved pages with the live ones")
    r.add_argument("--topic", help="only the topic's sources (default: every page in sources.csv)")
    r.add_argument("--ids", help="comma-separated source ids")
    r.add_argument("--from-crawl", type=Path, help="reuse the raw files of a discover run")
    r.add_argument("--offline", action="store_true", help="never download: only --from-crawl files")
    r.add_argument("--out", type=Path, help="where to write the new text and a diff of changed pages")

    i = sub.add_parser("ingest", help="save the manifest entries a person picked (status review)")
    i.add_argument("--from-crawl", type=Path, required=True, help="the --out folder of discover")
    i.add_argument("--ids", required=True, help="suggested ids from the manifest; rename with old=new")
    i.add_argument("--python", default=sys.executable, help="Python with BeautifulSoup for clean_html.py")
    i.add_argument("--onevisit", help="the onevisit command (default .venv/bin/onevisit)")
    i.add_argument("--dry-run", action="store_true")
    i.add_argument("--force", action="store_true", help="overwrite a data/pages/<id>.md already there")

    a = sub.add_parser("approve", help="make pages in review searchable, after reading them")
    a.add_argument("--ids", required=True, help="comma-separated source ids in status review")

    args = ap.parse_args(argv)
    data_dir = args.data_dir

    if args.mode in ("discover", "rescore"):
        if _inside(args.out, data_dir):
            raise SystemExit("--out must be outside the data folder: discover never writes in the repository")
        policy, topic = load_config(args.seeds, args.topic)
        assert topic is not None
        if args.min_score is not None:
            topic.min_score = args.min_score
        if args.mode == "rescore":
            crawler = Crawler(
                policy, topic, PoliteClient(policy, transport=_no_transport), args.out, data_dir
            )
            manifest = crawler.rescore()
        else:
            crawler = Crawler(
                policy,
                topic,
                PoliteClient(policy),
                args.out,
                data_dir,
                max_pages=args.max_pages,
                max_depth=args.depth,
                use_sitemaps=not args.no_sitemaps,
                use_search=not args.no_search,
            )
            manifest = crawler.run()
        c = manifest["counts"]
        print(
            f"{c['pages_fetched']} pages fetched ({c['http_requests']} requests), {c['kept']} relevant: "
            f"{c['kept_new']} new, {c['kept_already_saved']} already in sources.csv. "
            f"Manifest: {args.out / 'manifest.json'}"
        )
        new = sorted(
            (
                e
                for e in manifest["entries"]
                if e["kept"] and not e["already_saved_as"] and not e["duplicate_of"]
            ),
            key=lambda e: -e["score"],
        )
        for e in new[:40]:
            print(f"  {e['score']:>4}  {e['suggested_id']:<45} {e['final_url']}")
        return 0

    if args.mode == "refresh":
        policy, topic = load_config(args.seeds, args.topic)
        if args.out is not None and _inside(args.out, data_dir):
            raise SystemExit("--out must be outside the data folder")
        client = None if args.offline else PoliteClient(policy)
        ids = {x.strip() for x in args.ids.split(",")} if args.ids else None
        results = refresh(
            data_dir,
            policy,
            client,
            kit_cleaner(policy),
            topic=topic,
            ids=ids,
            crawl_dir=args.from_crawl,
            out_dir=args.out,
        )
        for res in results:
            print(f"{res['status']:<10} {res['id']:<40} {res['detail']}")
        totals = {
            s: sum(1 for x in results if x["status"] == s)
            for s in ("unchanged", "changed", "failed", "skipped")
        }
        print(", ".join(f"{n} {s}" for s, n in totals.items()))
        if args.out is not None:
            args.out.mkdir(parents=True, exist_ok=True)
            (args.out / "refresh.json").write_text(
                json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8"
            )
        return 0

    if args.mode == "approve":
        return approve(data_dir, [x.strip() for x in args.ids.split(",") if x.strip()])

    policy, _ = load_config(args.seeds, None)
    return ingest(
        args.from_crawl,
        data_dir,
        policy,
        ids=parse_ids(args.ids),
        python=args.python,
        onevisit=args.onevisit,
        dry_run=args.dry_run,
        force=args.force,
    )


if __name__ == "__main__":
    sys.exit(main())
