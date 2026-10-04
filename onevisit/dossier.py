"""The dossier: a PDF the citizen brings to the appointment, or uses to prepare an online application.

Italian for the officer, with the citizen's language alongside: English, or Claude's translation
for Arabic, Spanish and Chinese (labelled as such; the Italian text and the quote are the ones
that count). Noto Naskh Arabic and Noto Sans SC are embedded, Arabic is shaped right to left. For a procedure sent online (the service
has an online form, e.g. residence from abroad) it says so and prints the form's link. It holds the service, the answers
that changed the checklist (never personal data), every verified requirement with
its source title, URL and verification date, the items still to verify with the
official page, the chosen office (open dataset ds549) and the appointment date.
Everything is recomputed from onevisit/kb.py, so only verified facts are printed.

    from onevisit import dossier
    pdf = dossier.build_pdf("carta-identita", {"motivo": "smarrimento-furto"},
                            office_id="ds549-11", appointment="2026-10-20")
"""
from __future__ import annotations

import datetime as dt
import pathlib

from fpdf import FPDF
from fpdf.enums import XPos, YPos

from onevisit import kb

FONTS = pathlib.Path(__file__).resolve().parents[1] / "app" / "assets" / "fonts"
RED = (166, 13, 39)        # Comune di Milano primary, used on comune.milano.it
INK = (26, 26, 26)
MUTED = (92, 111, 130)     # design-tokens-italia text-muted
LINE = (197, 199, 201)
FINAL_CHECK = ("La verifica finale spetta all'operatore allo sportello.",
               "The desk officer makes the final check.")
# Online procedures (the service has an online form): no desk, the registry office checks the application.
FINAL_CHECK_ONLINE = ("La verifica finale spetta all'ufficio anagrafe del Comune.",
                      "The City registry office makes the final check.")


# Headings in the citizen's language when it is not Italian or English (the English stays in the app).
LOCAL = {
    "ar": {"desk": "ملفك للشباك", "online": "ملفك للطلب الإلكتروني",
           "intro": "شروط موثّقة فقط من المصادر الرسمية، ولكل منها مصدره. بدون بيانات شخصية.",
           "translated": "ترجمة Claude: النص الإيطالي والاقتباس من المصدر هما المعتمدان.",
           "service": "الخدمة وإرسال الطلب", "service_desk": "الخدمة والموعد", "case": "الحالة", "reqs": "ما تحضّره وما تعرفه", "path": "المسار بالترتيب",
           "todo": "للتحقق في الصفحة الرسمية", "sources": "المصادر",
           "final": "القرار النهائي لموظف الشباك.", "final_online": "القرار النهائي لمكتب السجل المدني في البلدية."},
    "es": {"desk": "Tu dossier para la ventanilla", "online": "Tu dossier para la solicitud online",
           "intro": "Solo requisitos verificados en las fuentes oficiales, cada uno con su fuente. Sin datos personales.",
           "translated": "Traducción de Claude: el texto en italiano y la cita de la fuente son los que cuentan.",
           "service": "Servicio y envío de la solicitud", "service_desk": "Servicio y cita", "case": "El caso", "reqs": "Qué preparar y qué saber", "path": "El recorrido, en orden",
           "todo": "Por comprobar en la página oficial", "sources": "Fuentes",
           "final": "La comprobación final la hace el funcionario de la ventanilla.",
           "final_online": "La comprobación final la hace la oficina del registro del Ayuntamiento."},
    "zh": {"desk": "你的窗口材料单", "online": "你的在线申请材料单",
           "intro": "只包含根据官方来源核实的要求，每项都有来源。不含个人信息。",
           "translated": "Claude 翻译：以意大利语原文和来源引文为准。",
           "service": "服务和申请提交", "service_desk": "服务和预约", "case": "你的情况", "reqs": "需要准备和了解的事项", "path": "办理流程（按顺序）",
           "todo": "需在官方页面确认", "sources": "来源",
           "final": "最终由窗口工作人员审核。", "final_online": "最终由市政府户籍办公室审核。"},
}


def _label(option_id: str, lang: str) -> str:
    from onevisit import demo  # option labels live with the demo script (it, en, ar, es, zh)
    return demo.option_label(option_id, lang)


# Group headings of the checklist (kb.CATEGORIES), Italian for the desk and English alongside.
GROUPS = {
    "prepare": ("Da preparare", "To prepare"),
    "how": ("Come funziona", "How it works"),
    "if-urgent": ("Se è urgente", "If it's urgent"),
    "after": ("Dopo", "Afterwards"),
}


