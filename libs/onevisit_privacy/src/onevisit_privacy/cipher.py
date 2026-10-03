"""Cifratura dei contatti e impronte per la ricerca (storie C2, C9).

AES-256-GCM con nonce casuale di 12 byte in testa al testo cifrato; HMAC-SHA256
del valore normalizzato (minuscolo, senza spazi) con una chiave separata.
"""

import base64
import binascii
import hashlib
import hmac
import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from onevisit_privacy.errors import DecryptionError, InvalidKeyError

# AES-256 e la chiave HMAC usano 32 byte.
KEY_BYTES = 32
# Lunghezza del nonce raccomandata per GCM.
NONCE_BYTES = 12


def _decode_key(value_b64: str, label: str) -> bytes:
    try:
        key = base64.b64decode(value_b64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise InvalidKeyError(f"chiave {label} non e' base64 valido") from exc
    if len(key) != KEY_BYTES:
        raise InvalidKeyError(f"chiave {label} deve essere di {KEY_BYTES} byte")
    return key


def normalize_contact(value: str) -> str:
    """Normalizza un contatto per l'impronta: minuscolo e senza spazi."""
    return "".join(value.split()).lower()


class ContactCipher:
    """Cifra e decifra email e telefoni; calcola l'impronta per deduplica e ricerca."""

    def __init__(self, encryption_key_b64: str, hmac_key_b64: str) -> None:
        self._aes = AESGCM(_decode_key(encryption_key_b64, "di cifratura"))
        self._hmac_key = _decode_key(hmac_key_b64, "HMAC")

    def encrypt(self, value: str) -> bytes:
        """Restituisce nonce + testo cifrato (con tag di autenticazione)."""
        nonce = os.urandom(NONCE_BYTES)
        return nonce + self._aes.encrypt(nonce, value.encode("utf-8"), None)

    def decrypt(self, token: bytes) -> str:
        """Decifra un valore prodotto da :meth:`encrypt`."""
        if len(token) <= NONCE_BYTES:
            raise DecryptionError("testo cifrato troppo corto")
        try:
            plain = self._aes.decrypt(token[:NONCE_BYTES], token[NONCE_BYTES:], None)
        except InvalidTag as exc:
            raise DecryptionError("testo cifrato non valido o chiave errata") from exc
        return plain.decode("utf-8")

    def digest(self, value: str) -> str:
        """HMAC-SHA256 esadecimale del valore normalizzato."""
        normalized = normalize_contact(value).encode("utf-8")
        return hmac.new(self._hmac_key, normalized, hashlib.sha256).hexdigest()
