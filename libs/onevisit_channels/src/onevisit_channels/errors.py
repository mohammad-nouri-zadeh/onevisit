"""Eccezioni della libreria dei canali (storie C5-C7).

I messaggi non contengono mai indirizzi, numeri o testi: solo motivi generici.
"""


class ChannelError(Exception):
    """Base di tutte le eccezioni di ``onevisit_channels``."""


class ChannelSendError(ChannelError):
    """L'invio verso il fornitore (SMS o SMTP) non e' riuscito."""


class TemplateNotFoundError(ChannelError):
    """Non esiste un modello per il tipo, la lingua e il canale richiesti."""


class LinkError(ChannelError):
    """Token di un link personale non valido, alterato o scaduto."""


class SignatureError(ChannelError):
    """Firma del webhook del fornitore assente o non valida."""
