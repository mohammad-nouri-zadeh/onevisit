"""The knowledge crawler (data/tools/crawl.py): allowlist, relevance, robots, pacing, manifest,
refresh and ingest. Local fixture pages and a fake web: no test opens a network connection.

python -m pytest tests/streamlit/test_crawl.py -q
"""

from __future__ import annotations

import csv
import json
import pathlib
import shutil
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "data" / "tools"))

import crawl  # noqa: E402  (data/tools is not a package)

POLICY, TOPIC = crawl.load_config(crawl.DEFAULT_SEEDS, "carta-identita")
KIT_PYTHON = ROOT / ".venv" / "bin" / "python"
KIT_ONEVISIT = ROOT / ".venv" / "bin" / "onevisit"

# The fixtures copy the City's markup: long lines and the curly apostrophe it uses.
CIE_PAGE = """<!doctype html><html lang="it"><head><title>Carta d'identità - Comune di Milano</title>
<script>var menu = "carta d'identità carta d'identità";</script></head><body>
<header><nav><a href="/servizi/tributi">Tributi</a>
<a href="/servizi/anagrafe/carta-d-identita">Carta d’identità</a></nav></header>
<main><h1>Carta d’identità</h1>
<p>Prenota un appuntamento per ottenere o rinnovare la carta di identità elettronica (CIE).
La CIE vale come documento di espatrio. Porta una fototessera recente e la vecchia carta d'identità.</p>
<p>In caso di smarrimento o furto serve la denuncia. Il PIN e il PUK arrivano con la ricevuta.</p>
<p>La carta d'identità elettronica viene spedita a casa. Costo della CIE: 22,20 euro.</p>
<ul><li><a href="/servizi/anagrafe/carta-d-identita/foto">Requisiti della fototessera</a></li>
<li><a href="https://www.cartaidentita.interno.gov.it/info-utili/viaggiare/">Viaggiare con la CIE</a></li>
<li><a href="https://www.example.org/carta-identita">Carta d'identità altrove</a></li>
<li><a href="https://servizicrm.comune.milano.it/spec/appuntamenti/anagrafecie">Prenota CIE</a></li>
<li><a href="/servizi/tributi/tari">Pagare la TARI</a></li>
<li><a href="mailto:x@example.org">Scrivici</a></li></ul>
</main><footer>Piede di pagina: carta d'identità carta d'identità carta d'identità</footer></body></html>"""  # noqa: E501, RUF001

FOTO_PAGE = """<html><head><title>Fototessera per la carta d'identità</title></head><body><main>
<h1>Requisiti della fototessera</h1><p>La fototessera per la carta d'identità elettronica (CIE)
deve essere recente, a colori, 45 x 35 mm. La carta d'identità riporta la foto.</p>
<p>Per la CIE serve una foto stampata. Dettagli:
<a href="/servizi/anagrafe/carta-d-identita/foto/dettagli">Altri dettagli sulla carta d'identità</a>
<a href="/servizi/anagrafe/carta-d-identita-bis">La stessa pagina altrove</a></p>
</main></body></html>"""

TARI_PAGE = """<html><head><title>TARI</title></head><body><main><h1>Tassa rifiuti</h1>
<p>La TARI si paga entro il 30 settembre. Il Comune invia l'avviso a casa. Questo testo è lungo
abbastanza da essere il testo principale della pagina, e non parla del documento che cerchiamo.
Una specie di tassa sui rifiuti urbani, calcolata sui metri quadri dell'abitazione.</p>
</main></body></html>"""

VIAGGIARE_PAGE = """<html><head><title>Viaggiare - Carta di Identità Elettronica (CIE)</title></head><body>
<article><h1>Viaggiare</h1><p>La Carta di Identità Elettronica (CIE) è valida per l'espatrio nei Paesi UE.
I minori viaggiano con la CIE valida per l'espatrio. La CIE è un documento di riconoscimento.</p>
<p>Per i Paesi extra UE serve il passaporto, non la carta di identità.</p></article></body></html>"""  # noqa: E501


