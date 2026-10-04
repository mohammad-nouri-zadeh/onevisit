"""Claude translates the checklist into the citizen's language; the Italian stays authoritative.

Requirement, step and section texts are written in Italian and English in data/services.
For the other languages of the app (Arabic, Spanish, Chinese) Claude translates them:

- at runtime, with Claude Haiku 4.5 and a structured output that maps each text key to its
  translation, for any text the cache doesn't have yet (a new or changed requirement);
- ahead of time, into data/i18n/requirements.<lang>.json, so the demo without a key shows
  the same translations. Each entry keeps the Italian it was made from: when the Italian
  changes, the entry is stale and the app shows English until it is translated again.

The verbatim quote from the official page is never translated: it stays behind the (?) as
the text that counts, and the app labels every translated item "Traduzione di Claude".

    python -m onevisit.translate --lang ar           # list what is missing or stale
    python -m onevisit.translate --lang ar --write   # translate it with Claude (needs a key)
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys

from onevisit import kb, validator
from onevisit.agent import FAST_MODEL

LANG_NAMES = {"ar": "Arabic (Modern Standard Arabic)", "es": "Spanish", "zh": "Simplified Chinese",
              "fr": "French", "pt": "Portuguese"}

SCHEMA = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"key": {"type": "string"}, "text": {"type": "string"}},
                "required": ["key", "text"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["items"],
    "additionalProperties": False,
}

INSTRUCTIONS = """Translate these texts from a City of Milan registry checklist into {language}, for a newcomer who reads {language} better than Italian.
Rules:
- Translate the English text, using the Italian text to resolve doubts. Keep the meaning exactly: add nothing, drop nothing, no advice of your own.
- Keep official Italian names in Italian and add a short translation in parentheses the first time, e.g. "codice fiscale", "permesso di soggiorno", "Questura", "Sportello Unico", "Agenzia delle Entrate", "comodato", "rogito", "denuncia", "SPID", "CIE".
- Keep numbers, dates, amounts, hours, addresses and file formats exactly as written.
- Never say or imply that a document or a person is eligible, valid, accepted or guaranteed; "in corso di validità" means "not expired".
- Plain, short sentences. Return one item per key, with the same key."""


def _texts(service_id: str, keys: dict[str, dict]) -> str:
    return json.dumps([{"key": k, "it": v["it"], "en": v["en"]} for k, v in keys.items()], ensure_ascii=False, indent=1)


def translate(service_id: str, lang: str, client, keys: dict[str, dict] | None = None, batch: int = 40) -> dict[str, dict]:
    """Ask Claude for the translations of `keys` (default: what is missing for `lang`).

    Returns {key: {"it": <Italian source>, "text": <translation>}}. A translation is dropped,
    not repaired, if its key is unknown or it contains an eligibility or validity claim.
    """
    if lang not in LANG_NAMES:
        return {}
    keys = kb.missing_translations(service_id, lang) if keys is None else keys
    out: dict[str, dict] = {}
    pending = list(keys.items())
    for start in range(0, len(pending), batch):
        chunk = dict(pending[start:start + batch])
        resp = client.messages.create(
            model=FAST_MODEL, max_tokens=8000,
            system=INSTRUCTIONS.format(language=LANG_NAMES[lang]),
            messages=[{"role": "user", "content": _texts(service_id, chunk)}],
            output_config={"format": {"type": "json_schema", "schema": SCHEMA}},
        )
        if resp.stop_reason == "refusal":
            continue
        data = json.loads("".join(b.text for b in resp.content if b.type == "text") or "{}")
        for item in data.get("items", []):
            key, text = item.get("key"), (item.get("text") or "").strip()
            if key in chunk and text and not validator.forbidden_phrases_in(text):
                out[key] = {"it": chunk[key]["it"], "text": text}
    return out


def ensure(service_id: str, lang: str, client) -> int:
    """Runtime step: translate what the cache lacks for this service and keep it for this process."""
    if lang in ("it", "en") or lang not in LANG_NAMES:
        return 0
    missing = kb.missing_translations(service_id, lang)
    if not missing:
        return 0
    done = translate(service_id, lang, client, missing)
    kb.add_runtime_translations(lang, done)
    return len(done)


def _write(lang: str, texts: dict[str, dict]) -> None:
    path = kb.I18N / f"requirements.{lang}.json"
    data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"lang": lang, "texts": {}}
    data["texts"].update(texts)
    data["texts"] = dict(sorted(data["texts"].items()))
    data["updated"] = dt.date.today().isoformat()
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--lang", required=True, choices=sorted(LANG_NAMES))
    ap.add_argument("--write", action="store_true", help="translate the missing texts with Claude and save them")
    args = ap.parse_args(argv)
    total = 0
    for svc in kb.list_services():
        missing = kb.missing_translations(svc["id"], args.lang)
        print(f"{svc['id']}: {len(missing)} texts missing or stale in {args.lang}")
        total += len(missing)
        if args.write and missing:
            import anthropic
            done = translate(svc["id"], args.lang, anthropic.Anthropic(), missing)
            _write(args.lang, done)
            print(f"  translated and saved: {len(done)}")
    return 0 if args.write or total == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
