# Convenzioni del codice

L'obiettivo è un codice che una persona del Comune, o un fornitore che arriverà dopo, possa leggere e modificare senza dover chiedere a chi l'ha scritto.

## Lingua

| Elemento | Lingua |
|---|---|
| Identificatori (variabili, funzioni, classi, tabelle, colonne) | Inglese |
| Docstring e commenti | Italiano |
| Documentazione in `docs/` | Italiano |
| `README.md` | Inglese, con un riassunto in italiano |
| Testi rivolti al cittadino | Italiano e inglese, nei template |

## Struttura

- Un modulo ha una sola responsabilità. Se supera le 300 righe, va diviso.
- Una funzione fa una cosa. Se supera le 40 righe, o ha più di tre livelli di annidamento, va spezzata.
- Classi solo quando servono stato o polimorfismo. Altrimenti funzioni.
- Le applicazioni in `apps/` sono sottili: rotte, template, configurazione. La logica sta in `libs/`.
- Le librerie non leggono l'ambiente e non conoscono FastAPI. Ricevono ciò che serve come parametri.
- Le dipendenze esterne (Claude, fornitore SMS, SMTP, orologio) entrano come parametri o come `typing.Protocol`, così nei test si sostituiscono con versioni finte.

## Tipi e dati

- mypy in modalità strict. Ogni funzione ha i tipi di parametri e ritorno.
- Pydantic per i dati che attraversano un confine: richieste HTTP, file YAML, strumenti dell'agente, messaggi tra servizi.
- `@dataclass(frozen=True)` per i valori interni immutabili.
- Niente `dict[str, Any]` che girano per il codice: si definisce un modello.
- Date sempre con fuso orario (`zoneinfo.ZoneInfo("Europe/Rome")`). Le date senza fuso sono un errore.

## Database

- SQLAlchemy 2 in stile tipizzato (`Mapped[...]`, `mapped_column`).
- Ogni tabella appartiene esplicitamente a uno schema: `pii`, `core` o `analytics`.
- Ogni migrazione che crea una tabella concede, nella stessa migrazione, i permessi ai ruoli che la usano, e solo a quelli.
- Le migrazioni non si modificano dopo l'applicazione: se ne crea una nuova.
- Accesso sincrono con `Session`. Gli endpoint FastAPI che usano il database sono `def`, e FastAPI li esegue in un thread pool. Unica eccezione: lo streaming della chat (`async def` con `AsyncAnthropic`), che delega il database a `run_in_threadpool`.

## Errori e log

- Ogni libreria definisce le proprie eccezioni (per esempio `CatalogError` o `ChannelSendError`), che derivano da una base comune della libreria.
- Mai `except Exception` senza rilanciare o registrare con un motivo chiaro.
- Log con `logging.getLogger(__name__)`. Nei log compaiono solo identificativi opachi (id del caso, id della notifica), mai email, telefono, testo dei messaggi o risposte del cittadino.
- I messaggi delle eccezioni seguono la stessa regola: possono finire nei log.

## Configurazione

- Ogni applicazione ha la sua classe `Settings` (pydantic-settings) con prefisso `ONEVISIT_`.
- Nessun numero magico: soglie, tempi e limiti stanno in `Settings` e in `.env.example`, ciascuno con un commento.

## Interfaccia web

- Jinja2 con autoescape attivo; HTMX per l'interattività; nessun framework JavaScript.
- HTML semantico:
  - ogni campo ha la sua `label`;
  - i messaggi della chat stanno in una regione `aria-live="polite"`;
  - contrasto AA;
  - tutto si usa da tastiera.
- Ogni grafico del pannello ha una tabella equivalente.
- I testi stanno nei template o nei file di messaggi, in italiano e inglese. Mai stringhe rivolte all'utente dentro il codice Python.

## Documentazione nel codice

- Ogni modulo comincia con un docstring che dice cosa contiene e quale storia del backlog implementa.
- Ogni funzione e classe pubblica ha un docstring che spiega cosa fa e, se non è ovvio, perché.
- I commenti spiegano il perché, non il cosa.
- Ogni applicazione ha un breve `README.md` con: cosa fa, come si avvia, variabili d'ambiente usate.

## Test

- Nomi che descrivono il comportamento: `test_reminder_is_not_sent_after_consent_revoked`.
- Struttura in tre blocchi separati da una riga vuota: preparazione, azione, verifica.
- Un comportamento per test.
- I test stanno accanto al codice: `apps/<app>/tests/`, `libs/<lib>/tests/`. I test end-to-end stanno in `e2e/`.
- Dettagli in `docs/testing-strategy.md`.

## Git

- Una storia per commit, in formato Conventional Commits con l'identificativo della storia:
  - `feat(B1): riconoscimento del servizio dalla descrizione libera`
  - `fix(C6): normalizzazione dei numeri senza prefisso internazionale`
  - `docs(A3): ADR sul catalogo come fonte dei requisiti`
- Rami nel formato `story/B1-descrizione-breve`.
- Nessun segreto nel repository: la CI lo controlla con gitleaks.
