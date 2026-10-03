"""Download the City open datasets OneVisit uses, through the CKAN API (no key).

    python data/tools/fetch_opendata.py           # all datasets
    python data/tools/fetch_opendata.py ds1702    # one dataset

Files land in data/opendata/<slug>.csv exactly as the City publishes them.
The big survey files are not committed (see .gitignore): run this to get them,
then data/tools/summarise_opendata.py to rebuild data/context/.
"""
import json
import pathlib
import sys
import urllib.parse
import urllib.request

DATA = pathlib.Path(__file__).resolve().parents[1]
API = "https://dati.comune.milano.it/api/3/action/package_show?"

DATASETS = {
    "ds549": "ds549-sedi-dei-servizi-anagrafici",
    "ds1702": "ds1702-rilevazione-qualita-servizio-richieste-residenza-anno-2022",
    "ds1511": "ds1511-rilevazione-della-qualita-del-servizio-appuntamenti-on-line-anno-2021",
    "ds1512": "ds1512-rilevazione-qualita-servizio-richieste-certificati-anno-2021",
    "ds1959": "ds1959-popolazione-iscrizioni-anagrafiche-per-luogo-di-provenienza",
    "ds74": "ds74-popolazione-residenti-stranieri-cittadinanza-e-municipio",
}


def fetch(short: str) -> pathlib.Path:
    slug = DATASETS[short]
    with urllib.request.urlopen(API + urllib.parse.urlencode({"id": slug}), timeout=30) as r:
        pkg = json.load(r)["result"]
    csv_res = next(res for res in pkg["resources"] if (res.get("format") or "").upper() == "CSV")
    out = DATA / "opendata" / f"{slug}.csv"
    urllib.request.urlretrieve(csv_res["url"], out)
    print(f"{short}: {out.relative_to(DATA.parent)} ({out.stat().st_size} bytes, resource modified {csv_res.get('last_modified', '?')[:10]})")
    return out


if __name__ == "__main__":
    for short in sys.argv[1:] or DATASETS:
        fetch(short)
