"""Sessioni di chat solo in memoria, con scadenza (storie B1-B4, C9).

Lo stato della conversazione non viene mai salvato su disco ne' registrato nei log:
il cookie contiene solo un identificativo opaco firmato.
"""

import secrets
import threading
import time
import uuid
from dataclasses import dataclass, field

from onevisit_agent import SessionState


@dataclass
class ChatSession:
    """Stato di una sessione: stato dell'agente e riferimenti opachi al caso."""

    state: SessionState = field(default_factory=SessionState)
    case_id: uuid.UUID | None = None
    missing_procedure: bool = False
    contact_saved: bool = False
    # Ultimo contatto salvato in questa sessione: un nuovo invio del modulo lo sostituisce.
    contact_id: uuid.UUID | None = None
    expires_at: float = 0.0


class SessionStore:
    """Archivio in memoria con TTL; sicuro tra thread."""

    def __init__(self, ttl_s: int) -> None:
        self._ttl_s = ttl_s
        self._items: dict[str, ChatSession] = {}
        self._lock = threading.Lock()

    def get(self, session_id: str | None) -> tuple[str, ChatSession]:
        """Restituisce la sessione esistente o ne crea una nuova (con un nuovo id)."""
        now = time.monotonic()
        with self._lock:
            self._purge(now)
            if session_id and session_id in self._items:
                item = self._items[session_id]
                item.expires_at = now + self._ttl_s
                return session_id, item
            new_id = secrets.token_urlsafe(24)
            item = ChatSession(expires_at=now + self._ttl_s)
            self._items[new_id] = item
            return new_id, item

    def peek(self, session_id: str | None) -> ChatSession | None:
        """Sessione esistente senza crearne una nuova."""
        with self._lock:
            self._purge(time.monotonic())
            return self._items.get(session_id) if session_id else None

    def _purge(self, now: float) -> None:
        expired = [k for k, v in self._items.items() if v.expires_at <= now]
        for key in expired:
            del self._items[key]
