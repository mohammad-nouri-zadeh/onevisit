"""Il design system ha i file attesi e non fa uscire le pagine verso servizi esterni."""

import re

import onevisit_ui

_TOKENS = (
    "--paper",
    "--sheet",
    "--ink",
    "--graphite",
    "--pewter",
    "--silver",
    "--mist",
    "--sans",
    "--mono",
)


def test_every_stylesheet_and_script_exists() -> None:
    names = (*onevisit_ui.STYLESHEETS, onevisit_ui.HTMX_JS, onevisit_ui.CHART_JS)

    missing = [n for n in names if not (onevisit_ui.STATIC_DIR / n).is_file()]

    assert missing == []


def test_tokens_are_defined_for_light_and_dark_themes() -> None:
    css = (onevisit_ui.STATIC_DIR / "onevisit.css").read_text(encoding="utf-8")

    for token in _TOKENS:
        assert f"{token}:" in css
    assert ':root[data-theme="dark"]' in css
    assert "prefers-color-scheme: dark" in css


def test_fonts_are_local_files_that_exist() -> None:
    css = (onevisit_ui.STATIC_DIR / "fonts.css").read_text(encoding="utf-8")

    urls = re.findall(r"url\(([^)]+)\)", css)

    assert urls
    assert all(not u.startswith(("http:", "https:", "//")) for u in urls)
    assert all((onevisit_ui.STATIC_DIR / u.strip("'\"")).is_file() for u in urls)


def test_stylesheets_never_call_external_hosts() -> None:
    for name in onevisit_ui.STYLESHEETS:
        css = (onevisit_ui.STATIC_DIR / name).read_text(encoding="utf-8")

        assert "http://" not in css
        assert "https://" not in css


def test_pewter_text_colour_meets_aa_on_paper() -> None:
    def luminance(hex_colour: str) -> float:
        channels = [int(hex_colour[i : i + 2], 16) / 255 for i in (1, 3, 5)]
        linear = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
        return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]

    contrast = (luminance("#EDEEF0") + 0.05) / (luminance("#5E626B") + 0.05)

    assert contrast >= 4.5


def test_asset_url_uses_the_mount_path() -> None:
    assert onevisit_ui.asset_url("onevisit.css") == "/ui/onevisit.css"
