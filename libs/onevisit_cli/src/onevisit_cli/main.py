"""Comandi ``onevisit``: ingestione, validazione del catalogo, dati demo, valutazione.

Ogni comando delega a un modulo dedicato (``ingest``, ``catalog``, ``seed``, ``evaluate``),
importato solo quando serve: così i comandi restano indipendenti tra loro e chi lavora
su uno non tocca gli altri. Solo questo modulo legge l'ambiente (percorsi e URL).
"""

import os
from pathlib import Path

import typer

app = typer.Typer(help="Strumenti di sviluppo e operazioni di OneVisit.", no_args_is_help=True)

_DEFAULT_DATA_DIR = Path(os.environ.get("ONEVISIT_DATA_DIR", "data"))


@app.command()
def ingest(
    source_id: str = typer.Argument(help="Id della fonte in data/sources.csv"),
    url: str = typer.Option("", help="URL ufficiale della pagina da scaricare"),
    html: Path | None = typer.Option(None, help="Pagina salvata dal browser, se il sito blocca gli script"),
    data_dir: Path = typer.Option(_DEFAULT_DATA_DIR, help="Cartella dei dati"),
) -> None:
    """Salva una pagina ufficiale in data/pages/<source_id>.md con hash e data (storia A1)."""
    from onevisit_cli import ingest as command

    raise typer.Exit(code=command.run(source_id=source_id, url=url, html_path=html, data_dir=data_dir))


@app.command("catalog-check")
def catalog_check(
    data_dir: Path = typer.Option(_DEFAULT_DATA_DIR, help="Cartella dei dati"),
) -> None:
    """Valida il catalogo: fonti esistenti, citazioni alla lettera, varianti coperte (storia A2)."""
    from onevisit_cli import catalog as command

    raise typer.Exit(code=command.run(data_dir=data_dir))


@app.command("seed-demo")
def seed_demo(
    seed: int = typer.Option(42, help="Seme fisso: stessi numeri a ogni esecuzione"),
    weeks: int = typer.Option(8, help="Settimane di casi sintetici"),
) -> None:
    """Genera i dati sintetici dello scenario demo (storia D1)."""
    from onevisit_cli import seed as command

    database_url = os.environ.get("ONEVISIT_DATABASE_URL", "")
    raise typer.Exit(code=command.run(database_url=database_url, seed=seed, weeks=weeks))


@app.command("eval")
def evaluate(
    quick: bool = typer.Option(False, help="Esegue solo gli scenari veloci."),
    data_dir: Path = typer.Option(_DEFAULT_DATA_DIR, help="Cartella dei dati"),
    report: Path = typer.Option(Path("docs/eval-report.md"), help="Dove scrivere il report"),
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
