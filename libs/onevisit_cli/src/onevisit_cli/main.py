"""Comandi ``onevisit``: ingestione, validazione del catalogo, dati demo, valutazione.

Ogni comando delega a un modulo dedicato (``ingest``, ``catalog``, ``seed``, ``evaluate``),
importato solo quando serve: così i comandi restano indipendenti tra loro e chi lavora
su uno non tocca gli altri. Solo questo modulo legge l'ambiente (percorsi e URL).
"""

import os
from pathlib import Path
from typing import Annotated

import typer

app = typer.Typer(help="Strumenti di sviluppo e operazioni di OneVisit.", no_args_is_help=True)

_DEFAULT_DATA_DIR = Path(os.environ.get("ONEVISIT_DATA_DIR", "data"))
# Dove `onevisit eval` scrive il report, relativo alla radice del repository.
_DEFAULT_EVAL_REPORT = Path("docs/eval-report.md")
# Seme e durata predefiniti dello scenario demo (storia D1): stessi numeri a ogni esecuzione.
_DEFAULT_SEED = 42
_DEFAULT_WEEKS = 8

DataDirOption = Annotated[Path, typer.Option(help="Cartella dei dati")]


@app.command()
def ingest(
    source_id: Annotated[str, typer.Argument(help="Id della fonte in data/sources.csv")],
    url: Annotated[str, typer.Option(help="URL ufficiale della pagina da scaricare")] = "",
    html: Annotated[
        Path | None, typer.Option(help="Pagina salvata dal browser, se il sito blocca gli script")
    ] = None,
    data_dir: DataDirOption = _DEFAULT_DATA_DIR,
) -> None:
    """Salva una pagina ufficiale in data/pages/<source_id>.md con hash e data (storia A1)."""
    from onevisit_cli import ingest as command

    raise typer.Exit(
        code=command.run(source_id=source_id, url=url, html_path=html, data_dir=data_dir)
    )


@app.command("catalog-check")
def catalog_check(data_dir: DataDirOption = _DEFAULT_DATA_DIR) -> None:
    """Valida il catalogo: fonti esistenti, citazioni alla lettera, varianti coperte (storia A2)."""
    from onevisit_cli import catalog as command

    raise typer.Exit(code=command.run(data_dir=data_dir))


@app.command("seed-demo")
def seed_demo(
    seed: Annotated[
        int, typer.Option(help="Seme fisso: stessi numeri a ogni esecuzione")
    ] = _DEFAULT_SEED,
    weeks: Annotated[int, typer.Option(help="Settimane di casi sintetici")] = _DEFAULT_WEEKS,
) -> None:
    """Genera i dati sintetici dello scenario demo (storia D1)."""
    from onevisit_cli import seed as command

    database_url = os.environ.get("ONEVISIT_DATABASE_URL", "")
    raise typer.Exit(code=command.run(database_url=database_url, seed=seed, weeks=weeks))


@app.command("eval")
def evaluate(
    quick: Annotated[bool, typer.Option(help="Esegue solo gli scenari veloci.")] = False,
    data_dir: DataDirOption = _DEFAULT_DATA_DIR,
    report: Annotated[Path, typer.Option(help="Dove scrivere il report")] = _DEFAULT_EVAL_REPORT,
) -> None:
    """Esegue gli scenari di valutazione dell'agente con la vera API (storia C13)."""
    from onevisit_cli import evaluate as command

    raise typer.Exit(
        code=command.run(
            data_dir=data_dir,
            quick=quick,
            report_path=report,
            api_key=os.environ.get("ANTHROPIC_API_KEY", ""),
            model=os.environ.get("ONEVISIT_MODEL_CONVERSATION", "claude-sonnet-5-5"),
        )
    )
