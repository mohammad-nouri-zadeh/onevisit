"""Design system condiviso di OneVisit: token, componenti CSS, font e script locali.

Origine: il prototipo di design del team (branch ``momo/streamlit-demo``,
``design/onevisit-prototype.html``), adattato alle tre applicazioni. Guida in
``docs/design-system.md``.

Le applicazioni servono :data:`STATIC_DIR` sotto :data:`MOUNT_PATH` e nei template
includono, in quest'ordine, ``fonts.css`` e ``onevisit.css``; htmx e Chart.js stanno in
``vendor/`` così le pagine dei cittadini non chiamano CDN di terzi. La libreria non
conosce FastAPI: espone solo percorsi e nomi.
"""

from pathlib import Path

#: Cartella dei file statici del design system (CSS, font, script di terze parti).
STATIC_DIR: Path = Path(__file__).resolve().parent / "static"

#: Percorso URL dove ogni applicazione monta :data:`STATIC_DIR`.
MOUNT_PATH = "/ui"

#: File da includere in ogni pagina, nell'ordine.
STYLESHEETS: tuple[str, ...] = ("fonts.css", "onevisit.css")

#: Script di terze parti serviti in locale (licenze in ``static/vendor/NOTICE.md``).
HTMX_JS = "vendor/htmx.min.js"
CHART_JS = "vendor/chart.umd.min.js"


def asset_url(name: str) -> str:
    """URL di un file del design system, per esempio ``asset_url("onevisit.css")``."""
    return f"{MOUNT_PATH}/{name}"


__all__ = ["CHART_JS", "HTMX_JS", "MOUNT_PATH", "STATIC_DIR", "STYLESHEETS", "asset_url"]
