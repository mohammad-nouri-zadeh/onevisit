"""Comando ``onevisit ingest``: salva una pagina ufficiale come Markdown citabile (storie A1, C4).

Scarica l'URL con httpx (rispettando robots.txt, al massimo una richiesta al secondo) oppure
legge una pagina salvata dal browser, la converte in Markdown con markdownify (senza script,
stili, menu, intestazioni e piè di pagina) e scrive ``data/pages/<source_id>.md`` con un
front matter YAML: url, ente, servizio, verified_at, content_hash. Aggiorna solo la riga
della fonte in ``data/sources.csv``. Se l'hash del contenuto è cambiato rispetto al file
precedente, elenca i requisiti che citano la fonte: una persona deve riverificarli.
"""

import csv
import io
import json
import re
import time
from collections.abc import Callable
from datetime import date
from pathlib import Path
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

import httpx
from bs4 import BeautifulSoup
from markdownify import markdownify

from onevisit_knowledge import content_hash, render_page, split_front_matter

USER_AGENT = "OneVisit/0.1 (hackathon Comune di Milano)"
# Intervallo minimo tra due richieste allo stesso sito, in secondi (1 richiesta/secondo).
MIN_REQUEST_INTERVAL_S = 1.0
# Timeout di ogni richiesta HTTP, in secondi.
REQUEST_TIMEOUT_S = 30.0
# Elementi eliminati con tutto il loro contenuto prima della conversione.
DROPPED_TAGS = ("script", "style", "noscript", "nav", "header", "footer", "svg", "form")
_BLANK_LINES = re.compile(r"\n{3,}")


class IngestError(Exception):
    """La pagina non si può scaricare o salvare; il messaggio è adatto al terminale."""


