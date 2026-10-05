"""Caricamento del catalogo dai file del livello dati, senza copiarli (storie A2, C4).

Riproduce la semantica di ``onevisit/kb.py``: al cittadino arrivano solo i fatti con
``status == "verified"`` (salvo ``include_drafts``, solo sviluppo); un requisito il cui
``when`` dipende da una domanda senza risposta non compare. ``still_to_ask`` elenca,
nell'ordine del catalogo, solo le domande da cui dipende qualcosa ancora possibile (un
requisito che nessuna risposta ha escluso, un servizio indicato da un percorso attivo); un
percorso che chiude il caso (``option_routes`` con ``route: "stop"``) ferma le altre domande.
Le correzioni approvate nel pannello (B11) si sovrappongono al catalogo.
"""

import csv
import json
import math
from collections.abc import Mapping, Sequence
from datetime import date, datetime
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from onevisit_knowledge.errors import CatalogError
from onevisit_knowledge.models import (
    APPROVED_CORRECTION_SOURCE_ID,
    ApprovedCorrection,
    Checklist,
    ChecklistItem,
    DecidingQuestion,
    Ente,
    Office,
    Requirement,
    Service,
    ServiceSummary,
    Source,
    Step,
)

VERIFIED = "verified"
# Percorsi (``option_routes``) che chiudono il caso: la persona non può fare la pratica qui.
ENDING_ROUTES = frozenset({"stop"})
# Diametro medio della Terra in km (2 x 6371), come in onevisit/kb.py.
EARTH_DIAMETER_KM = 12742.0
# Cifre decimali delle distanze restituite.
DISTANCE_DECIMALS = 2


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distanza in km tra due punti (formula dell'emisenoverso)."""
    rad = math.pi / 180
    a = (
        math.sin((lat2 - lat1) * rad / 2) ** 2
        + math.cos(lat1 * rad) * math.cos(lat2 * rad) * math.sin((lon2 - lon1) * rad / 2) ** 2
    )
    return EARTH_DIAMETER_KM * math.asin(math.sqrt(a))


def _parse_date(value: Any) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        return None


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise CatalogError(f"file mancante: {path.name}") from exc
    except json.JSONDecodeError as exc:
        raise CatalogError(f"JSON non valido: {path.name} ({exc.msg})") from exc


def read_sources(data_dir: Path) -> dict[str, Source]:
    """Legge ``sources.csv``; date non valide diventano ``None``."""
    path = data_dir / "sources.csv"
    try:
        with path.open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
    except FileNotFoundError as exc:
        raise CatalogError("file mancante: sources.csv") from exc
    sources: dict[str, Source] = {}
    for row in rows:
        data = {k: (v or "") for k, v in row.items() if k is not None}
        data["retrieved_at"] = _parse_date(data.get("retrieved_at"))
        sources[data["id"]] = Source.model_validate(data)
    return sources


def _office_from_raw(raw: Mapping[str, Any]) -> Office:
    nil = raw.get("nil") or {}
    data = dict(raw)
    data["nil_id"] = nil.get("id")
    data["nil_name"] = nil.get("name")
    data["data_issues"] = list(raw.get("data_issues") or [])
    return Office.model_validate(data)


class _RawService:
    """Servizio così come scritto nel file JSON, già validato nei suoi pezzi."""

    def __init__(self, raw: Mapping[str, Any], file_name: str) -> None:
        try:
            title = raw.get("title") or {}
            self.id: str = str(raw["id"])
            self.title_it: str = str(title.get("it", self.id))
            self.title_en: str = str(title.get("en", self.title_it))
            self.ente: str | None = raw.get("ente")
            self.source_ids: list[str] = list(raw.get("source_ids") or [])
            self.questions = [
                DecidingQuestion.model_validate(q) for q in raw.get("deciding_questions", [])
            ]
            self.option_routes: dict[str, dict[str, dict[str, Any]]] = {
                str(q["id"]): _routes_of(q) for q in raw.get("deciding_questions", [])
            }
            self.requirements = [
                Requirement.model_validate(_clean_dates(r)) for r in raw.get("requirements", [])
            ]
            self.steps = [Step.model_validate(_clean_dates(s)) for s in raw.get("steps", [])]
            self.unknowns_it: list[str] = list(raw.get("unknowns_it") or [])
            self.official_url: str = str(raw.get("official_url") or "")
        except (KeyError, TypeError, ValidationError) as exc:
            raise CatalogError(f"servizio non valido: {file_name}") from exc


def _routes_of(question: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    """I percorsi di una domanda (``option_routes``: opzione -> percorso), letti così come sono."""
    routes = question.get("option_routes") or {}
    if not isinstance(routes, Mapping) or not all(isinstance(r, Mapping) for r in routes.values()):
        raise TypeError("option_routes non valido")
    return {str(option): dict(route) for option, route in routes.items()}


def _possible(when: Mapping[str, Sequence[str]], answers: Mapping[str, str]) -> bool:
    """Vero se nessuna risposta data finora esclude la condizione (le domande aperte no)."""
    return all(answers[q] in allowed for q, allowed in when.items() if q in answers)


def _stop_applies(raw: _RawService, question: str, answer: str, answers: Mapping[str, str]) -> bool:
    """Un percorso "stop" chiude il caso solo finché qualcosa che ferma è ancora possibile: un
    requisito che nomina la risposta che chiude e che nessuna risposta ha escluso (stessa regola di
    ``onevisit/kb.py``). Residente in un'altra regione ma con PIN/PUK smarriti (si chiedono a
    qualsiasi sportello): le voci dello stop non valgono e il caso prosegue. Uno stop che nessun
    requisito nomina vale sempre."""
    naming = [r.when for r in raw.requirements if answer in (r.when.get(question) or [])]
    return not naming or any(_possible(when, answers) for when in naming)


def _active_routes(raw: _RawService, answers: Mapping[str, str]) -> list[dict[str, Any]]:
    """I percorsi scelti dalle risposte date finora, nell'ordine delle domande (uno "stop" solo
    finché qualcosa che ferma è ancora possibile, vedi ``_stop_applies``)."""
    out: list[dict[str, Any]] = []
    for question in raw.questions:
        answer = answers.get(question.id)
        route = raw.option_routes.get(question.id, {}).get(answer) if answer is not None else None
        if route is None:
            continue
        if route.get("route") in ENDING_ROUTES and not _stop_applies(
            raw, question.id, str(answer), answers
        ):
            continue
        out.append({"question": question.id, "answer": answer, **route})
    return out


def _still_to_ask(
    raw: _RawService,
    answers: Mapping[str, str],
    whens: Sequence[Mapping[str, Sequence[str]]],
) -> list[str]:
    """Domande ancora utili, nell'ordine del catalogo (stessa regola di ``onevisit/kb.py``).

    Una domanda entra solo se ne dipende qualcosa ancora possibile: una condizione ``when``
    che nessuna risposta ha escluso, o il ``when`` di un servizio indicato da un percorso
    attivo. Un percorso che chiude il caso ferma le altre domande: restano solo quelle da cui
    dipendono le sue voci (i requisiti che nominano la risposta che chiude, i suoi servizi).
    """
    active = _active_routes(raw, answers)
    stops = [r for r in active if r.get("route") in ENDING_ROUTES]
    considered: list[Mapping[str, Sequence[str]]] = list(whens)
    if stops:
        stopping = {str(r["question"]) for r in stops}
        considered = [w for w in considered if stopping & set(w)]
        active = stops
    for route in active:
        for service in route.get("services") or []:
            considered.append(service.get("when") or {})
    needed: set[str] = set()
    for when in considered:
        if _possible(when, answers):
            needed.update(q for q in when if q not in answers)
    order = [q.id for q in raw.questions]
    return [q for q in order if q in needed] + sorted(needed - set(order))


def _clean_dates(raw: Mapping[str, Any]) -> dict[str, Any]:
    data = dict(raw)
    data["verified_at"] = _parse_date(data.get("verified_at"))
    data["when"] = data.get("when") or {}
    if not data.get("quote"):
        data["quote"] = None
    return data


class Catalog:
    """Catalogo in memoria: servizi, fonti, sedi, enti, tabelle di contesto."""

    def __init__(
        self,
        *,
        services: Sequence[_RawService],
        sources: Mapping[str, Source],
        offices: Sequence[Office],
        enti: Sequence[Ente],
        context: Mapping[str, list[dict[str, str]]],
        include_drafts: bool,
        overlays: Sequence[ApprovedCorrection],
    ) -> None:
        self._services = {s.id: s for s in services}
        self._sources = dict(sources)
        self._offices = list(offices)
        self._enti = list(enti)
        self._context = {k: list(v) for k, v in context.items()}
        self._include_drafts = include_drafts
        self._overlays = list(overlays)
        if self._overlays:
            latest = max(_parse_date(o.approved_at) or date.min for o in self._overlays)
            self._sources[APPROVED_CORRECTION_SOURCE_ID] = Source(
                id=APPROVED_CORRECTION_SOURCE_ID,
                title="Correzione approvata dal Comune nel pannello OneVisit",
                publisher="Comune di Milano",
                kind="approved_correction",
                retrieved_at=latest,
                status="ok",
            )

    # ------------------------------------------------------------------ servizi
    def _usable(self, status: str) -> bool:
        return status == VERIFIED or self._include_drafts

    def services(self) -> list[ServiceSummary]:
        """Servizi coperti, con quanti requisiti sono verificati."""
        return [
            ServiceSummary(
                id=s.id,
                title_it=s.title_it,
                title_en=s.title_en,
                verified_requirements=sum(r.status == VERIFIED for r in s.requirements),
                total_requirements=len(s.requirements),
            )
            for s in self._services.values()
        ]

    def service(self, service_id: str) -> Service | None:
        """Domande decisive e passaggi (solo verificati, salvo ``include_drafts``)."""
        raw = self._services.get(service_id)
        if raw is None:
            return None
        return Service(
            id=raw.id,
            title_it=raw.title_it,
            title_en=raw.title_en,
            ente=raw.ente,
            source_ids=list(raw.source_ids),
            deciding_questions=list(raw.questions),
            steps=sorted((s for s in raw.steps if self._usable(s.status)), key=lambda s: s.order),
            unknowns_it=list(raw.unknowns_it),
        )

    def checklist(self, service_id: str, answers: Mapping[str, str]) -> Checklist:
        """Requisiti che valgono per questo caso, ciascuno con la sua fonte.

        Solleva ``CatalogError`` se il servizio non esiste.
        """
        raw = self._services.get(service_id)
        if raw is None:
            raise CatalogError(f"servizio sconosciuto: {service_id}")
        overlays = [o for o in self._overlays if o.service_id == service_id]
        replaced = {o.requirement_id for o in overlays if o.requirement_id}
        items: list[ChecklistItem] = []
        not_verified: list[str] = []
        whens: list[Mapping[str, Sequence[str]]] = []

        def applies(when: Mapping[str, Sequence[str]]) -> bool:
            whens.append(when)
            if any(q not in answers for q in when):
                return False
            return all(answers[q] in allowed for q, allowed in when.items())

        for req in raw.requirements:
            if req.id in replaced or not applies(req.when):
                continue
            if not self._usable(req.status):
                not_verified.append(req.id)
                continue
            items.append(
                ChecklistItem(
                    id=req.id,
                    text_it=req.text_it,
                    text_en=req.text_en,
                    source_id=req.source_id,
                    quote=req.quote,
                    verified_at=req.verified_at,
                    lead_time_days=req.lead_time_days,
                    origin="source",
                )
            )
        # Una correzione senza condizioni eredita il ``when`` del requisito che sostituisce:
        # altrimenti un requisito di una sola variante comparirebbe per tutti i casi.
        replaced_when = {r.id: r.when for r in raw.requirements if r.id in replaced}
        for overlay in overlays:
            when = overlay.when or replaced_when.get(overlay.requirement_id or "", {})
            if not applies(when):
                continue
            items.append(
                ChecklistItem(
                    id=overlay.requirement_id or overlay.id,
                    text_it=overlay.text_it,
                    text_en=overlay.text_en,
                    source_id=APPROVED_CORRECTION_SOURCE_ID,
                    verified_at=_parse_date(overlay.approved_at),
                    origin="approved_correction",
                )
            )
        cited = sorted({i.source_id for i in items})
        return Checklist(
            service_id=service_id,
            items=items,
            still_to_ask=_still_to_ask(raw, answers, whens),
            not_yet_verified=not_verified,
            sources=[self._sources[s] for s in cited if s in self._sources],
        )

    def _official_page(self, raw: _RawService | None) -> dict[str, str] | None:
        """La pagina ufficiale di un servizio con la fonte salvata che ha quell'indirizzo, come
        ``kb.service_links``; None se nessuna fonte salvata la riporta."""
        if raw is None or not raw.official_url:
            return None
        source = next((s for s in self._sources.values() if s.url == raw.official_url), None)
        return {"url": raw.official_url, "source_id": source.id} if source else None

    def routes(self, service_id: str, answers: Mapping[str, str]) -> list[dict[str, Any]]:
        """Dove portano le risposte date finora (``option_routes`` delle domande decisive).

        Ogni percorso: ``question``, ``answer``, ``route`` ("stop": la pratica non si fa qui;
        "home": servizio a domicilio; "desk", "walk-in", "info"), ``ends_case``, i ``links``
        con la loro ``source_id`` e i ``services`` da fare prima (solo quelli la cui
        condizione ha già risposta e vale), ognuno con ``official_url`` (url e ``source_id``)
        quando una fonte salvata lo riporta. Solleva ``CatalogError`` se il servizio non esiste.
        """
        raw = self._services.get(service_id)
        if raw is None:
            raise CatalogError(f"servizio sconosciuto: {service_id}")
        out: list[dict[str, Any]] = []
        for route in _active_routes(raw, answers):
            item: dict[str, Any] = {
                "question": route["question"],
                "answer": route["answer"],
                "route": route.get("route"),
                "ends_case": route.get("route") in ENDING_ROUTES,
            }
            links = [
                dict(link)
                for link in route.get("links") or []
                if link.get("url") and link.get("source_id")
            ]
            if links:
                item["links"] = links
            services: list[dict[str, Any]] = []
            for service in route.get("services") or []:
                when = service.get("when") or {}
                if not all(answers.get(q) in allowed for q, allowed in when.items()):
                    continue
                other = self._services.get(str(service.get("id")))
                entry: dict[str, Any] = {
                    "id": str(service.get("id")),
                    "title_it": other.title_it if other else None,
                    "title_en": other.title_en if other else None,
                }
                page = self._official_page(other)
                if page is not None:
                    entry["official_url"] = page
                services.append(entry)
            if services:
                item["services"] = services
            out.append(item)
        return out

    def requirements_citing(self, source_id: str) -> list[tuple[str, str]]:
        """Coppie ``(service_id, requirement_id)`` dei requisiti che citano questa fonte."""
        return [
            (s.id, r.id)
            for s in self._services.values()
            for r in s.requirements
            if r.source_id == source_id
        ]

    # ------------------------------------------------------------------- fonti
    def source(self, source_id: str) -> Source | None:
        """Titolo, URL, ente e data di recupero di una fonte."""
        return self._sources.get(source_id)

    def source_ids(self) -> frozenset[str]:
        """Id di fonte citabili; comprende ``correzione-approvata`` se ci sono overlay."""
        return frozenset(self._sources)

    def is_stale(self, source_id: str, *, today: date, max_days: int) -> bool:
        """Vero se la fonte non è stata recuperata negli ultimi ``max_days`` giorni.

        Scelte: le correzioni approvate non scadono mai (sono decisioni recenti del
        Comune, non pagine copiate); una fonte sconosciuta o senza ``retrieved_at`` è
        considerata scaduta, perché non possiamo dimostrare che sia aggiornata.
        """
        if source_id == APPROVED_CORRECTION_SOURCE_ID and self._overlays:
            return False
        src = self._sources.get(source_id)
        if src is None or src.retrieved_at is None:
            return True
        return (today - src.retrieved_at).days > max_days

    # ------------------------------------------------------------- sedi e enti
    def offices(
        self,
        *,
        area: str | None = None,
        municipio: int | None = None,
        lat: float | None = None,
        lon: float | None = None,
        limit: int = 3,
    ) -> list[Office]:
        """Sedi per quartiere (NIL o indirizzo), Municipio o distanza da un punto."""
        found = list(self._offices)
        if municipio is not None:
            found = [o for o in found if o.municipio == municipio]
        if area:
            needle = area.lower()
            found = [
                o
                for o in found
                if needle in (o.nil_name or "").lower() or needle in o.address.lower()
            ]
        if lat is not None and lon is not None:
            located = [
                o.model_copy(
                    update={
                        "distance_km": round(
                            haversine_km(lat, lon, o.lat, o.lon), DISTANCE_DECIMALS
                        )
                    }
                )
                for o in found
                if o.lat is not None and o.lon is not None
            ]
            found = sorted(located, key=lambda o: o.distance_km or 0.0)
        return found[: max(limit, 0)]

    def office(self, office_id: str) -> Office | None:
        """Una sede per id (es. ``ds549-01``)."""
        return next((o for o in self._offices if o.id == office_id), None)

    def enti(self) -> list[Ente]:
        """Enti coinvolti nelle procedure."""
        return list(self._enti)

    def context_tables(self) -> dict[str, list[dict[str, str]]]:
        """Statistiche del Comune per il pannello (``data/context/*.csv``)."""
        return {k: [dict(r) for r in v] for k, v in self._context.items()}


def load_catalog(
    data_dir: Path,
    *,
    include_drafts: bool = False,
    overlays: Sequence[ApprovedCorrection] = (),
) -> Catalog:
    """Carica il catalogo leggendo i file di ``data_dir`` sul posto."""
    data_dir = Path(data_dir)
    services = [
        _RawService(_read_json(path), path.name)
        for path in sorted((data_dir / "services").glob("*.json"))
    ]
    offices_raw = _read_json(data_dir / "offices.json")
    enti_path = data_dir / "enti.json"
    enti_raw = _read_json(enti_path) if enti_path.exists() else []
    context: dict[str, list[dict[str, str]]] = {}
    for path in sorted((data_dir / "context").glob("*.csv")):
        with path.open(encoding="utf-8", newline="") as handle:
            context[path.stem] = list(csv.DictReader(handle))
    try:
        offices = [_office_from_raw(o) for o in offices_raw]
        enti = [Ente.model_validate(e) for e in enti_raw]
    except (ValidationError, AttributeError, TypeError) as exc:
        raise CatalogError("offices.json o enti.json non validi") from exc
    return Catalog(
        services=services,
        sources=read_sources(data_dir),
        offices=offices,
        enti=enti,
        context=context,
        include_drafts=include_drafts,
        overlays=overlays,
    )
