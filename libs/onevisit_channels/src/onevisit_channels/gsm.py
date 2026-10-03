"""Conteggio dei caratteri e dei segmenti SMS in GSM-7 (storia C6)."""

# Alfabeto di base GSM 03.38: un settetto per carattere.
GSM7_BASIC = (
    "@£$¥èéùìòÇ\nØø\rÅåΔ_ΦΓΛΩΠΨΣΘΞÆæßÉ !\"#¤%&'()*+,-./0123456789:;<=>?"
    "¡ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÑÜ§¿abcdefghijklmnopqrstuvwxyzäöñüà"
)
# Estensione GSM 03.38: due settetti per carattere (escape + carattere).
GSM7_EXTENDED = "^{}\\[~]|€\f"

# SMS singolo: 160 settetti; concatenato: 153 per segmento (il resto e' l'intestazione UDH).
SINGLE_SEGMENT_SEPTETS = 160
MULTI_SEGMENT_SEPTETS = 153


def is_gsm7(text: str) -> bool:
    """Vero se il testo si codifica tutto in GSM-7 (base o estensione)."""
    return all(ch in GSM7_BASIC or ch in GSM7_EXTENDED for ch in text)


def gsm7_length(text: str) -> int:
    """Numero di settetti occupati dal testo in GSM-7."""
    return sum(2 if ch in GSM7_EXTENDED else 1 for ch in text)


def sms_segments(text: str) -> int:
    """Numero di segmenti SMS necessari (solo testi GSM-7)."""
    length = gsm7_length(text)
    if length <= SINGLE_SEGMENT_SEPTETS:
        return 1
    return -(-length // MULTI_SEGMENT_SEPTETS)