class _Throttle:
    """Garantisce almeno ``interval`` secondi tra due richieste."""

    def __init__(
        self,
        interval: float,
        sleep: Callable[[float], None],
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._interval = interval
        self._sleep = sleep
        self._clock = clock
        self._last: float | None = None

    def wait(self) -> None:
        now = self._clock()
        if self._last is not None and now - self._last < self._interval:
            self._sleep(self._interval - (now - self._last))
        self._last = self._clock()


def html_to_markdown(raw_html: str) -> str:
    """Converte l'HTML in Markdown pulito, eliminando script, stili e navigazione."""
    soup = BeautifulSoup(raw_html, "html.parser")
    for tag in soup.find_all(DROPPED_TAGS):
        tag.decompose()
    root = soup.find("main") or soup.body or soup
    text = markdownify(str(root), heading_style="ATX", bullets="-")
    lines = [line.rstrip() for line in text.splitlines()]
    return _BLANK_LINES.sub("\n\n", "\n".join(lines)).strip() + "\n"


def fetch(
    url: str,
    *,
    transport: httpx.BaseTransport | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> str:
    """Scarica una pagina rispettando robots.txt e il limite di una richiesta al secondo."""
    throttle = _Throttle(MIN_REQUEST_INTERVAL_S, sleep)
    headers = {"User-Agent": USER_AGENT, "Accept-Language": "it-IT,it;q=0.9"}
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https"):
        raise IngestError(f"URL non valido: {url}")
    robots_url = urljoin(f"{parts.scheme}://{parts.netloc}", "/robots.txt")
    with httpx.Client(
        transport=transport, headers=headers, timeout=REQUEST_TIMEOUT_S, follow_redirects=True
    ) as client:
        try:
            throttle.wait()
            robots = client.get(robots_url)
            parser = RobotFileParser()
            if robots.status_code == httpx.codes.OK:
                parser.parse(robots.text.splitlines())
                allowed = parser.can_fetch(USER_AGENT, url)
            else:
                # robots.txt assente (4xx): tutto permesso; errore del server (5xx): nulla.
                allowed = robots.status_code < httpx.codes.INTERNAL_SERVER_ERROR
            if not allowed:
                raise IngestError(
                    "robots.txt non permette di scaricare questa pagina: salvala dal browser "
                    "e usa --html"
                )
            throttle.wait()
            response = client.get(url)
        except httpx.HTTPError as exc:
            raise IngestError(
                f"download non riuscito ({exc.__class__.__name__}): salva la pagina dal "
                "browser e usa --html"
            ) from exc
    if response.status_code != httpx.codes.OK:
        raise IngestError(
            f"download non riuscito (HTTP {response.status_code}): salva la pagina dal "
            "browser e usa --html"
        )
    return response.text


def _services_citing(data_dir: Path, source_id: str) -> tuple[list[str], list[str]]:
    """Servizi che citano la fonte e requisiti/passaggi collegati (``servizio/id``)."""
    services: list[str] = []
    linked: list[str] = []
    for path in sorted((data_dir / "services").glob("*.json")):
        try:
            svc = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        sid = str(svc.get("id", path.stem))
        cites = source_id in (svc.get("source_ids") or [])
        for req in svc.get("requirements", []):
            if req.get("source_id") == source_id:
                cites = True
                linked.append(f"{sid}/{req.get('id')} ({req.get('status', 'todo')})")
        for step in svc.get("steps", []):
            if step.get("source_id") == source_id:
                cites = True
                linked.append(f"{sid}/step {step.get('order')} ({step.get('status', 'todo')})")
        if cites:
            services.append(sid)
    return services, linked


def _update_source_row(sources_path: Path, source_id: str, updates: dict[str, str]) -> None:
    """Riscrive solo la riga della fonte; tutte le altre righe restano identiche al byte."""
    text = sources_path.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)
    reader = csv.reader(io.StringIO(text))
    header = next(reader)
    start = reader.line_num
    for row in reader:
        end = reader.line_num
        if row and row[0] == source_id:
            record = dict(zip(header, row, strict=False))
            record.update(updates)
            newline = "\r\n" if lines[end - 1].endswith("\r\n") else "\n"
            buffer = io.StringIO()
            csv.writer(buffer, lineterminator=newline).writerow(
                [record.get(col, "") for col in header]
            )
            lines[start:end] = [buffer.getvalue()]
            sources_path.write_text("".join(lines), encoding="utf-8")
            return
        start = end
    raise IngestError(f"nessuna fonte '{source_id}' in sources.csv: aggiungi prima la riga")


def _read_row(sources_path: Path, source_id: str) -> dict[str, str] | None:
    with sources_path.open(encoding="utf-8", newline="") as handle:
        return next((r for r in csv.DictReader(handle) if r["id"] == source_id), None)


def run(
    *,
    source_id: str,
    url: str,
    html_path: Path | None,
    data_dir: Path,
    transport: httpx.BaseTransport | None = None,
    today: date | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> int:
    """Salva la pagina e aggiorna ``sources.csv``; restituisce il codice di uscita."""
    today = today or date.today()
    sources_path = data_dir / "sources.csv"
    row = _read_row(sources_path, source_id)
    if row is None:
        print(f"Nessuna fonte '{source_id}' in sources.csv: aggiungi prima la riga.")
        return 1
    page_url = url or row.get("url", "")
    try:
        if html_path is not None:
            raw = html_path.read_text(encoding="utf-8", errors="replace")
        elif page_url:
            raw = fetch(page_url, transport=transport, sleep=sleep)
        else:
            print("La fonte non ha ancora un URL: passa --url https://... oppure --html.")
            return 1
    except (IngestError, OSError) as exc:
        print(f"Errore: {exc}")
        return 1

    body = html_to_markdown(raw)
    new_hash = content_hash(body)
    page_path = data_dir / "pages" / f"{source_id}.md"
    old_hash: str | None = None
    if page_path.exists():
        meta, old_body = split_front_matter(page_path.read_text(encoding="utf-8"))
        old_hash = str(meta.get("content_hash") or content_hash(old_body))

    services, linked = _services_citing(data_dir, source_id)
    meta_out = {
        "source_id": source_id,
        "url": page_url,
        "ente": row.get("publisher", ""),
        "servizio": services,
        "verified_at": today.isoformat(),
        "content_hash": new_hash,
    }
    page_path.parent.mkdir(parents=True, exist_ok=True)
    page_path.write_text(render_page(meta_out, body), encoding="utf-8")

    updates = {
        "snapshot": f"pages/{source_id}.md",
        "retrieved_at": today.isoformat(),
        "status": "ok",
    }
    if url:
        updates["url"] = url
    try:
        _update_source_row(sources_path, source_id, updates)
    except IngestError as exc:
        print(f"Errore: {exc}")
        return 1

    print(f"Salvata {page_path} ({len(body)} caratteri, {new_hash[:19]}...).")
    if old_hash is None:
        print("Pagina nuova: copia le citazioni in data/services/ e lancia onevisit catalog-check.")
    elif old_hash != new_hash:
        print("ATTENZIONE: il contenuto della pagina è cambiato dall'ultima versione salvata.")
        if linked:
            print("Da riverificare (le citazioni potrebbero non essere più valide):")
            for item in linked:
                print(f"  - {item}")
        else:
            print("Nessun requisito cita ancora questa fonte.")
    else:
        print("Contenuto invariato rispetto alla versione salvata.")
    return 0
