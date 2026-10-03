"""Test di cifratura e impronta dei contatti (storie C2, C9)."""

import base64
import os

import pytest

from onevisit_privacy import ContactCipher, DecryptionError, InvalidKeyError


def _key() -> str:
    return base64.b64encode(os.urandom(32)).decode()


def test_round_trip_and_random_nonce() -> None:
    cipher = ContactCipher(_key(), _key())

    first = cipher.encrypt("utente@example.org")
    second = cipher.encrypt("utente@example.org")

    assert first != second
    assert cipher.decrypt(first) == "utente@example.org"
    assert cipher.decrypt(second) == "utente@example.org"
    assert b"utente" not in first


def test_digest_is_stable_across_case_and_spaces() -> None:
    cipher = ContactCipher(_key(), _key())

    assert cipher.digest("Utente@Example.org ") == cipher.digest("utente@example.org")
    assert cipher.digest("+39 333 000 0000") == cipher.digest("+393330000000")
    assert cipher.digest("a@example.org") != cipher.digest("b@example.org")


def test_wrong_key_cannot_decrypt() -> None:
    token = ContactCipher(_key(), _key()).encrypt("+393330000000")

    with pytest.raises(DecryptionError):
        ContactCipher(_key(), _key()).decrypt(token)


def test_invalid_keys_are_rejected_without_echoing_them() -> None:
    short = base64.b64encode(b"x" * 16).decode()

    with pytest.raises(InvalidKeyError) as info:
        ContactCipher(short, _key())
    assert short not in str(info.value)
    with pytest.raises(InvalidKeyError):
        ContactCipher("not base64 !!", _key())