def _office(office_id: str | None) -> dict | None:
    if not office_id:
        return None
    return next((o for o in kb.find_offices(limit=1000) if o["id"] == office_id), None)


def _date(value: str | dt.date | None) -> str:
    if not value:
        return ""
    if isinstance(value, dt.date):
        return value.strftime("%d/%m/%Y")
    try:
        return dt.date.fromisoformat(value).strftime("%d/%m/%Y")
    except ValueError:
        return str(value)


class _Doc(FPDF):
    def __init__(self, final_check: tuple[str, str] = FINAL_CHECK) -> None:
        super().__init__(format="A4")
        self.final_check = final_check
        self.second_lang = "en"  # the language printed under the Italian
        self.set_margins(18, 16, 18)
        self.set_auto_page_break(True, margin=22)
        self.add_font("Titillium", "", str(FONTS / "TitilliumWeb-Regular.ttf"))
        self.add_font("Titillium", "B", str(FONTS / "TitilliumWeb-Bold.ttf"))
        self.add_font("Titillium", "I", str(FONTS / "TitilliumWeb-Regular.ttf"))
        self.add_font("DejaVu", "", str(FONTS / "DejaVuSans.ttf"))
        self.add_font("Naskh", "", str(FONTS / "NotoNaskhArabic-Regular.ttf"))
        self.add_font("Naskh", "B", str(FONTS / "NotoNaskhArabic-Bold.ttf"))
        self.add_font("NotoSC", "", str(FONTS / "NotoSansSC-Regular-GB2312.ttf"))
        self.add_font("NotoSC", "B", str(FONTS / "NotoSansSC-Regular-GB2312.ttf"))
        self.set_fallback_fonts(["DejaVu"], exact_match=False)
        self.set_title("Dossier per lo sportello")
        self.set_author("OneVisit (prototipo)")
        self.set_creator("OneVisit")

    def header(self) -> None:
        self.set_fill_color(*RED)
        self.rect(0, 0, self.w, 4, style="F")

    def footer(self) -> None:
        self.set_y(-16)
        self.set_draw_color(*LINE)
        self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
        self.set_font("Titillium", "", 8)
        self.set_text_color(*MUTED)
        self.cell(0, 5, f"{self.final_check[0]} {self.final_check[1]}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.cell(0, 4, f"OneVisit · prototipo non ufficiale, non è un servizio del Comune di Milano · pagina {self.page_no()}/{{nb}}")

    # --- small helpers -------------------------------------------------
    def section(self, it: str, en: str) -> None:
        if self.get_y() > self.h - 50:
            self.add_page()
        self.ln(4)
        self.set_font("Titillium", "B", 13)
        self.set_text_color(*RED)
        self.cell(0, 7, it, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        if self.second_lang in ("ar", "zh"):
            self.local(en, self.second_lang, 9.5)
        else:
            self.set_font("Titillium", "", 9.5)
            self.set_text_color(*MUTED)
            self.cell(0, 4.5, en, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_draw_color(*LINE)
        self.line(self.l_margin, self.get_y() + 1, self.w - self.r_margin, self.get_y() + 1)
        self.ln(3)

    def para(self, text: str, size: float = 10.5, bold: bool = False, color: tuple = INK,
             indent: float = 0, link: str = "") -> None:
        self.set_font("Titillium", "B" if bold else "", size)
        self.set_text_color(*color)
        self.set_x(self.l_margin + indent)
        self.multi_cell(self.w - self.l_margin - self.r_margin - indent, size * 0.5, text, align="L",
                        new_x=XPos.LMARGIN, new_y=YPos.NEXT, link=link)

    def local(self, text: str, lang: str, size: float = 9, color: tuple = MUTED, indent: float = 0,
              bold: bool = False) -> None:
        """A line in the citizen's language: Arabic shaped right to left, Chinese in Noto Sans SC."""
        if lang == "ar":
            self.set_font("Naskh", "B" if bold else "", size)
            self.set_text_shaping(use_shaping_engine=True, direction="rtl", script="arab", language="ar")
            align = "R"
        elif lang == "zh":
            self.set_font("NotoSC", "B" if bold else "", size)
            self.set_text_shaping(use_shaping_engine=True)
            align = "L"
        else:
            self.para(text, size, bold=bold, color=color, indent=indent)
            return
        self.set_text_color(*color)
        self.set_x(self.l_margin + indent)
        self.multi_cell(self.w - self.l_margin - self.r_margin - indent, size * 0.62, text, align=align,
                        new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_text_shaping(False)

    def checkbox(self, ticked: bool) -> None:
        x, y = self.l_margin, self.get_y() + 1.2
        self.set_draw_color(*INK)
        self.set_line_width(0.35)
        self.rect(x, y, 3.6, 3.6)
        if ticked:
            self.line(x + 0.7, y + 1.9, x + 1.5, y + 2.9)
            self.line(x + 1.5, y + 2.9, x + 3.0, y + 0.7)
        self.set_line_width(0.2)


def build_pdf(service_id: str, answers: dict | None = None, *, office_id: str | None = None,
              appointment: str | dt.date | None = None, ticked: set[str] | None = None,
              today: dt.date | None = None, lang: str = "it") -> bytes:
    """Build the desk dossier for one case. Only verified facts from kb are printed.

    Italian first; under it English, or the citizen's language (`lang` ar, es or zh) when a
    current translation by Claude exists for that text.
    """
    answers = dict(answers or {})
    second = lang if lang in LOCAL else "en"
    loc = LOCAL.get(second, {})

    def under(pdf: "_Doc", it: str | None, en: str | None, local: str | None, size: float = 9, indent: float = 0) -> None:
        """The second-language line under an Italian text: the citizen's language when translated, else English."""
        if second != "en" and local:
            pdf.local(local, second, size, MUTED, indent)
        elif en:
            pdf.para(en, size, color=MUTED, indent=indent)

    ticked = ticked or set()
    service = kb.get_service(service_id)
    if not service:
        raise ValueError(f"Unknown service {service_id!r}")
    cl = kb.checklist(service_id, answers)
    office = _office(office_id)
    today = today or dt.date.today()
    links = kb.service_links(service_id)
    online = links.get("online_form_url")
    final_check = FINAL_CHECK_ONLINE if online else FINAL_CHECK

    pdf = _Doc(final_check)
    pdf.second_lang = second
    pdf.alias_nb_pages()
    pdf.add_page()

    # Title
    pdf.set_font("Titillium", "B", 9)
    pdf.set_text_color(*RED)
    pdf.cell(0, 5, "ONEVISIT · SERVIZI ANAGRAFICI · MILANO", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font("Titillium", "B", 22)
    pdf.set_text_color(*INK)
    pdf.cell(0, 11, "Dossier per la domanda online" if online else "Dossier per lo sportello",
             new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font("Titillium", "", 13)
    pdf.set_text_color(*MUTED)
    if loc:
        pdf.local(loc["online" if online else "desk"], second, 13, MUTED)
    else:
        pdf.cell(0, 6, "Your online application dossier" if online else "Your desk dossier",
                 new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(2)
    pdf.para(f"Preparato con OneVisit il {_date(today)}. Contiene solo requisiti verificati sulle fonti ufficiali, "
             "ognuno con la sua fonte. Nessun dato personale.", 9.5, color=MUTED)
    if loc:
        pdf.local(loc["intro"], second, 9.5)
        pdf.local(loc["translated"], second, 9.5, RED)
    else:
        pdf.para(f"Prepared with OneVisit on {_date(today)}. Only requirements verified against official sources, "
                 "each with its source. No personal data.", 9.5, color=MUTED)

    # Service and appointment
    pdf.section("Servizio e invio della domanda" if online else "Servizio e appuntamento",
                (loc["service"] if online else loc["service_desk"]) if loc
                else ("Service and application" if online else "Service and appointment"))
    title = service.get("title") or {}
    pdf.para(title.get("it", service_id), 13, bold=True)
    if title.get("en"):
        pdf.para(title["en"], 10, color=MUTED)
    pdf.ln(1.5)
    if appointment:
        label = "Data prevista di invio / Planned submission date" if online else "Data dell'appuntamento / Appointment date"
        pdf.para(f"{label}: {_date(appointment)}", 11, bold=True)
    if office:
        where = office["address"] + (f" ({office['entrance_note']})" if office.get("entrance_note") else "")
        pdf.para(f"Sede / Office: {where}" + (f" · Municipio {office['municipio']}" if office.get("municipio") else ""),
                 11, bold=not appointment)
        if office.get("hours_it"):
            pdf.para(f"Orari / Hours: {office['hours_it']}", 9.5)
        if office.get("phone"):
            pdf.para(f"Telefono / Phone: {office['phone']}", 9.5)
        src = kb.get_source(office.get("source_id", "ds549")) or {}
        pdf.para(f"Fonte: {src.get('title', 'ds549')} ({office.get('source_id', 'ds549')}), "
                 f"{src.get('url', '')}, scaricato il {src.get('retrieved_at', '')}", 8.5, color=MUTED)
        for issue in office.get("data_issues", []):
            pdf.para(f"Nota sui dati del Comune / City data note: {issue}", 8.5, color=MUTED)
    if online:
        pdf.para(f"Domanda online / Online application [{online['source_id']}]:", 9.5, bold=True)
        pdf.para(online["url"], 9.5, color=RED, link=online["url"])
    booked_at_desk = "prenotazione" in {s["id"] for s in cl.get("sources", []) if s}
    booking = links.get("booking_url") or (
        {"url": (kb.get_source("prenotazione") or {}).get("url"), "source_id": "prenotazione"} if booked_at_desk else None)
    if booking and booking.get("url") and not online and not appointment:
        pdf.para(f"Prenotazione / Booking [{booking['source_id']}]:", 9.5, bold=True)
        pdf.para(booking["url"], 9.5, color=RED, link=booking["url"])

    # The case
    questions = [q for q in service.get("deciding_questions", []) if q.get("id") in answers]
    if questions:
        pdf.section("Il caso", loc.get("case") or "The case: only the answers that change the list")
        for q in questions:
            value = answers[q["id"]]
            pdf.para(f"{q.get('ask_it', q['id'])} → {_label(value, 'it')}", 10)
            if loc:
                pdf.local(_label(value, second), second, 9)
            elif q.get("ask_en"):
                pdf.para(f"{q['ask_en']} → {_label(value, 'en')}", 9, color=MUTED)
            pdf.ln(0.8)

    # Verified requirements
    reqs = cl.get("requirements", [])
    if online:
        pdf.section(f"Da preparare e da sapere: {len(reqs)} requisiti verificati",
                    f"{loc['reqs']}: {len(reqs)}" if loc else f"What to prepare and know: {len(reqs)} verified requirements")
    else:
        pdf.section(f"Da portare e da sapere: {len(reqs)} requisiti verificati",
                    f"{loc['reqs']}: {len(reqs)}" if loc else f"What to bring and know: {len(reqs)} verified requirements")
    if not reqs:
        pdf.para("Le fonti salvate non contengono ancora requisiti verificati per questo caso.", 10)
        pdf.para("The saved sources don't contain verified requirements for this case yet.", 9, color=MUTED)
    groups: dict[str, list[dict]] = {}
    for r in reqs:
        groups.setdefault(r.get("category") or "prepare", []).append(r)
    order = [c for c in kb.CATEGORIES if c in groups] + [c for c in groups if c not in kb.CATEGORIES]
    for category in order:
        by_source: dict[str, list[dict]] = {}
        for r in groups[category]:
            by_source.setdefault(r["source_id"], []).append(r)
        # largest source first (as in the app): the official document list before the side notes
        items = [r for _, rs in sorted(by_source.items(), key=lambda kv: -len(kv[1])) for r in rs]
        if pdf.get_y() > pdf.h - 50:
            pdf.add_page()
        it, en = GROUPS.get(category, (category, category))
        pdf.ln(1)
        pdf.para(f"{it} ({len(items)})", 11.5, bold=True, color=RED)
        if loc:
            from onevisit import demo  # group names in ar, es, zh live with the demo script
            pdf.local(demo.category_label(category, second), second, 8.5)
        else:
            pdf.para(en, 8.5, color=MUTED)
        pdf.ln(1)
        for r in items:
            if pdf.get_y() > pdf.h - 40:
                pdf.add_page()
            pdf.checkbox(r["id"] in ticked)
            pdf.para(r.get("text_it", ""), 10.5, bold=True, indent=6)
            local, translated = kb.req_text(service_id, r, second) if loc else ("", False)
            under(pdf, r.get("text_it"), r.get("text_en"), local if translated else None, 9, 6)
            src = kb.get_source(r["source_id"]) or {}
            pdf.para(f"Fonte [{r['source_id']}]: {src.get('title', r['source_id'])} · verificata il {r.get('verified_at') or ''}",
                     8, color=MUTED, indent=6)
            if r.get("quote"):
                quote = r["quote"] if len(r["quote"]) <= 280 else r["quote"][:277].rstrip() + "…"
                pdf.para(f"Testo della fonte: «{quote}»", 8, color=MUTED, indent=6)
            pdf.ln(1.5)
        pdf.ln(1)

    # The path across offices
    steps = sorted(service.get("steps") or [], key=lambda x: x.get("order", 0))
    if steps:
        from onevisit import demo  # body names from data/enti.json
        pdf.section("Il percorso, in ordine", loc.get("path") or "The path, in order")
        for n, step in enumerate(steps, start=1):
            who = " / ".join(dict.fromkeys(demo.ente_name(b) for b in [step.get("ente")]
                                           + [r.get("ente") for r in step.get("routes") or []] if b))
            title = f"{step['title_it']} · " if step.get("title_it") else ""
            pdf.para(f"{n}. {title}{who}", 9, bold=True, color=MUTED)
            if step.get("booking") and appointment and not online:
                pdf.para(f"Appuntamento già prenotato per il {_date(appointment)}.", 10, indent=4)
                pdf.ln(1)
                continue
            routes = [(step, None)] + [(r, k) for k, r in enumerate(step.get("routes") or [], start=1)]
            for item, k in routes:
                prefix = "– " if step.get("routes") else ""
                pdf.para(prefix + item.get("text_it", ""), 10, indent=4)
                local, translated = (kb.step_text(service_id, step, second) if k is None
                                     else kb.route_text(service_id, step, k, second)) if loc else ("", False)
                under(pdf, item.get("text_it"), item.get("text_en"), local if translated else None, 9, 4)
                if item.get("source_id"):
                    src = kb.get_source(item["source_id"]) or {}
                    pdf.para(f"Fonte: {src.get('title', item['source_id'])} [{item['source_id']}] · verificato il {item.get('verified_at') or ''}",
                             8.5, color=MUTED, indent=4)
            pdf.ln(1)

    # Still to verify
    todo = kb.open_items(service_id, cl.get("not_yet_verified", []))
    if todo:
        pdf.section("Da verificare sulla pagina ufficiale",
                    loc.get("todo") or "Still to verify on the official page (no verified source yet)")
        by_url: dict[str, list[dict]] = {}
        for item in todo:
            by_url.setdefault(item["url"], []).append(item)
        for url, items in by_url.items():
            for item in items:
                pdf.para(f"?  {item.get('text_it') or item['id']}", 10, bold=True)
                local, translated = (kb.localized(service_id, "req", item["id"], "text", item.get("text_it"),
                                                  item.get("text_en"), second) if loc else ("", False))
                under(pdf, item.get("text_it"), item.get("text_en"), local if translated else None, 9, 4)
            pdf.para(f"Pagina ufficiale / Official page: {url}", 8.5, color=RED, indent=4, link=url)
            pdf.ln(1)
    if cl.get("still_to_ask"):
        open_q = [q for q in service.get("deciding_questions", []) if q["id"] in cl["still_to_ask"]]
        pdf.section("Domande ancora aperte", "Open questions that could change the list")
        for q in open_q:
            pdf.para(f"{q.get('ask_it', q['id'])} / {q.get('ask_en', '')}", 9.5)

    # Sources
    shown_links = [online] if online else ([booking] if booking and booking.get("url") and not appointment else [])
    cited = sorted({r["source_id"] for r in reqs} | {x["source_id"] for x in steps if x.get("source_id")}
                   | ({office.get("source_id", "ds549")} if office else set())
                   | {x["source_id"] for x in shown_links})
    if cited:
        pdf.section("Fonti", loc.get("sources") or "Sources")
        for sid in cited:
            src = kb.get_source(sid) or {}
            pdf.para(f"[{sid}] {src.get('title', '')} · {src.get('publisher', '')} · consultata il {src.get('retrieved_at', '')}", 9)
            if src.get("url"):
                pdf.para(src["url"], 8.5, color=RED, indent=4, link=src["url"])

    pdf.ln(5)
    pdf.set_draw_color(*RED)
    pdf.set_line_width(0.6)
    y = pdf.get_y()
    pdf.line(pdf.l_margin, y, pdf.l_margin, y + 12)
    pdf.set_line_width(0.2)
    pdf.para(final_check[0], 11, bold=True, indent=3)
    pdf.para(final_check[1] + " OneVisit does not decide whether documents are accepted.", 9.5, color=MUTED, indent=3)
    if loc:
        pdf.local(loc["final_online" if online else "final"], second, 9.5, MUTED, 3)
    return bytes(pdf.output())


def filename(service_id: str, appointment: str | dt.date | None = None) -> str:
    stamp = _date(appointment).replace("/", "-") if appointment else dt.date.today().isoformat()
    return f"onevisit-dossier-{service_id}-{stamp}.pdf"
