"""Rimozione dei dati personali, pseudonimizzazione, cifratura dei contatti (storia C9).

Interfaccia pubblica fissata in docs/contracts.md, sezione 2.
"""

from onevisit_privacy.cipher import ContactCipher, normalize_contact
from onevisit_privacy.errors import (
    ClaudeUnavailableError,
    DecryptionError,
    InvalidKeyError,
    PrivacyError,
)
from onevisit_privacy.feedback import (
    CAUSES,
    DEFAULT_MODEL,
    Cause,
    ClaudeClient,
    StructuredFeedback,
    Tone,
    structure_feedback,
)
from onevisit_privacy.logfilter import PiiLogFilter
from onevisit_privacy.redact import PLACEHOLDERS, Redaction, contains_pii, redact

__all__ = [
    "CAUSES",
    "DEFAULT_MODEL",
    "PLACEHOLDERS",
    "Cause",
    "ClaudeClient",
    "ClaudeUnavailableError",
    "ContactCipher",
    "DecryptionError",
    "InvalidKeyError",
    "PiiLogFilter",
    "PrivacyError",
    "Redaction",
    "StructuredFeedback",
    "Tone",
    "contains_pii",
    "normalize_contact",
    "redact",
    "structure_feedback",
]