class FakeWeb:
    """A tiny web: url -> (status, headers, body) or a list of answers served in turn."""

    def __init__(self, pages: dict[str, object]) -> None:
        self.pages = pages
        self.calls: list[str] = []

    def __call__(
        self, url: str, headers: dict[str, str], timeout: float, max_bytes: int
    ) -> crawl.Response:
        self.calls.append(url)
        assert headers["User-Agent"].startswith("OneVisitCrawler/")  # who we are, never a browser
        assert headers["Accept-Language"] == "it-IT,it;q=0.9,en;q=0.8"
        answer = self.pages.get(url)
        if isinstance(answer, list):
            answer = answer.pop(0) if len(answer) > 1 else answer[0]
        if answer is None:
            return crawl.Response(url, 404, {"content-type": "text/html"}, b"not found")
        if isinstance(answer, crawl.Response):
            return crawl.Response(
                answer.url, answer.status, answer.headers, answer.body, answer.error
            )
        status, headers_, body = answer  # type: ignore[misc]
        data = body.encode("utf-8") if isinstance(body, str) else body
        return crawl.Response(url, status, {k.lower(): v for k, v in headers_.items()}, data)


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0
        self.sleeps: list[float] = []

    def clock(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(round(seconds, 3))
        self.now += seconds


HTML = {"Content-Type": "text/html; charset=utf-8"}


def client_for(web: FakeWeb, clock: FakeClock | None = None) -> crawl.PoliteClient:
    clock = clock or FakeClock()
    return crawl.PoliteClient(
        POLICY, transport=web, clock=clock.clock, sleep=clock.sleep, logger=lambda m: None
    )


def make_data_dir(
    tmp_path: pathlib.Path, rows: list[dict[str, str]], pages: dict[str, str] | None = None
) -> pathlib.Path:
    data = tmp_path / "data"
    (data / "pages").mkdir(parents=True)
    (data / "services").mkdir()
    header = [
        "id",
        "title",
        "url",
        "publisher",
        "kind",
        "snapshot",
        "retrieved_at",
        "status",
        "notes",
    ]
    with (data / "sources.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=header, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in header})
    for sid, text in (pages or {}).items():
        (data / "pages" / f"{sid}.md").write_text(text, encoding="utf-8")
    return data


def saved_page(sid: str, url: str, body: str, service: str = "carta-identita") -> str:
    return (
        f"---\nsource_id: {sid}\nurl: {url}\nente: Comune di Milano\nservizio:\n- {service}\n"
        f"verified_at: '2026-10-04'\ncontent_hash: {crawl.content_hash(body)}\n---\n\n{body}"
    )


# --------------------------------------------------------------------------- configuration


def test_seeds_file_has_the_topic_and_its_seeds():
    data = json.loads(crawl.DEFAULT_SEEDS.read_text(encoding="utf-8"))
    assert set(data["topics"]) >= {"carta-identita"}
    for url in (
        "https://www.comune.milano.it/servizi/anagrafe/carta-d-identita",
        "https://www.comune.milano.it/en/servizi/anagrafe/carta-d-identita",
        "https://www.comune.milano.it/argomenti/anagrafe",
        "https://www.yesmilano.it/en/study/how-to/id-card",
        "https://www.cartaidentita.interno.gov.it/",
    ):
        assert url in TOPIC.seeds
    assert POLICY.host_intervals_s["yesmilano.it"] >= 3
    assert POLICY.default_interval_s >= 1
    with pytest.raises(SystemExit, match="carta-identita"):
        crawl.load_config(crawl.DEFAULT_SEEDS, "no-such-topic")


def test_topic_sources_come_from_sources_csv_without_open_data():
    rows = crawl.topic_source_rows(ROOT / "data", TOPIC)
    ids = {r["id"] for r in rows}
    assert "cie" in ids and any(i.startswith("cie-faq-") for i in ids)
    assert all(r["kind"] != "opendata" for r in rows)
    assert "residenza-estero" not in ids


# --------------------------------------------------------------------------- allowlist and URLs


@pytest.mark.parametrize(
    "url",
    [
        "https://www.comune.milano.it/servizi/anagrafe/carta-d-identita",
        "https://servizicrm.comune.milano.it/centro-supporto/KA-00411/Definizione",
        "https://formshd3.comune.milano.it/rwe2/module_preview.jsp?MODULE_TAG=X",
        "https://studyandwork.yesmilano.it/en/study/how-to/id-card",
        "https://www.cartaidentita.interno.gov.it/info-utili/viaggiare/",
        "https://dait.interno.gov.it/documenti/circ-dait-060-servdemo-24-07-2026.pdf",
        "https://www.poliziadistato.it/articolo/denunce-online",
    ],
)
def test_allowlist_accepts_official_pages(url):
    assert POLICY.block_reason(url) is None


@pytest.mark.parametrize(
    "url, reason",
    [
        ("https://www.example.org/carta-identita", "outside the allowlist"),
        ("https://comune.milano.it.evil.example/x", "outside the allowlist"),
        ("https://fakecomune.milano.it.example.com/", "outside the allowlist"),
        ("https://www.interno.gov.it/it/carta-identita", "outside the allowlist"),
        ("https://servizicdm.comune.milano.it/cdmlogin/?realm=/Servizi", "blocked host"),
        ("https://servizicrm.comune.milano.it/spec/appuntamenti/anagrafecie", "blocked pattern"),
        ("https://www.comune.milano.it/ricerca?q=carta", "blocked pattern"),
        ("https://www.cartaidentita.interno.gov.it/fr/la-carte/", "blocked pattern"),
        ("https://www.cartaidentita.interno.gov.it/pa-e-imprese/esercenti/", "blocked pattern"),
        ("https://www.cartaidentita.interno.gov.it/watch?v=wmwdW_51Ur0", "blocked pattern"),
        ("https://www.yesmilano.it/en/news/jeff-koons", "blocked pattern"),
        ("https://www.comune.milano.it/documents/foto.jpg", "not a page"),
    ],
)
def test_allowlist_refuses_everything_else(url, reason):
    assert reason in (POLICY.block_reason(url) or "")


def test_sitemaps_and_searches_skip_page_filters_but_never_the_allowlist():
    assert POLICY.block_reason("https://www.yesmilano.it/sitemap.xml", page_filters=False) is None
    assert (
        POLICY.block_reason(
            "https://servizicrm.comune.milano.it/Support/SearchService?query=CIE",
            page_filters=False,
        )
        is None
    )
    assert "outside" in POLICY.block_reason(
        "https://www.example.org/sitemap.xml", page_filters=False
    )


def test_normalize_url():
    base = "https://www.comune.milano.it/servizi/anagrafe/carta-d-identita"
    assert (
        crawl.normalize_url("/argomenti/anagrafe#top", base=base)
        == "https://www.comune.milano.it/argomenti/anagrafe"
    )
    assert (
        crawl.normalize_url("http://WWW.Comune.Milano.it:443/a b")
        == "https://www.comune.milano.it/a%20b"
    )
    assert crawl.normalize_url("mailto:x@example.org", base=base) is None
    assert crawl.normalize_url("javascript:void(0)", base=base) is None
    ka = "/centro-supporto/KA-00411/Definizione?query=CIE"
    assert (
        crawl.normalize_url(
            ka, base="https://servizicrm.comune.milano.it/Support/SearchService", policy=POLICY
        )
        == "https://servizicrm.comune.milano.it/centro-supporto/KA-00411/Definizione"
    )
    assert (
        crawl.normalize_url("https://www.comune.milano.it/x?utm_source=a&b=1", policy=POLICY)
        == "https://www.comune.milano.it/x?b=1"
    )
    pdf = "https://www.comune.milano.it/documents/d/guest/x?download=true"
    assert crawl.normalize_url(pdf, policy=POLICY) == pdf  # fetching keeps the parameters
    spaced = crawl.normalize_url(
        "https://comune.milano.it/servizi/foto?album=Anagrafe e stato civile"
    )
    assert spaced == "https://comune.milano.it/servizi/foto?album=Anagrafe%20e%20stato%20civile"
    twice_escaped = "https://www.comune.milano.it/documents/d/guest/x?amp;download=true"
    assert crawl.normalize_url(twice_escaped, policy=POLICY) == pdf


def test_canonical_key_joins_the_same_page():
    a = crawl.canonical_key("https://servizicrm.comune.milano.it/centro-supporto/KA-00354/", POLICY)
    b = crawl.canonical_key(
        "https://servizicrm.comune.milano.it/centro-supporto/KA-00354/Neonati-CIE", POLICY
    )
    assert a == b
    c = crawl.canonical_key(
        "https://www.comune.milano.it/documents/20118/1/x.pdf/abc?version=1.0&t=1&download=true",
        POLICY,
    )
    d = crawl.canonical_key("https://www.comune.milano.it/documents/20118/1/x.pdf/abc", POLICY)
    assert c == d
    assert crawl.canonical_key(
        "https://www.yesmilano.it/en/study/how-to/id-card", POLICY
    ) == crawl.canonical_key("https://studyandwork.yesmilano.it/en/study/how-to/id-card/", POLICY)
    assert crawl.canonical_key("https://www.comune.milano.it/a/", POLICY) == crawl.canonical_key(
        "https://www.comune.milano.it/a", POLICY
    )


def test_suggested_ids():
    assert (
        crawl.suggest_id("https://servizicrm.comune.milano.it/centro-supporto/KA-00411/Def", TOPIC)
        == "cie-faq-00411"
    )
    assert (
        crawl.suggest_id("https://www.cartaidentita.interno.gov.it/info-utili/viaggiare/", TOPIC)
        == "cie-ministero-viaggiare"
    )
    assert (
        crawl.suggest_id("https://www.cartaidentita.interno.gov.it/en/help/", TOPIC)
        == "cie-ministero-en-help"
    )
    assert (
        crawl.suggest_id(
            "https://dait.interno.gov.it/documenti/circ-dait-060-servdemo-24-07-2026.pdf", TOPIC
        )
        == "circ-dait-060-2026"
    )
    assert (
        crawl.suggest_id("https://www.comune.milano.it/w/servizi-civici.-addio-alle-carte", TOPIC)
        == "news-servizi-civici-addio-alle-carte"
    )
    assert (
        crawl.suggest_id("https://www.cartaidentita.interno.gov.it/", TOPIC) == "cie-ministero-home"
    )
    other = crawl.Topic(name="t", id_prefix="t")
    assert crawl.suggest_id("https://www.comune.milano.it/", other) == "t-comune-milano-it-home"
    assert (
        crawl.suggest_id(
            "https://studyandwork.yesmilano.it/en/work/getting-started-guide/identity-card", TOPIC
        )
        == "yesmilano-identity-card"
    )


# --------------------------------------------------------------------------- parsing and relevance


def test_parse_html_reads_main_text_links_and_title():
    page = crawl.parse_html(CIE_PAGE.encode("utf-8"), "text/html; charset=utf-8")
    assert page.title == "Carta d'identità - Comune di Milano"
    assert page.h1 == "Carta d’identità"  # noqa: RUF001  (the City's own apostrophe)
    assert "22,20 euro" in page.text
    assert "Tributi" not in page.text and "var menu" not in page.text  # nav, footer, script are out
    assert "Piede di pagina" not in page.text  # the footer's repetitions are not main text
    links = dict(page.links)
    assert links["/servizi/anagrafe/carta-d-identita/foto"] == "Requisiti della fototessera"
    assert links["/servizi/tributi"] == "Tributi"  # menu links are still links


def test_parse_html_without_main_uses_article_then_body():
    assert "valida per l'espatrio" in crawl.parse_html(VIAGGIARE_PAGE).text
    bare = (
        "<html><body><div>Solo testo, nessun main. Carta d'identità.</div>"
        "<footer>piede</footer></body></html>"
    )
    assert crawl.parse_html(bare).text == "Solo testo, nessun main. Carta d'identità."
    unclosed_head = "<html><head><title>T</title><body><p>Carta d'identità</p></body></html>"
    assert "Carta d'identità" in crawl.parse_html(unclosed_head).text


def test_relevance_scores_cie_pages_and_drops_others():
    rel = crawl.Relevance(TOPIC)
    cie = crawl.parse_html(CIE_PAGE)
    score, hits, strong = rel.score(cie.text, cie.title)
    assert rel.is_relevant(score, strong)
    assert hits["carta d'identita"] >= 1 and hits["cie"] >= 2 and hits["pin"] == 1
    tari = crawl.parse_html(TARI_PAGE)
    score, hits, strong = rel.score(tari.text, tari.title)
    assert not rel.is_relevant(score, strong)
    assert "cie" not in hits  # "specie" is not "CIE": whole words only


def test_relevance_normalises_accents_and_apostrophes_and_caps_counts():
    rel = crawl.Relevance(TOPIC)
    a = rel.score("La Carta d’Identità e la CARTA D'IDENTITA")[1]  # noqa: RUF001  (both apostrophes)
    assert a["carta d'identita"] == 2
    many = rel.score("CIE " * 50)
    few = rel.score("CIE " * TOPIC.count_cap)
    assert many[0] == few[0]  # a page repeating a word 50 times does not win


def test_link_score():
    rel = crawl.Relevance(TOPIC)
    assert rel.link_score("https://www.comune.milano.it/servizi/anagrafe/carta-d-identita") >= 3
    assert rel.link_score("https://www.comune.milano.it/x", "Requisiti della fototessera") >= 3
    assert (
        rel.link_score("https://www.comune.milano.it/servizi/tributi/tari", "Pagare la TARI") == 0
    )
    # a host all about the topic gives no score of its own: a link needs a keyword
    assert rel.link_score("https://www.cartaidentita.interno.gov.it/cookie-policy/") == 0
    assert rel.link_score("https://www.cartaidentita.interno.gov.it/attiva/") >= 1
    assert rel.on_topic_host("https://www.cartaidentita.interno.gov.it/attiva/")


def test_title_counts_without_the_site_name_and_strong_hits_come_from_the_text():
    rel = crawl.Relevance(TOPIC, POLICY.title_suffixes)
    ministry = "Cookie policy - Carta di Identità Elettronica (CIE)"
    assert rel.clean_title(ministry) == "cookie policy"
    assert rel.clean_title("Carta d'identità - Comune di Milano") == "carta d'identita"
    score, _hits, strong = rel.score("", ministry)
    assert (score, strong) == (0, 0) and not rel.is_relevant(score, strong)
    # a title on the topic still adds its bonus, but never a strong hit
    text = "La carta d'identità elettronica (CIE) si rinnova allo sportello. Porta la CIE."
    plain = rel.score(text)
    titled = rel.score(text, "Carta d'identità - Comune di Milano")
    assert titled[0] > plain[0] and titled[2] == plain[2]


HUB_PAGE = (
    "<html><head><title>Richiesta CIE - Carta di Identità Elettronica (CIE)</title></head><body>"
    "<header>Carta d'identità elettronica CIE CIE CIE</header><main><div class='cards'>"
    + "<a href='/richiedi/x/'>Carta di identità elettronica (CIE): rilascio e rinnovo</a> " * 6
    + "</div></main><footer>CIE carta d'identità</footer></body></html>"
)


def test_pages_are_scored_on_the_text_ingest_keeps():
    hub_url = "https://www.cartaidentita.interno.gov.it/richiesta-cie/"
    assert crawl.scoring_text(HUB_PAGE, hub_url, POLICY) == ""  # the Ministry keeps <article>
    rel = crawl.Relevance(TOPIC, POLICY.title_suffixes)
    page = crawl.parse_html(HUB_PAGE)
    assert rel.is_relevant(*rel.score(page.text, page.title)[::2])  # the whole page would pass
    score, _hits, strong = rel.score(crawl.scoring_text(HUB_PAGE, hub_url, POLICY), page.title)
    assert not rel.is_relevant(score, strong)
    viaggiare = crawl.scoring_text(
        VIAGGIARE_PAGE, "https://www.cartaidentita.interno.gov.it/info-utili/viaggiare/", POLICY
    )
    assert viaggiare.startswith("Viaggiare") and "valida per l'espatrio" in viaggiare
    ka_url = "https://servizicrm.comune.milano.it/centro-supporto/KA-00999/CIE-espatrio"
    ka = crawl.scoring_text(KA_RAW_FOR_SCORING, ka_url, POLICY)
    assert "Posso usare la CIE" in ka and "menu" not in ka and "Ti è stato utile" not in ka


KA_RAW_FOR_SCORING = (
    "<html><head><title>Centro supporto</title></head><body><nav>menu</nav><main>"
    "<h1 id='faqtitle'>Posso usare la CIE come documento di espatrio?</h1>"
    "<div id='faqcontent'><p>La Carta di Identità Elettronica (CIE) è valida.</p></div>"
    "<div id='faqsentiment'>Ti è stato utile?</div></main></body></html>"
)


def test_a_topic_host_only_breaks_ties_in_the_queue(tmp_path):
    data = make_data_dir(tmp_path, [])
    client = crawl.PoliteClient(POLICY, transport=crawl._no_transport, logger=lambda m: None)
    crawler = crawl.Crawler(
        POLICY, small_topic(), client, tmp_path / "out", data, logger=lambda m: None
    )
    city = "https://www.comune.milano.it/servizi/pin-puk"  # same words, same score
    ministry = "https://www.cartaidentita.interno.gov.it/servizi/pin-puk/"
    better = "https://www.comune.milano.it/servizi/anagrafe/carta-d-identita/pin-puk"
    for url in (city, ministry, better):
        crawler.enqueue(url, 1, "seed")
    assert crawler.relevance.link_score(city) == crawler.relevance.link_score(ministry)
    order = [crawler.pending[item.key]["url"] for item in sorted(crawler.heap)]
    assert order == [better, ministry, city]
    assert not crawler.enqueue("https://www.cartaidentita.interno.gov.it/notizie/", 1, "seed")


# --------------------------------------------------------------------------- robots.txt and pacing


def test_parse_robots_with_prefixes_and_wildcards():
    rules = crawl.parse_robots(
        "User-agent: *\nDisallow: /fascicolo-del-cittadino/\nDisallow: /search/*\n"
        "Disallow: /*.pdf$\n"
        "Allow: /search/ok\nCrawl-delay: 4\nSitemap: https://www.comune.milano.it/sitemap.xml\n"
    )
    assert rules.allows("https://www.comune.milano.it/servizi/anagrafe/carta-d-identita")
    assert not rules.allows("https://www.comune.milano.it/fascicolo-del-cittadino/x")
    assert not rules.allows(
        "https://www.comune.milano.it/search/anything"
    )  # wildcard, ignored by robotparser
    assert not rules.allows("https://www.comune.milano.it/doc/x.pdf")
    assert rules.allows("https://www.comune.milano.it/doc/x.pdf?download=true")
    assert rules.crawl_delay == 4
    assert rules.sitemaps == ["https://www.comune.milano.it/sitemap.xml"]


def test_robots_disallow_means_the_page_is_never_requested():
    page = "https://www.comune.milano.it/fascicolo/privato"
    web = FakeWeb(
        {
            "https://www.comune.milano.it/robots.txt": (
                200,
                {},
                "User-agent: *\nDisallow: /fascicolo/\n",
            ),
            page: (200, HTML, CIE_PAGE),
        }
    )
    answer = client_for(web).get(page)
    assert answer.blocked and "robots.txt" in answer.error
    assert page not in web.calls


def test_robots_missing_allows_and_robots_refused_blocks_the_host():
    web = FakeWeb(
        {
            "https://servizicrm.comune.milano.it/centro-supporto/KA-1/X": (
                200,
                HTML,
                "<main>ok</main>",
            ),
            "https://www.yesmilano.it/robots.txt": [(403, {}, "no"), (403, {}, "no")],
            "https://www.yesmilano.it/en/study/how-to/id-card": (200, HTML, "<main>ok</main>"),
        }
    )
    clock = FakeClock()
    client = client_for(web, clock)
    assert client.get("https://servizicrm.comune.milano.it/centro-supporto/KA-1/X").status == 200
    blocked = client.get("https://www.yesmilano.it/en/study/how-to/id-card")
    assert blocked.blocked and "https://www.yesmilano.it/en/study/how-to/id-card" not in web.calls
    assert 30.0 not in clock.sleeps  # a 403 is the site saying no: never retried
    assert web.calls.count("https://www.yesmilano.it/robots.txt") == 1


def test_throttle_spaces_requests_per_host():
    clock = FakeClock()
    throttle = crawl.HostThrottle(POLICY, clock.clock, clock.sleep)
    throttle.wait("www.comune.milano.it")
    throttle.wait("www.comune.milano.it")
    assert clock.sleeps == [1.0]
    throttle.wait("www.yesmilano.it")
    clock.now += 1
    throttle.wait("studyandwork.yesmilano.it")  # same group as www.yesmilano.it: 3 s
    assert clock.sleeps[-1] == 2.0
    throttle.crawl_delays["www.comune.milano.it"] = 5.0
    throttle.wait("www.comune.milano.it")
    assert throttle.interval("www.comune.milano.it") == 5.0


def test_retry_once_after_429_or_dropped_connection():
    url = "https://www.comune.milano.it/servizi/anagrafe/carta-d-identita"
    for first in (
        (429, {}, "slow down"),
        crawl.Response(url, 0, {}, b"", error="ConnectionResetError: [Errno 104] reset"),
    ):
        web = FakeWeb({url: [first, (200, HTML, CIE_PAGE)]})
        clock = FakeClock()
        answer = client_for(web, clock).get(url)
        assert answer.status == 200 and answer.retried
        assert clock.sleeps.count(30.0) == 1
        assert web.calls.count(url) == 2
    web = FakeWeb({url: [(429, {}, "slow"), (429, {}, "slow"), (200, HTML, CIE_PAGE)]})
    assert client_for(web).get(url).status == 429  # only one retry


def test_a_403_is_a_refusal_not_retried_and_the_report_says_to_ask_the_site():
    url = "https://www.comune.milano.it/servizi/anagrafe/carta-d-identita"
    web = FakeWeb({url: [(403, {}, ""), (200, HTML, CIE_PAGE)]})
    clock = FakeClock()
    answer = client_for(web, clock).get(url)
    assert answer.status == 403 and not answer.retried and web.calls.count(url) == 1
    assert "ask the site" in answer.error and 30.0 not in clock.sleeps


def test_the_crawler_says_who_it_is():
    agent = crawl.CRAWLER_HEADERS["User-Agent"]
    assert agent.startswith(crawl.ROBOTS_AGENT + "/") and "github.com" in agent
    assert "Mozilla" not in agent and "Chrome" not in agent
    assert 403 not in crawl.Policy(allowed_domains=[]).retry_statuses
    assert 403 not in POLICY.retry_statuses  # the seeds file too


def test_redirects_are_followed_only_inside_the_allowlist():
    start = "https://servizicrm.comune.milano.it/centro-supporto/KA-2/Y"
    web = FakeWeb(
        {
            start: (302, {"Location": "https://servizicdm.comune.milano.it/cdmlogin/?x=1"}, ""),
            "https://www.yesmilano.it/en/study/how-to/id-card": (
                301,
                {"Location": "https://studyandwork.yesmilano.it/en/study/how-to/id-card"},
                "",
            ),
            "https://studyandwork.yesmilano.it/en/study/how-to/id-card": (
                200,
                HTML,
                "<main>ID card</main>",
            ),
        }
    )
    client = client_for(web)
    login = client.get(start)
    assert login.blocked and "blocked host" in login.error
    assert not any("servizicdm" in call for call in web.calls)
    moved = client.get("https://www.yesmilano.it/en/study/how-to/id-card")
    assert moved.status == 200
    assert moved.final_url == "https://studyandwork.yesmilano.it/en/study/how-to/id-card"


# --------------------------------------------------------------------------- discover and manifest


def site() -> FakeWeb:
    search = json.dumps(
        [
            {
                "link": "/centro-supporto/KA-00999/Nuova-domanda-CIE?query=CIE",
                "question": "Nuova domanda sulla CIE",
                "category": "/servizi/anagrafe/carta-d-identita",
            },
            {
                "link": "/centro-supporto/KA-00888/Tari?query=CIE",
                "question": "Come pago la TARI?",
                "category": "/tributi",
            },
        ]
    )
    ka = (
        "<html><head><title>Nuova domanda sulla CIE</title></head><body><main>"
        "<h2 id='faqtitle'>Nuova domanda sulla Carta di Identità Elettronica (CIE)</h2>"
        "<div id='faqcontent'><p>La CIE si rinnova ... la carta d'identità "
        "elettronica, la CIE, la carta d'identità.</p></div>"
        "<p id='faqlastmodified'>Ultimo aggiornamento: 01/10/2026"
        "</p></main></body></html>"
    )
    return FakeWeb(
        {
            "https://www.comune.milano.it/servizi/anagrafe/carta-d-identita": (200, HTML, CIE_PAGE),
            "https://www.comune.milano.it/servizi/anagrafe/carta-d-identita/foto": (
                200,
                HTML,
                FOTO_PAGE,
            ),
            "https://www.comune.milano.it/servizi/anagrafe/carta-d-identita/foto/dettagli": (
                200,
                HTML,
                FOTO_PAGE,
            ),
            "https://www.comune.milano.it/servizi/tributi": (200, HTML, TARI_PAGE),
            "https://www.comune.milano.it/servizi/anagrafe/carta-d-identita-bis": (
                200,
                HTML,
                CIE_PAGE,
            ),
            "https://www.cartaidentita.interno.gov.it/info-utili/viaggiare/": (
                200,
                HTML,
                VIAGGIARE_PAGE,
            ),
            "https://www.cartaidentita.interno.gov.it/robots.txt": (
                200,
                {},
                "User-agent: *\nDisallow: /wp-admin/\nSitemap: https://www.cartaidentita.interno.gov.it/sitemap.xml\n",
            ),
            "https://www.cartaidentita.interno.gov.it/sitemap.xml": (
                200,
                {"Content-Type": "text/xml"},
                (
                    '<?xml version="1.0"?>'
                    '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" '
                    'xmlns:image="http://www.google.com/schemas/sitemap-image/1.1">'
                    "<url><loc>https://www.cartaidentita.interno.gov.it/info-utili/viaggiare/</loc>"
                    "<image:image><image:loc>https://www.cartaidentita.interno.gov.it/x.png</image:loc></image:image></url>"
                    "<url><loc>https://www.cartaidentita.interno.gov.it/fr/voyager/</loc></url>"
                    "<url><loc>https://www.cartaidentita.interno.gov.it/attiva/</loc></url></urlset>"
                ),
            ),
            "https://www.cartaidentita.interno.gov.it/attiva/": (
                200,
                HTML,
                VIAGGIARE_PAGE.replace("Viaggiare", "Attiva"),
            ),
            "https://servizicrm.comune.milano.it/Support/SearchService?query=CIE": (
                200,
                {"Content-Type": "application/json"},
                search,
            ),
            "https://servizicrm.comune.milano.it/centro-supporto/KA-00999/Nuova-domanda-CIE": (
                200,
                HTML,
                ka,
            ),
        }
    )


def small_topic(**overrides) -> crawl.Topic:
    topic = crawl.Topic.from_dict(
        "carta-identita", json.loads(crawl.DEFAULT_SEEDS.read_text())["topics"]["carta-identita"]
    )
    topic.seeds = ["https://www.comune.milano.it/servizi/anagrafe/carta-d-identita"]
    topic.seed_sources = {"id_patterns": ["^cie$"], "exclude_kinds": ["opendata"]}
    topic.search_endpoints = [dict(topic.search_endpoints[0], queries=["CIE"])]
    topic.sitemaps = {"hosts": ["www.cartaidentita.interno.gov.it"], "max_files_per_host": 2}
    for key, value in overrides.items():
        setattr(topic, key, value)
    return topic


def run_crawl(tmp_path, web, **kwargs):
    data = make_data_dir(
        tmp_path,
        [
            {
                "id": "cie",
                "url": "https://www.comune.milano.it/servizi/anagrafe/carta-d-identita",
                "kind": "page",
                "snapshot": "pages/cie.md",
            },
            {
                "id": "cie-ministero-viaggiare",
                "url": "https://www.cartaidentita.interno.gov.it/info-utili/viaggiare/",
                "kind": "page",
                "snapshot": "pages/cie-ministero-viaggiare.md",
            },
            {
                "id": "ds549",
                "url": "https://dati.comune.milano.it/dataset/ds549",
                "kind": "opendata",
            },
        ],
    )
    out = tmp_path / "crawl"
    clock = FakeClock()
    client = crawl.PoliteClient(
        POLICY, transport=web, clock=clock.clock, sleep=clock.sleep, logger=lambda m: None
    )
    crawler = crawl.Crawler(
        POLICY,
        kwargs.pop("topic", small_topic()),
        client,
        out,
        data,
        logger=lambda m: None,
        **kwargs,
    )
    return crawler.run(), out, web, clock


def test_discover_writes_a_manifest_with_every_field(tmp_path, no_network):
    _manifest, out, _web, _clock = run_crawl(tmp_path, site())
    saved = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert saved["finished_at"] and saved["topic"] == "carta-identita"
    entries = {e["url"]: e for e in saved["entries"]}
    cie = entries["https://www.comune.milano.it/servizi/anagrafe/carta-d-identita"]
    for field in (
        "url",
        "final_url",
        "http_status",
        "content_type",
        "sha256",
        "fetched_at",
        "title",
        "score",
        "keyword_hits",
        "links_from",
        "already_saved_as",
        "raw_file",
        "suggested_id",
        "kept",
    ):
        assert field in cie
    assert cie["http_status"] == 200 and cie["kept"] and cie["already_saved_as"] == "cie"
    assert (out / cie["raw_file"]).read_text(encoding="utf-8") == CIE_PAGE
    assert cie["links_from"] == ["seed", "sources.csv:cie"]
    foto = entries["https://www.comune.milano.it/servizi/anagrafe/carta-d-identita/foto"]
    assert foto["kept"] and foto["already_saved_as"] is None and foto["depth"] == 1
    assert foto["links_from"] == ["https://www.comune.milano.it/servizi/anagrafe/carta-d-identita"]
    assert foto["suggested_id"] == "comune-foto"
    assert (out / foto["text_file"]).exists()
    viaggiare = entries["https://www.cartaidentita.interno.gov.it/info-utili/viaggiare/"]
    assert viaggiare["already_saved_as"] == "cie-ministero-viaggiare"
    assert "sitemap:https://www.cartaidentita.interno.gov.it/sitemap.xml" in viaggiare["links_from"]
    ka = entries["https://servizicrm.comune.milano.it/centro-supporto/KA-00999/Nuova-domanda-CIE"]
    assert ka["kept"] and ka["suggested_id"] == "cie-faq-00999"
    assert ka["links_from"] == ["search:centro-supporto:CIE"]
    assert saved["searches"][0]["results"] == 2 and saved["searches"][0]["queued"] == 1
    assert "https://www.cartaidentita.interno.gov.it/attiva/" in entries
    bis = entries["https://www.comune.milano.it/servizi/anagrafe/carta-d-identita-bis"]
    assert bis["duplicate_of"] == "https://www.comune.milano.it/servizi/anagrafe/carta-d-identita"
    assert bis["already_saved_as"] == "cie" and bis["suggested_id"] == "cie"


def test_discover_stays_inside_the_rules(tmp_path, no_network):
    manifest, _out, web, _clock = run_crawl(tmp_path, site())
    entries = {e["url"]: e for e in manifest["entries"]}
    assert not any("example.org" in c or "servizicdm" in c for c in web.calls)
    assert not any(
        "/spec/appuntamenti" in c or "/fr/" in c or c.endswith(".png") for c in web.calls
    )
    assert (
        "https://www.comune.milano.it/servizi/tributi/tari" not in entries
    )  # irrelevant link: not followed
    tributi = entries.get("https://www.comune.milano.it/servizi/tributi")
    assert tributi is None or not tributi["kept"]
    not_fetched = {n["url"]: n["reason"] for n in manifest["not_fetched"]}
    assert "outside the allowlist" in not_fetched["https://www.example.org/carta-identita"]
    assert (
        "blocked pattern"
        in not_fetched["https://servizicrm.comune.milano.it/spec/appuntamenti/anagrafecie"]
    )
    # depth 2 pages are fetched, but their links are not followed
    assert (
        entries["https://www.comune.milano.it/servizi/anagrafe/carta-d-identita/foto/dettagli"][
            "depth"
        ]
        == 2
    )
    assert all(e["depth"] <= 2 for e in manifest["entries"])
    assert len(web.calls) == len(set(web.calls))  # nothing downloaded twice


def test_a_redirect_to_a_page_already_fetched_is_a_duplicate(tmp_path, no_network):
    web = site()
    web.pages["https://www.cartaidentita.interno.gov.it/info-utili/homepage/"] = (
        301,
        {"Location": "https://www.cartaidentita.interno.gov.it/info-utili/viaggiare/"},
        "",
    )
    web.pages["https://www.cartaidentita.interno.gov.it/sitemap.xml"] = (
        200,
        {"Content-Type": "text/xml"},
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        "<url><loc>https://www.cartaidentita.interno.gov.it/info-utili/viaggiare/</loc></url>"
        "<url><loc>https://www.cartaidentita.interno.gov.it/info-utili/homepage/</loc></url></urlset>",
    )
    manifest, *_ = run_crawl(tmp_path, web, use_search=False)
    entries = {e["url"]: e for e in manifest["entries"]}
    home = entries["https://www.cartaidentita.interno.gov.it/info-utili/homepage/"]
    assert home["duplicate_of"] == "https://www.cartaidentita.interno.gov.it/info-utili/viaggiare/"
    assert home["already_saved_as"] == "cie-ministero-viaggiare"
    assert manifest["counts"]["kept_new"] == len(
        [
            e
            for e in manifest["entries"]
            if e["kept"] and not e["already_saved_as"] and not e["duplicate_of"]
        ]
    )


def test_rescore_scores_a_crawl_again_without_network(tmp_path, no_network):
    manifest, out, web, _clock = run_crawl(tmp_path, site())
    calls = len(web.calls)
    before = {e["url"]: e["kept"] for e in manifest["entries"]}
    topic = small_topic(min_score=10_000)
    client = crawl.PoliteClient(POLICY, transport=crawl._no_transport, logger=lambda m: None)
    again = crawl.Crawler(
        POLICY, topic, client, out, tmp_path / "data", logger=lambda m: None
    ).rescore()
    assert len(web.calls) == calls
    assert any(before.values()) and not any(e["kept"] for e in again["entries"])
    assert again["counts"]["http_requests"] == manifest["counts"]["http_requests"]
    assert again["searches"] == manifest["searches"]
    assert {e["url"] for e in again["entries"]} == set(before)
    again = crawl.Crawler(
        POLICY, small_topic(), client, out, tmp_path / "data", logger=lambda m: None
    ).rescore()
    assert {e["url"]: e["kept"] for e in again["entries"]} == before


def test_discover_respects_depth_and_page_cap(tmp_path, no_network):
    manifest, *_ = run_crawl(tmp_path, site(), max_depth=0, use_sitemaps=False, use_search=False)
    assert [e["url"] for e in manifest["entries"]] == [
        "https://www.comune.milano.it/servizi/anagrafe/carta-d-identita"
    ]
    manifest, *_ = run_crawl(tmp_path / "b", site(), max_pages=2)
    assert manifest["counts"]["pages_fetched"] == 2
    assert any(n["reason"] == "page cap reached" for n in manifest["not_fetched"])


def test_discover_refuses_to_write_inside_the_data_folder(tmp_path):
    with pytest.raises(SystemExit, match="outside the data folder"):
        crawl.main(
            [
                "--data-dir",
                str(tmp_path),
                "discover",
                "--topic",
                "carta-identita",
                "--out",
                str(tmp_path / "x"),
            ]
        )


def test_parse_sitemap_index_and_urlset():
    kind, locs = crawl.parse_sitemap(
        b'<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><sitemap><loc>https://a/1.xml</loc>'
        b"</sitemap></sitemapindex>"
    )
    assert (kind, locs) == ("index", ["https://a/1.xml"])
    assert crawl.parse_sitemap(b"not xml")[0] == "invalid"


# --------------------------------------------------------------------------- refresh


def fake_cleaner(raw: bytes, is_pdf: bool, url: str) -> list[tuple[str, str]]:
    text = raw.decode("utf-8")
    return [("main", text), ("--select article", text.upper())]


def test_refresh_reports_unchanged_changed_failed_and_skipped(tmp_path, no_network):
    base = "https://www.comune.milano.it/servizi/anagrafe/"
    body = "# Carta d'identità\n\nPorta la fototessera.\n"
    data = make_data_dir(
        tmp_path,
        [
            {"id": "same", "url": base + "same", "snapshot": "pages/same.md", "kind": "page"},
            {"id": "spaces", "url": base + "spaces", "snapshot": "pages/spaces.md", "kind": "page"},
            {"id": "moved", "url": base + "moved", "snapshot": "pages/moved.md", "kind": "page"},
            {"id": "gone", "url": base + "gone", "snapshot": "pages/gone.md", "kind": "page"},
            {
                "id": "ds549",
                "url": "https://dati.comune.milano.it/dataset/ds549",
                "snapshot": "opendata/x.csv",
                "kind": "opendata",
            },
        ],
        pages={
            sid: saved_page(sid, base + sid, body) for sid in ("same", "spaces", "moved", "gone")
        },
    )
    web = FakeWeb(
        {
            base + "same": (200, HTML, body),
            # the curly apostrophe is part of what is tested
            base + "spaces": (200, HTML, "# Carta d’identità\n\n\nPorta   la fototessera.\n"),  # noqa: RUF001
            base + "moved": (
                200,
                HTML,
                "# Carta d'identità\n\nPorta la fototessera e il passaporto.\n",
            ),
        }
    )
    out = tmp_path / "refresh"
    results = {
        r["id"]: r for r in crawl.refresh(data, POLICY, client_for(web), fake_cleaner, out_dir=out)
    }
    assert results["same"]["status"] == "unchanged" and results["same"]["detail"] == "main"
    assert results["spaces"]["status"] == "unchanged" and "spacing" in results["spaces"]["detail"]
    assert results["moved"]["status"] == "changed" and 0.5 < results["moved"]["similarity"] < 1
    assert "+Porta la fototessera e il passaporto." in (out / "moved.diff").read_text(
        encoding="utf-8"
    )
    assert results["gone"]["status"] == "failed" and "404" in results["gone"]["detail"]
    assert results["ds549"]["status"] == "skipped"
    # the repository copy was only read
    assert crawl.read_front_matter((data / "pages" / "moved.md").read_text())[1] == body


def test_refresh_can_reuse_a_crawl_without_network(tmp_path, no_network):
    url = "https://www.comune.milano.it/servizi/anagrafe/carta-d-identita"
    body = "# Carta d'identità\n"
    data = make_data_dir(
        tmp_path,
        [{"id": "cie", "url": url, "snapshot": "pages/cie.md", "kind": "page"}],
        pages={"cie": saved_page("cie", url, body)},
    )
    crawl_dir = tmp_path / "crawl"
    (crawl_dir / "raw").mkdir(parents=True)
    (crawl_dir / "raw" / "cie.html").write_text(body, encoding="utf-8")
    (crawl_dir / "manifest.json").write_text(
        json.dumps(
            {
                "entries": [
                    {"url": url, "final_url": url, "http_status": 200, "raw_file": "raw/cie.html"}
                ]
            }
        ),
        encoding="utf-8",
    )
    [result] = crawl.refresh(data, POLICY, None, fake_cleaner, crawl_dir=crawl_dir)
    assert result["status"] == "unchanged" and result["from"] == "crawl"


# --------------------------------------------------------------------------- ingest


KA_RAW = (
    "<html><head><title>Centro supporto</title></head><body><nav>menu</nav><main>"
    "<h1 id='faqtitle'>Posso usare la CIE come documento di espatrio?</h1>"
    "<div id='faqcontent'><p>La Carta di Identità Elettronica (CIE) &egrave; valida "
    "per l&#39;espatrio "
    "nei <strong>Paesi UE</strong>.</p><br><p>Altro testo.</p></div>"
    "<div id='faqsentiment'>Ti è stato utile?</div>"
    "<p id='faqlastmodified'>Ultimo aggiornamento: 01/10/2026</p></main></body></html>"
)


def make_crawl(tmp_path) -> pathlib.Path:
    crawl_dir = tmp_path / "crawl"
    (crawl_dir / "raw").mkdir(parents=True)
    (crawl_dir / "raw" / "ka.html").write_text(KA_RAW, encoding="utf-8")
    (crawl_dir / "raw" / "doc.pdf").write_bytes(b"%PDF-1.4 fake")
    ka_url = "https://servizicrm.comune.milano.it/centro-supporto/KA-00999/CIE-espatrio"
    entries = [
        {
            "suggested_id": "cie-faq-00999",
            "url": ka_url,
            "final_url": ka_url,
            "http_status": 200,
            "kept": True,
            "score": 40,
            "raw_file": "raw/ka.html",
            "already_saved_as": None,
            "title": "Centro supporto",
            "h1": "Posso usare la CIE come documento di espatrio?",
            "publisher": "Comune di Milano",
            "kind": "faq",
            "links_from": ["search:centro-supporto:CIE"],
        },
        {
            "suggested_id": "comune-doc-modulo",
            "url": "https://www.comune.milano.it/documents/d/guest/modulo",
            "final_url": "https://www.comune.milano.it/documents/d/guest/modulo",
            "http_status": 200,
            "kept": True,
            "score": 20,
            "raw_file": "raw/doc.pdf",
            "already_saved_as": None,
            "title": "modulo",
            "h1": "",
            "publisher": "Comune di Milano",
            "kind": "pdf",
            "links_from": ["x"],
        },
        {
            "suggested_id": "cie",
            "url": "https://www.comune.milano.it/servizi/anagrafe/carta-d-identita",
            "final_url": "https://www.comune.milano.it/servizi/anagrafe/carta-d-identita",
            "http_status": 200,
            "kept": True,
            "score": 200,
            "raw_file": "raw/ka.html",
            "already_saved_as": "cie",
        },
    ]
    (crawl_dir / "manifest.json").write_text(
        json.dumps({"topic": "carta-identita", "entries": entries}), encoding="utf-8"
    )
    return crawl_dir


def test_prewrap_keeps_only_the_selected_elements_without_beautifulsoup(monkeypatch):
    monkeypatch.setitem(sys.modules, "bs4", None)  # the stdlib fallback, as in the Streamlit venv
    wrapped = crawl.prewrap_selectors(KA_RAW, ["#faqtitle", "#faqcontent", "#faqlastmodified"])
    assert wrapped.startswith("<!doctype html><html><body><main>")
    assert (
        "Posso usare la CIE" in wrapped
        and "&egrave;" in wrapped
        and "<strong>Paesi UE</strong>" in wrapped
    )
    assert "Ultimo aggiornamento" in wrapped
    assert "menu" not in wrapped and "Ti è stato utile" not in wrapped


def test_ingest_with_a_fake_runner(tmp_path, no_network):
    data = make_data_dir(
        tmp_path, [{"id": "cie", "url": "https://www.comune.milano.it/x", "kind": "page"}]
    )
    crawl_dir = make_crawl(tmp_path)
    calls: list[list[str]] = []

    def runner(cmd, cwd):
        calls.append(cmd)
        if "clean_html.py" in " ".join(cmd):
            pathlib.Path(cmd[3]).write_text("<main>ok</main>", encoding="utf-8")
        return subprocess.CompletedProcess(cmd, 0, "ok", "")

    code = crawl.ingest(
        crawl_dir,
        data,
        POLICY,
        ids=crawl.parse_ids("cie-faq-00999,comune-doc-modulo=cie-modulo,cie"),
        python="py",
        onevisit="ov",
        runner=runner,
    )
    assert code == 0
    clean_ka, ingest_ka, clean_pdf, ingest_pdf = calls
    assert clean_ka[2].endswith(
        "cie-faq-00999.pre.html"
    )  # support-centre page: question, answer, date only
    pre = pathlib.Path(clean_ka[2]).read_text(encoding="utf-8")
    assert "faqtitle" in pre and "faqsentiment" not in pre
    assert ingest_ka == [
        "ov",
        "ingest",
        "cie-faq-00999",
        "--html",
        clean_ka[3],
        "--url",
        "https://servizicrm.comune.milano.it/centro-supporto/KA-00999/CIE-espatrio",
        "--data-dir",
        str(data),
    ]
    assert clean_pdf[-1] == "--pdf" and ingest_pdf[2] == "cie-modulo"
    rows = {r["id"]: r for r in crawl.read_sources(data)}
    assert rows["cie-faq-00999"]["title"] == "Posso usare la CIE come documento di espatrio?"
    # not searchable until a person has read it (onevisit ingest would have said "ok")
    assert rows["cie-faq-00999"]["kind"] == "faq"
    assert rows["cie-faq-00999"]["status"] == crawl.REVIEW_STATUS
    assert rows["cie-modulo"]["kind"] == "pdf"
    assert (data / "sources.csv").read_text(encoding="utf-8").endswith("\n")
    assert "\r\n" not in (data / "sources.csv").read_text(encoding="utf-8")


def test_ingest_skips_saved_unknown_and_taken_ids_and_dry_run_writes_nothing(tmp_path, capsys):
    data = make_data_dir(
        tmp_path, [{"id": "cie-faq-00999", "url": "https://www.comune.milano.it/y", "kind": "page"}]
    )
    crawl_dir = make_crawl(tmp_path)
    before = (data / "sources.csv").read_text(encoding="utf-8")

    def runner(cmd, cwd):  # pragma: no cover - must not run
        raise AssertionError(cmd)

    assert (
        crawl.ingest(
            crawl_dir, data, POLICY, ids=crawl.parse_ids("cie,nope,cie-faq-00999"), runner=runner
        )
        == 1
    )
    out = capsys.readouterr().out
    assert (
        "already saved as cie" in out
        and "nope: not in the manifest" in out
        and "already in sources.csv" in out
    )
    with pytest.raises(TypeError):  # no --min-score: only the ids a person picked
        crawl.ingest(crawl_dir, data, POLICY, min_score=30, dry_run=True, runner=runner)  # type: ignore[call-arg]  # removed on purpose
    assert (
        crawl.ingest(
            crawl_dir,
            data,
            POLICY,
            ids=crawl.parse_ids("cie-faq-00999=cie-faq-new"),
            dry_run=True,
            runner=runner,
        )
        == 0
    )
    assert "plan    cie-faq-new" in capsys.readouterr().out
    assert (data / "sources.csv").read_text(encoding="utf-8") == before


def _never(cmd, cwd):  # pragma: no cover - must not run
    raise AssertionError(cmd)


def test_ingest_never_overwrites_a_saved_page_without_force(tmp_path, capsys):
    data = make_data_dir(
        tmp_path, [], pages={"cie-faq-00999": "---\nsource_id: x\n---\n\nTesto.\n"}
    )
    crawl_dir = make_crawl(tmp_path)
    before = (data / "pages" / "cie-faq-00999.md").read_text(encoding="utf-8")
    ids = crawl.parse_ids("cie-faq-00999")
    assert crawl.ingest(crawl_dir, data, POLICY, ids=ids, runner=_never) == 1
    assert "pass --force to overwrite it" in capsys.readouterr().out
    assert (data / "pages" / "cie-faq-00999.md").read_text(encoding="utf-8") == before
    assert crawl.read_sources(data) == []
    calls = []

    def runner(cmd, cwd):
        calls.append(cmd)
        if "clean_html.py" in " ".join(cmd):
            pathlib.Path(cmd[3]).write_text("<main>ok</main>", encoding="utf-8")
        return subprocess.CompletedProcess(cmd, 0, "ok", "")

    assert crawl.ingest(crawl_dir, data, POLICY, ids=ids, runner=runner, force=True) == 0
    assert len(calls) == 2


def test_ingest_skips_a_url_already_saved_under_another_id(tmp_path, capsys):
    ka_url = "https://servizicrm.comune.milano.it/centro-supporto/KA-00999/Altro-titolo"
    data = make_data_dir(tmp_path, [{"id": "cie-espatrio", "url": ka_url, "kind": "faq"}])
    crawl_dir = make_crawl(tmp_path)  # the manifest still says "not saved"
    ids = crawl.parse_ids("cie-faq-00999=cie-faq-nuova")
    assert crawl.ingest(crawl_dir, data, POLICY, ids=ids, runner=_never) == 1
    assert "already saved as cie-espatrio (use refresh)" in capsys.readouterr().out
    assert [r["id"] for r in crawl.read_sources(data)] == ["cie-espatrio"]


def test_ingest_applies_the_current_policy(tmp_path, capsys):
    data = make_data_dir(tmp_path, [])
    crawl_dir = make_crawl(tmp_path)
    policy = crawl.Policy.from_dict(
        dict(
            json.loads(crawl.DEFAULT_SEEDS.read_text(encoding="utf-8"))["policy"],
            blocked_url_patterns=["centro-supporto/KA-00999"],
        )
    )
    ids = crawl.parse_ids("cie-faq-00999")
    assert crawl.ingest(crawl_dir, data, policy, ids=ids, runner=_never) == 1
    assert "the crawl policy now refuses it (blocked pattern" in capsys.readouterr().out


def test_ingest_takes_only_picked_ids(tmp_path):
    data = make_data_dir(tmp_path, [])
    crawl_dir = make_crawl(tmp_path)
    for argv in (
        ["ingest", "--from-crawl", str(crawl_dir), "--min-score", "10"],
        ["ingest", "--from-crawl", str(crawl_dir)],
    ):
        with pytest.raises(SystemExit):
            crawl.main(["--data-dir", str(data), *argv])
    assert crawl.read_sources(data) == []


def test_approve_makes_only_read_pages_searchable(tmp_path, capsys):
    rows = [
        {"id": "nuova", "url": "https://x.it/a", "snapshot": "pages/nuova.md", "status": "review"},
        {"id": "senza", "url": "https://x.it/b", "snapshot": "pages/senza.md", "status": "review"},
        {"id": "vecchia", "url": "https://x.it/c", "snapshot": "pages/vecchia.md", "status": "ok"},
    ]
    data = make_data_dir(tmp_path, rows, pages={"nuova": "x", "vecchia": "y"})
    lines = (data / "sources.csv").read_text(encoding="utf-8").splitlines()
    assert crawl.approve(data, ["nuova", "senza", "vecchia", "nessuna"]) == 1
    out = capsys.readouterr().out
    assert "ok      nuova" in out and "no saved page" in out and "not review" in out
    status = {r["id"]: r["status"] for r in crawl.read_sources(data)}
    assert status == {"nuova": "ok", "senza": "review", "vecchia": "ok"}
    after = (data / "sources.csv").read_text(encoding="utf-8").splitlines()
    assert [a for a, b in zip(lines, after, strict=True) if a != b] == [lines[1]]


@pytest.mark.skipif(
    not (KIT_PYTHON.exists() and KIT_ONEVISIT.exists()),
    reason="needs the kit environment (.venv with BeautifulSoup and the onevisit command)",
)
def test_ingest_and_refresh_for_real_on_a_copy_of_the_data(tmp_path):
    """clean_html.py + onevisit ingest on a copy of data/, then refresh finds it unchanged."""
    data = tmp_path / "data"
    (data / "pages").mkdir(parents=True)
    shutil.copy(ROOT / "data" / "sources.csv", data / "sources.csv")
    shutil.copytree(ROOT / "data" / "services", data / "services")
    real_sources = (ROOT / "data" / "sources.csv").read_text(encoding="utf-8")
    crawl_dir = make_crawl(tmp_path)
    code = crawl.ingest(
        crawl_dir,
        data,
        POLICY,
        ids=crawl.parse_ids("cie-faq-00999=cie-faq-test-crawl"),
        python=str(KIT_PYTHON),
        onevisit=str(KIT_ONEVISIT),
    )
    assert code == 0
    page = (data / "pages" / "cie-faq-test-crawl.md").read_text(encoding="utf-8")
    meta, body = crawl.read_front_matter(page)
    assert meta["source_id"] == "cie-faq-test-crawl" and meta["content_hash"] == crawl.content_hash(
        body
    )
    assert "valida per l'espatrio nei Paesi UE" in body and "Ti è stato utile" not in body
    assert "Ultimo aggiornamento: 01/10/2026" in body
    row = {r["id"]: r for r in crawl.read_sources(data)}["cie-faq-test-crawl"]
    assert row["snapshot"] == "pages/cie-faq-test-crawl.md" and row["status"] == "review"
    assert crawl.approve(data, ["cie-faq-test-crawl"]) == 0
    row = {r["id"]: r for r in crawl.read_sources(data)}["cie-faq-test-crawl"]
    assert row["status"] == "ok"
    assert (ROOT / "data" / "sources.csv").read_text(encoding="utf-8") == real_sources

    def run_refresh() -> str:
        # fixed arguments: the repository's own crawl.py on a temporary copy of data/
        return subprocess.run(  # noqa: S603
            [
                str(KIT_PYTHON),
                str(crawl.TOOLS_DIR / "crawl.py"),
                "--data-dir",
                str(data),
                "refresh",
                "--ids",
                "cie-faq-test-crawl",
                "--from-crawl",
                str(crawl_dir),
                "--offline",
                "--out",
                str(tmp_path / "r"),
            ],
            capture_output=True,
            text=True,
            check=True,
        ).stdout

    assert run_refresh().startswith("unchanged")
    raw = crawl_dir / "raw" / "ka.html"
    raw.write_text(
        raw.read_text(encoding="utf-8").replace("Altro testo.", "Testo nuovo."), encoding="utf-8"
    )
    assert run_refresh().startswith("changed")
    assert "+Testo nuovo." in (tmp_path / "r" / "cie-faq-test-crawl.diff").read_text(
        encoding="utf-8"
    )
