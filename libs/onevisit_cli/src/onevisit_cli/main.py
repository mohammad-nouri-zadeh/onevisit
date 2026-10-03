"""Comandi ``onevisit``: ingestione, validazione del catalogo, dati demo, valutazione.

Ogni comando e' uno stub che indica la storia del backlog che lo implementa.
"""

import typer

app = typer.Typer(help="Strumenti di sviluppo e operazioni di OneVisit.", no_args_is_help=True)


def _not_implemented(story: str) -> None:
    typer.echo(f"Non ancora implementato: vedi la storia {story} in docs/backlog.md.", err=True)
    raise typer.Exit(code=1)


@app.command()
def ingest() -> None:
    """Scarica le pagine ufficiali in data/sources/ (storia A1)."""
    _not_implemented("A1")


@app.command("catalog-check")
def catalog_check() -> None:
    """Valida il catalogo delle procedure in data/procedures/ (storia A2)."""
    _not_implemented("A2")


@app.command("seed-demo")
def seed_demo() -> None:
    """Genera i dati sintetici dello scenario demo (storia D1)."""
    _not_implemented("D1")


@app.command("eval")
def evaluate(quick: bool = typer.Option(False, help="Esegue solo gli scenari veloci.")) -> None:
    """Esegue gli scenari di valutazione dell'agente (storia C13)."""
    _not_implemented("C13")
