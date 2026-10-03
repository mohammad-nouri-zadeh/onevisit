"""Statistiche del Comune per la pagina "Contesto citta'" (storia B13).

Legge i CSV di ``data/context/`` con il modulo ``csv``: arrivi dall'estero (ds1959),
indagini sui servizi online (ds1702, ds1511, ds1512), residenti stranieri (ds74).
"""

import csv
from pathlib import Path

CONTEXT_FILES = {
    "arrivals": "arrivals-from-abroad.csv",
    "online": "online-services-helped.csv",
    "residence_groups": "residence-2022-helped-by-group.csv",
    "foreign_residents": "foreign-residents-2025-top20.csv",
}


def read_context(data_dir: Path) -> dict[str, list[dict[str, str]]]:
    """Tabelle del contesto; una tabella mancante diventa una lista vuota."""
    tables: dict[str, list[dict[str, str]]] = {}
    for key, name in CONTEXT_FILES.items():
        path = data_dir / "context" / name
        if not path.is_file():
            tables[key] = []
            continue
        with path.open(encoding="utf-8", newline="") as handle:
            tables[key] = list(csv.DictReader(handle))
    return tables
