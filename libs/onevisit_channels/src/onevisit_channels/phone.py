"""Normalizzazione dei numeri di telefono in formato E.164 (storia C6)."""

import phonenumbers


def normalize_phone(raw: str, default_region: str = "IT") -> str:
    """Restituisce il numero in E.164 o solleva ``ValueError`` (senza ripetere il numero)."""
    try:
        parsed = phonenumbers.parse(raw, default_region)
    except phonenumbers.NumberParseException:
        raise ValueError("numero di telefono non riconosciuto") from None
    if not phonenumbers.is_possible_number(parsed):
        raise ValueError("numero di telefono non valido")
    return str(phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164))
