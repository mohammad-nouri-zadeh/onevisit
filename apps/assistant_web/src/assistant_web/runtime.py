"""Dipendenze dell'applicazione create in modo pigro: catalogo, agente, database, chiavi (B1-B11).

Nessuna connessione e nessun caricamento all'import: ``create_app()`` non deve fallire
senza variabili d'ambiente o senza database. Le correzioni approvate (B11) vengono
lette dal database al piu' ogni ``catalog_refresh_s`` secondi.
"""

import logging
import secrets
import threading
import time
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from datetime import UTC, datetime
from types import ModuleType
from typing import Any

from sqlalchemy.exc import SQLAlchemyError

from assistant_web.config import Settings
from assistant_web.render import SourceLink
from assistant_web.sessions import SessionStore
from onevisit_agent import Agent, AgentConfig, AnthropicClaudeClient, ClaudeClient
from onevisit_channels import LinkSigner, resolve_link_signing_key
from onevisit_knowledge import ApprovedCorrection, Catalog, load_catalog
from onevisit_privacy import ClaudeClient as FeedbackClient
from onevisit_privacy import ContactCipher

logger = logging.getLogger(__name__)

CatalogLoader = Callable[[Sequence[ApprovedCorrection]], Catalog]
SessionFactory = Callable[[], Any]


class Runtime:
    """Contenitore delle dipendenze, condiviso dalle rotte tramite ``app.state.runtime``."""

    def __init__(
        self,
        settings: Settings,
        *,
        claude_client: ClaudeClient | None,
        catalog_loader: CatalogLoader | None,
        session_factory: SessionFactory | None,
        repo: ModuleType | Any | None,
        feedback_client: FeedbackClient | None,
    ) -> None:
        self.settings = settings
        self.sessions = SessionStore(settings.session_ttl_s)
        self._claude_client = claude_client
        self._catalog_loader = catalog_loader or self._default_loader
        self._session_factory = session_factory
        self._repo = repo
        self._feedback_client = feedback_client
        self._lock = threading.Lock()
        self._catalog: Catalog | None = None
        self._agent: Agent | None = None
        self._loaded_at = 0.0
        # Stessa chiave del gateway: senza chiave configurata vale quella di sviluppo
        # condivisa, e fuori sviluppo l'avvio fallisce (LinkError, fail closed).
        self.link_signer = LinkSigner(
            resolve_link_signing_key(settings.link_signing_key, environment=settings.environment)
        )
        self.session_secret = settings.session_secret or secrets.token_urlsafe(32)

    # --- catalogo e agente -------------------------------------------------------------

    def _default_loader(self, overlays: Sequence[ApprovedCorrection]) -> Catalog:
        return load_catalog(
            self.settings.data_dir, include_drafts=self.settings.include_drafts, overlays=overlays
        )

    def _overlays(self) -> list[ApprovedCorrection]:
        """Correzioni approvate dal pannello; lista vuota se il database non risponde."""
        if not self.db_enabled:
            return []
        try:
            with self.db() as s:
                rows = self.repo.approved_corrections(s)
        except SQLAlchemyError as exc:
            logger.warning("correzioni approvate non lette: %s", type(exc).__name__)
            return []
        return [
            ApprovedCorrection(
                id=str(r.id),
                service_id=r.service_id,
                requirement_id=r.requirement_id,
                text_it=r.text_it,
                text_en=r.text_en,
                approved_at=r.approved_at,
            )
            for r in rows
        ]

    def catalog(self) -> Catalog:
        """Catalogo con gli overlay, ricaricato al piu' ogni ``catalog_refresh_s`` secondi."""
        with self._lock:
            now = time.monotonic()
            if self._catalog is None or now - self._loaded_at >= self.settings.catalog_refresh_s:
                self._catalog = self._catalog_loader(self._overlays())
                self._agent = None
                self._loaded_at = now
            return self._catalog

    def claude_client(self) -> ClaudeClient | None:
        """Client Claude: quello iniettato, altrimenti Anthropic se c'e' la chiave."""
        if self._claude_client is None and self.settings.anthropic_api_key:
            self._claude_client = AnthropicClaudeClient(self.settings.anthropic_api_key)
        return self._claude_client

    def agent(self) -> Agent | None:
        """Agente pronto, o ``None`` senza client Claude (si mostra il messaggio di cortesia)."""
        catalog = self.catalog()
        client = self.claude_client()
        if client is None:
            return None
        with self._lock:
            if self._agent is None:
                config = AgentConfig(
                    model_conversation=self.settings.model_conversation,
                    model_fast=self.settings.model_fast,
                    official_fallback_url=self.settings.official_fallback_url,
                    stale_after_days=self.settings.source_stale_days,
                    today=datetime.now(UTC).date(),
                )
                self._agent = Agent(client=client, catalog=catalog, config=config)
            return self._agent

    def feedback_client(self) -> FeedbackClient | None:
        """Client per structure_feedback: solo se c'e' una chiave API (o iniettato nei test)."""
        if self._feedback_client is None and self.settings.anthropic_api_key:
            import anthropic

            from onevisit_privacy.anthropic_client import AnthropicFeedbackClient

            self._feedback_client = AnthropicFeedbackClient(
                anthropic.Anthropic(
                    api_key=self.settings.anthropic_api_key,
                    timeout=self.settings.feedback_timeout_s,
                    max_retries=self.settings.feedback_max_retries,
                )
            )
        return self._feedback_client

    def source_link(self, source_id: str) -> SourceLink | None:
        """Titolo, URL e data di verifica di una fonte del catalogo."""
        source = self.catalog().source(source_id)
        if source is None:
            return None
        verified = source.retrieved_at.isoformat() if source.retrieved_at else None
        return SourceLink(title=source.title, url=source.url, verified_on=verified)

    # --- database ----------------------------------------------------------------------

    @property
    def db_enabled(self) -> bool:
        """Vero se c'e' un database configurato o una factory iniettata."""
        return self._session_factory is not None or bool(self.settings.database_url)

    @property
    def repo(self) -> Any:
        """Modulo delle funzioni di accesso (``onevisit_db.repo`` o un finto nei test)."""
        if self._repo is None:
            from onevisit_db import repo

            self._repo = repo
        return self._repo

    @contextmanager
    def db(self) -> Iterator[Any]:
        """Sessione con commit alla fine e rollback in caso di errore."""
        if self._session_factory is None:
            from onevisit_db.engine import create_db_engine, create_session_factory

            engine = create_db_engine(self.settings.database_url)
            self._session_factory = create_session_factory(engine)
        session = self._session_factory()
        try:
            yield session
            session.commit()
        except BaseException:
            session.rollback()
            raise
        finally:
            session.close()

    def cipher(self) -> ContactCipher:
        """Cifratura dei contatti (solleva un errore della libreria se mancano le chiavi)."""
        return ContactCipher(self.settings.encryption_key, self.settings.hmac_key)
