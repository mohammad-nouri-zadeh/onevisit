"""Turn the City's open datasets into small, citable tables in data/context/.

    python data/tools/fetch_opendata.py && python data/tools/summarise_opendata.py

These numbers are for the pitch and the panel (size of the problem, baseline
satisfaction, which languages to support). They are computed, never typed in.
"""
import collections
import csv
import pathlib

DATA = pathlib.Path(__file__).resolve().parents[1]
OD, OUT = DATA / "opendata", DATA / "context"

RESIDENCE = "ds1702-rilevazione-qualita-servizio-richieste-residenza-anno-2022"
APPOINTMENTS = "ds1511-rilevazione-della-qualita-del-servizio-appuntamenti-on-line-anno-2021"
CERTIFICATES = "ds1512-rilevazione-qualita-servizio-richieste-certificati-anno-2021"
ARRIVALS = "ds1959-popolazione-iscrizioni-anagrafiche-per-luogo-di-provenienza"
FOREIGN = "ds74-popolazione-residenti-stranieri-cittadinanza-e-municipio"
HELPED = "Ha facilitato la gestione della tua esigenza?"
ANSWERS = ["Molto", "Abbastanza", "Poco", "Per niente"]


def load(slug: str) -> list[dict]:
    raw = (OD / f"{slug}.csv").read_bytes()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode("cp1252")  # the survey files are Windows-encoded
    header = text.split("\n", 1)[0]
    delim = ";" if header.count(";") > header.count(",") else ","
    return list(csv.DictReader(text.splitlines(), delimiter=delim))


def write(name: str, rows: list[dict]) -> None:
    with (OUT / name).open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"wrote data/context/{name} ({len(rows)} rows)")


def helped_row(label: str, rows: list[dict], **extra) -> dict:
    c = collections.Counter(r[HELPED] for r in rows)
    n = len(rows)
    neg = c["Poco"] + c["Per niente"]
    return {**extra, "group": label, "responses": n, **{a: c[a] for a in ANSWERS},
            "helped_little_or_not_pct": round(100 * neg / n, 1)}


def main() -> None:
    OUT.mkdir(exist_ok=True)

    # 1. How many people register in Milan arriving from abroad (ds1959)
    rows = load(ARRIVALS)
    years = sorted({r["Anno_evento"] for r in rows})
    out = []
    for y in years:
        yr = [r for r in rows if r["Anno_evento"] == y]
        total = sum(int(r["Numerosità"]) for r in yr)
        abroad = sum(int(r["Numerosità"]) for r in yr if r["Luogo_Prov"] == "Estero")
        out.append({"year": y, "registrations_from_abroad": abroad, "all_registrations": total,
                    "share_from_abroad_pct": round(100 * abroad / total, 1)})
    write("arrivals-from-abroad.csv", out)

    # 2. Largest foreign communities, latest year (ds74): which languages to support
    rows = load(FOREIGN)
    last = max(r["Anno"] for r in rows)
    yr = [r for r in rows if r["Anno"] == last]
    total = sum(int(r["Residenti"]) for r in yr)
    top = sorted(yr, key=lambda r: -int(r["Residenti"]))[:20]
    write(f"foreign-residents-{last}-top20.csv", [
        {"rank": i, "citizenship": r["Cittadinanza"], "residents": int(r["Residenti"]),
         "share_of_foreign_residents_pct": round(100 * int(r["Residenti"]) / total, 1)}
        for i, r in enumerate(top, 1)])

    # 3. Did the online service help? By service (ds1702, ds1512, ds1511)
    res = load(RESIDENCE)
    write("online-services-helped.csv", [
        helped_row("all respondents", res, service="Richieste residenza (online)", year=2022, dataset="ds1702"),
        helped_row("all respondents", load(CERTIFICATES), service="Certificati anagrafici (online)", year=2021, dataset="ds1512"),
        helped_row("all respondents", load(APPOINTMENTS), service="Appuntamenti online", year=2021, dataset="ds1511"),
    ])

    # 4. Residence requests: Italian vs foreign respondents, and by request type (ds1702)
    out = [helped_row(c, [r for r in res if r["Sei un cittadino"] == c], split="citizen")
           for c in sorted({r["Sei un cittadino"] for r in res})]
    out += [helped_row(t, [r for r in res if r["Quale richiesta hai presentato?"] == t], split="request")
            for t in sorted({r["Quale richiesta hai presentato?"] for r in res})]
    langs = collections.Counter(r["Lingua iniziale"] for r in res)
    write("residence-2022-helped-by-group.csv", out)
    print(f"ds1702 survey languages: {dict(langs)}")


if __name__ == "__main__":
    main()
