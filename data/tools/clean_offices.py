"""Turn the City's registry-office dataset (ds549) into a clean data/offices.json.

    python data/tools/clean_offices.py

Input:  data/opendata/ds549-sedi-dei-servizi-anagrafici.csv (as downloaded, untouched)
Output: data/offices.json

Nothing is invented: every field comes from the CSV. Where the CSV is incomplete
or stale, the office gets a `data_issues` entry instead of a guessed value. The one
exception is an entrance a saved official page confirms (CONFIRMED_ENTRANCES): it
carries the page's quote, and the dataset's wording goes to `dataset_notes` for staff. Those
issues are real findings about City data, useful for the panel and the pitch.
"""
import csv
import datetime as dt
import json
import pathlib
import re

DATA = pathlib.Path(__file__).resolve().parents[1]
SRC = DATA / "opendata" / "ds549-sedi-dei-servizi-anagrafici.csv"
OUT = DATA / "offices.json"

MONTHS = {m: i for i, m in enumerate(
    "gennaio febbraio marzo aprile maggio giugno luglio agosto settembre ottobre novembre dicembre".split(), 1)}
DATE_IN_TEXT = re.compile(r"(\d{1,2})\s+(" + "|".join(MONTHS) + r")\s+(20\d\d)", re.I)


def clean(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").replace("’", "'")).strip(" .;")


def split_address(raw: str) -> tuple[str, str | None]:
    """'(sede via Larga 12) INGRESSO PROVVISORIO da Via Pecorari 3' -> ('via Larga 12', 'Ingresso provvisorio da Via Pecorari 3')"""
    m = re.match(r"\(sede\s+(.+?)\)\s*(.*)", raw, re.I)
    if not m:
        return raw, None
    entrance = re.sub(r"INGRESSO PROVVISORIO", "Ingresso provvisorio", m.group(2).strip())
    return m.group(1).strip(), entrance or None


# Entrances that a saved official page confirms, with the quote validate.py checks.
# ds549 still calls the via Larga entrance "provvisorio"; the City's CIE page (updated
# 02/10/2026) gives the same entrance without calling it provisional.
CONFIRMED_ENTRANCES = {
    "via Larga 12": {
        "entrance_note": "Ingresso da via Pecorari 3",
        "source_id": "cie",
        "quote": "via Larga 12 (ingresso lato via Pecorari, 3)",
        "dataset_note": ("Il dataset ds549 indica l'ingresso da via Pecorari 3 come «provvisorio»; la pagina del Comune "
                         "sulla carta d'identità (aggiornata il 02/10/2026) indica lo stesso ingresso senza dirlo provvisorio: "
                         "va aggiornato il dataset."),
    },
}


def past_dates(text: str, today: dt.date) -> list[str]:
    found = []
    for d, month, y in DATE_IN_TEXT.findall(text):
        when = dt.date(int(y), MONTHS[month.lower()], int(d))
        if when < today:
            found.append(f"{d} {month} {y}")
    return found


def main() -> None:
    today = dt.date.today()
    with SRC.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f, delimiter=";"))

    offices = []
    for i, r in enumerate(rows, 1):
        title, phone = clean(r["titolo"]), clean(r["telefono"])
        hours, notes = clean(r["orari"]), clean(r["Note"])
        address, entrance = split_address(clean(r["Indirizzo"]))
        municipio = int(m.group(1)) if (m := re.search(r"Municipio\s+(\d+)", title)) else None
        low = notes.lower()

        issues = []
        if municipio is None:
            issues.append("Campo 'titolo' vuoto: il Municipio della sede non è indicato")
        if not phone:
            issues.append("Telefono mancante")
        if not notes:
            issues.append("Nessuna nota su prenotazione e accesso")
        confirmed = CONFIRMED_ENTRANCES.get(address)
        dataset_notes = []
        if confirmed:
            entrance = confirmed["entrance_note"]
            dataset_notes.append(confirmed["dataset_note"])
        elif entrance and "provvisorio" in entrance.lower():
            issues.append("Ingresso indicato come provvisorio: verificare se è ancora valido")
        for d in past_dates(hours + " " + notes, today):
            issues.append(f"Il testo cita una data già passata ({d}): informazione probabilmente non aggiornata")

        offices.append({
            "id": f"ds549-{i:02d}",
            "municipio": municipio,
            "address": address,
            "entrance_note": entrance,
            "address_raw": r["Indirizzo"],
            "phone": phone.replace("Infoline ", "") or None,
            "hours_it": hours or None,
            "notes_it": notes or None,
            "appointment_only": "esclusivamente su appuntamento" in low or None,
            "booking_without_spid": True if "senza necessità di registrazione" in low else None,
            "nil": {"id": int(r["ID_NIL"]), "name": clean(r["NIL"])},
            "lat": float(r["LAT_Y_4326"]),
            "lon": float(r["LONG_X_4326"]),
            "source_id": "ds549",
            "data_issues": issues,
        })
        if confirmed:
            offices[-1]["entrance_confirmed_by"] = {"source_id": confirmed["source_id"], "quote": confirmed["quote"]}
            offices[-1]["dataset_notes"] = dataset_notes

    OUT.write_text(json.dumps(offices, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    flagged = sum(1 for o in offices if o["data_issues"])
    print(f"{len(offices)} offices -> {OUT.relative_to(DATA.parent)} ({flagged} with data issues)")
    for o in offices:
        for issue in o["data_issues"]:
            print(f"  {o['id']} {o['address']}: {issue}")


if __name__ == "__main__":
    main()
