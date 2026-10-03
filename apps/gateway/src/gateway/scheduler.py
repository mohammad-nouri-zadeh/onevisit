"""Ciclo di invio delle notifiche nel processo del gateway (storie C8, C9, versione ridotta).

Per l'hackathon un semplice ciclo asyncio sostituisce Procrastinate: ogni N secondi
legge ``core.notifications`` in scadenza e chiama :func:`dispatch_due`. Lo stato vive
in Postgres, quindi dopo un riavvio il ciclo riprende da dove era rimasto.
Una volta al giorno (e al primo giro) esegue anche ``retention_purge``: cancella i
contatti scaduti con appuntamenti e notifiche (C9).
"""

import asyncio
import logging
import time
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from sqlalchemy.exc import SQLAlchemyError

from gateway.deps import GatewayDeps
from gateway.dispatcher import DispatchContext, dispatch_due
from onevisit_channels import ChannelError

logger = logging.getLogger(__name__)


async def run_once(deps: GatewayDeps, *, now: datetime | None = None) -> None:
    """Un giro del ciclo: invia le notifiche scadute."""
    if deps.store_factory is None or deps.cipher is None:
        return
    ctx = DispatchContext(
        senders=deps.senders,
        renderer=deps.renderer,
        links=deps.links,
        cipher=deps.cipher,
        retry=deps.retry,
        timezone=ZoneInfo(deps.settings.timezone),
    )
    with deps.store_factory() as store:
        await dispatch_due(
            store,
            now=now or datetime.now(UTC),
            ctx=ctx,
            limit=deps.settings.dispatch_batch_size,
        )


def purge_once(deps: GatewayDeps, *, now: datetime | None = None) -> int:
    """Conservazione (C9): cancella i contatti scaduti; restituisce quanti."""
    if deps.store_factory is None:
        return 0
    with deps.store_factory() as store:
        deleted = store.purge_expired(now=now or datetime.now(UTC))
        store.commit()
    if deleted:
        logger.info("conservazione: %d contatti scaduti cancellati", deleted)
    return deleted


async def run_loop(deps: GatewayDeps, stop: asyncio.Event) -> None:
    """Ripete :func:`run_once` finche' ``stop`` non viene impostato; purga una volta al giorno."""
    interval = deps.settings.dispatch_interval
    last_purge: float | None = None
    while not stop.is_set():
        now_mono = time.monotonic()
        if last_purge is None or now_mono - last_purge >= deps.settings.retention_purge_interval_s:
            try:
                purge_once(deps)
                last_purge = now_mono
            except (SQLAlchemyError, ImportError) as exc:
                logger.warning("conservazione: purga fallita (%s)", type(exc).__name__)
        try:
            await run_once(deps)
        except (SQLAlchemyError, ChannelError, ImportError) as exc:
            logger.warning("ciclo di invio: giro fallito (%s)", type(exc).__name__)
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval)
        except TimeoutError:
            continue
