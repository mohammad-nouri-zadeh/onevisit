"""Comando ``onevisit catalog-check``: valida catalogo e fonti (storia A2).

Stampa un riepilogo come ``data/tools/validate.py``, gli avvisi e gli errori; esce con 1
se c'è almeno un errore, così un fatto senza fonte non arriva alla demo.
"""

from pathlib import Path

from onevisit_knowledge import inspect_catalog


def run(*, data_dir: Path) -> int:
    """Esegue la validazione e restituisce il codice di uscita."""
    report = inspect_catalog(data_dir)
    counts = report.counts
    print(
        f"Requirements and steps: {counts.get('verified', 0)} verified, "
        f"{counts.get('draft', 0)} draft, {counts.get('todo', 0)} todo"
    )
    print(
        f"Offices: {report.offices} "
        f"({report.offices_with_issues} with data issues in the City dataset)"
    )
    for warning in report.warnings:
        print(f"WARN  {warning}")
    for error in report.errors:
        print(f"ERROR {error}")
    print("OK" if not report.errors else f"{len(report.errors)} error(s)")
    return 1 if report.errors else 0
