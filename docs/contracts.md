# Contratti tra librerie e applicazioni

Questo file fissa le interfacce pubbliche tra i pacchetti del kit, così più persone (o più sessioni di Claude) lavorano in parallelo senza rompersi a vicenda. **Cambiare una firma o una colonna qui elencata richiede di aggiornare questo file e il log di `TEAM.md` nello stesso push.**

Regole comuni:

- Le librerie (`libs/`) non leggono variabili d'ambiente e non conoscono FastAPI: ricevono configurazione, client e percorsi come parametri.
- Modelli Pydantic v2 per i dati che attraversano un confine; `typing.Protocol` per le dipendenze esterne (Claude, SMTP, SMS, orologio).
- Nessun dato personale in log, eccezioni o messaggi di errore: solo identificativi opachi.
- Testi rivolti al cittadino in italiano e inglese, nei template o nei file di messaggi.

## 1. `onevisit_knowledge`: catalogo e fonti (A1, A2, C4)

Legge **i file del livello dati del team, senza copiarli** (ADR 0007):

| File | Contenuto |
|---|---|
| `data/services/*.json` | Un servizio per file: `id`, `title{it,en}`, `ente`, `source_ids`, `deciding_questions[{id, ask_it, ask_en, options[], kind?}]`, `steps[{order, ente, text_it, source_id, status}]`, `requirements[{id, text_it, text_en?, when{question_id: [opzioni]}, source_id, quote, verified_at, status, lead_time_days?}]`, `unknowns_it[]` |
| `data/sources.csv` | `id,title,url,publisher,kind,snapshot,retrieved_at,status,notes` |
| `data/pages/<source_id>.md` | Testo salvato delle pagine ufficiali (le citazioni `quote` devono comparire qui alla lettera) |
| `data/offices.json` | Sedi anagrafiche dal dataset `ds549` |
| `data/enti.json` | Enti coinvolti |
| `data/context/*.csv` | Statistiche del Comune per il pannello |

```python
from onevisit_knowledge import (
    Catalog, load_catalog, check_catalog, ApprovedCorrection,
    Service, ServiceSummary, DecidingQuestion, Step, ChecklistItem, Checklist,
    Source, Office, Ente, KnowledgeError,
)

catalog = load_catalog(data_dir: Path, *, include_drafts: bool = False,
                       overlays: Sequence[ApprovedCorrection] = ()) -> Catalog

catalog.services() -> list[ServiceSummary]          # id, title_it, title_en, verified_requirements, total_requirements
catalog.service(service_id: str) -> Service | None  # id, title_it, title_en, ente, source_ids, deciding_questions,
                                                    # steps (solo verificati, salvo include_drafts), unknowns_it
catalog.checklist(service_id: str, answers: Mapping[str, str]) -> Checklist
#   Checklist: service_id, items: list[ChecklistItem], still_to_ask: list[str],
#              not_yet_verified: list[str], sources: list[Source]
#   ChecklistItem: id, text_it, text_en | None, source_id, quote | None, verified_at: date | None,
#                  lead_time_days: int | None, origin: Literal["source", "approved_correction"]
catalog.source(source_id: str) -> Source | None     # id, title, url, publisher, kind, retrieved_at: date | None, status
catalog.source_ids() -> frozenset[str]              # comprende "correzione-approvata" se ci sono overlay
catalog.offices(*, area: str | None = None, municipio: int | None = None,
                lat: float | None = None, lon: float | None = None, limit: int = 3) -> list[Office]
catalog.office(office_id: str) -> Office | None
catalog.enti() -> list[Ente]
catalog.context_tables() -> dict[str, list[dict[str, str]]]
catalog.is_stale(source_id: str, *, today: date, max_days: int) -> bool

check_catalog(data_dir: Path) -> list[str]          # errori leggibili; lista vuota = catalogo valido
```

Regole: solo i requisiti con `status == "verified"` arrivano al cittadino (salvo `include_drafts=True`, solo sviluppo). Un requisito il cui `when` dipende da una domanda senza risposta non compare ed entra in `still_to_ask`. Un `ApprovedCorrection(id, service_id, requirement_id, text_it, text_en, approved_at, when={})` approvato nel pannello (B11) compare nella checklist con `origin="approved_correction"` e `source_id="correzione-approvata"`.

## 2. `onevisit_privacy`: dati personali (C9, C2)

```python
from onevisit_privacy import redact, contains_pii, Redaction, ContactCipher, PiiLogFilter, \
    StructuredFeedback, structure_feedback, Cause, CAUSES

redact(text: str) -> Redaction            # Redaction.text con segnaposto [EMAIL] [TELEFONO] [CODICE_FISCALE] [IBAN] [DOCUMENTO]; .found: list[str] categorie
contains_pii(text: str) -> bool
ContactCipher(encryption_key_b64: str, hmac_key_b64: str)
    .encrypt(value: str) -> bytes          # AES-256-GCM, nonce in testa
    .decrypt(token: bytes) -> str
    .digest(value: str) -> str             # HMAC-SHA256 esadecimale del valore normalizzato (minuscolo, senza spazi)
PiiLogFilter()                            # logging.Filter che passa ogni messaggio da redact()
structure_feedback(text: str, *, client: ClaudeClient | None, model: str) -> StructuredFeedback
#   passo 1 regex sempre; passo 2 Claude (Haiku) se client non è None.
#   StructuredFeedback: missing_requirement: str | None, probable_cause: Cause | None,
#                       tone: Literal["neutro", "frustrato", "positivo"], suggestion: str | None (generalizzato)
```

`Cause` (sei cause del concept): `pagina-incompleta`, `procedura-non-aggiornata`, `procedura-mancante`, `ente-o-ufficio-sbagliato`, `pagina-chiara-non-seguita`, `richiesta-non-prevista`.

## 3. `onevisit_agent`: l'agente (C3, B1–B4, C13)

```python
from onevisit_agent import Agent, AgentConfig, Capabilities, SessionState, CaseState, \
    AppointmentInfo, TurnResult, AgentEvent, ClaudeClient, AnthropicClaudeClient, validate_reply
from onevisit_agent.testing import FakeClaudeClient

client = AnthropicClaudeClient(api_key: str, *, timeout_s: float = 30, max_retries: int = 2)
agent = Agent(client=client, catalog=catalog, config=AgentConfig(
    model_conversation="claude-sonnet-5-5", model_fast="claude-haiku-4-5-20251001",
    official_fallback_url="https://www.comune.milano.it/servizi", stale_after_days=30, today=date))
result: TurnResult = agent.run_turn(state: SessionState, message: str, capabilities: Capabilities)
```

- `SessionState` (Pydantic, serializzabile): `language: str = "it"`, `history: list[dict]` (messaggi per l'API, solo in memoria), `case: CaseState`.
- `CaseState`: `service_id`, `variant`, `answers: dict[str, str]` (solo id di opzione), `deadline_days: int | None`, `category: Literal["italiana","ue","extra-ue"] | None`, `confirmed: bool`, `appointment: AppointmentInfo | None` (`date`, `time`, `office_id`), `missing_procedure: bool`. **Nessun testo libero.**
- `Capabilities`: `channel: Literal["web","email","sms"]`, `buttons: bool`, `max_chars: int | None`, `browser_language: str | None`.
- `TurnResult`: `messages: list[str]` (Markdown con citazioni `[fonte: <source_id>]`), `quick_replies: list[str]`, `language: str` (ISO 639-1), `state: SessionState`, `blocked: bool`, `events: list[AgentEvent]`.
- `AgentEvent`: `kind: Literal["case_identified","case_confirmed","appointment_recorded","contact_requested","outcome_recorded","missing_procedure"]`, `data: dict[str, str | int | bool | None]` (solo campi strutturati).
- Strumenti per Claude: `identify_case`, `get_procedure`, `get_office`, `build_checklist`, `record_appointment`, `request_contact`, `record_outcome`, `report_missing_procedure`.
- `validate_reply(text: str, *, known_source_ids: frozenset[str], used_facts: bool) -> list[str]` restituisce i motivi del blocco: citazione con `source_id` inesistente, parole vietate (it/en/es/fr: "idoneo", "in regola", "garantito", "eligible", "guaranteed", "elegible", "garantizado", "éligible", "garanti", ...), nessuna citazione quando il turno ha usato fatti del catalogo. Una rigenerazione, poi messaggio di cortesia con il link ufficiale.
- Prompt di sistema versionato in `libs/onevisit_agent/src/onevisit_agent/prompts/system.md`. Catalogo e strumenti con prompt caching.

## 4. `onevisit_db`: schemi, tabelle, ruoli (C2, C11)

Migrazione `0002` sopra `0001`. Tutti gli id sono `uuid` casuali. Date con fuso (`timestamptz`).

| Tabella | Colonne principali |
|---|---|
| `core.cases` | `id`, `created_at`, `service_id`, `variant`, `category`, `language`, `office_id`, `appointment_week` (date, lunedì), `deadline_days`, `outcome` (`ok`/`missing`/`other`/null), `cause`, `missing_requirement_id`, `closed_in_time`, `rating`, `outcome_at`, `contact_ref` (uuid null, nessuna FK verso `pii`), `synthetic` (bool) |
| `core.case_answers` | `case_id` FK, `question_id`, `answer` (id di opzione) |
| `core.gaps` | `id`, `service_id`, `cause`, `source_id`, `title`, `summary`, `examples` (jsonb, generalizzati), `status` (`nuova`/`in-revisione`/`corretta`/`archiviata`), `recipient` (`redazione`/`ufficio`/`ente-nazionale`/`assistente`), `owner_ente`, `requirement_id`, `draft_it`, `draft_easy_it`, `draft_en`, `case_count`, `first_seen`, `last_seen`, `archived_reason`, `synthetic`, `created_at`, `updated_at` |
| `core.gap_cases` | `gap_id`, `case_id` |
| `core.interventions` | `id`, `gap_id`, `service_id`, `requirement_id`, `text_it`, `text_easy_it`, `text_en`, `approved_by` (ruolo demo, mai un nome), `approved_at` |
| `core.notifications` | `id`, `case_id`, `kind` (`reminder`/`followup`/`followup_nudge`/`correction_notice`/`revocation_confirm`/`email_confirm`), `channel` (`email`/`sms`), `due_at`, `status` (`scheduled`/`sent`/`failed`/`cancelled`), `attempts`, `sent_at`. **Nessun testo.** |
| `core.access_log` | `id`, `at`, `role`, `action`, `object_id` |
| `pii.contacts` | `id`, `email_enc`, `email_hmac`, `phone_enc`, `phone_hmac`, `preferred_channel`, `fallback_channel`, `language`, `consents` (jsonb `{reminder, followup, correction}` → istante ISO o null), `confirmed_at`, `expires_at`, `created_at` |
| `pii.appointments` | `id`, `contact_id` FK, `case_id`, `starts_at`, `office_id` |
| `analytics.config` | `key`, `value` (`k_threshold`=5, `cost_per_slot_eur`, `window_weeks`=4) |

Viste in `analytics` (filtro k dentro la vista): `first_visit_rate` (servizio, categoria, lingua → casi, chiusi al primo appuntamento, tasso), `weekly_first_visit` (servizio, settimana), `gaps_by_cause`, `intervention_effect` (prima/dopo, null sotto soglia), `avoided_visits` (stima con costo per slot).

Ruoli: `app_assistant` scrive `core` e `pii` e legge `core.interventions`; `app_notifier` legge `pii` e `core.cases`, aggiorna `core.notifications`; `app_analysis` legge `core.cases`/`core.case_answers`, scrive `core.gaps`/`core.gap_cases`; `app_dashboard` legge solo `analytics.*`, `core.gaps`, `core.interventions`, aggiorna `core.gaps`, inserisce in `core.interventions` e `core.access_log`. **`app_dashboard` riceve un errore su `pii.*` e su `core.cases`.**

Funzioni (`onevisit_db.repo`, sessione SQLAlchemy sincrona passata dal chiamante):

```python
create_case(s, *, service_id, variant, category, language, office_id, appointment_week, deadline_days,
            answers: Mapping[str, str], synthetic=False) -> UUID
update_case(s, case_id, **fields) -> None
record_outcome(s, case_id, *, outcome, cause, missing_requirement_id, closed_in_time, rating) -> None
create_contact(s, *, email_enc, email_hmac, phone_enc, phone_hmac, preferred_channel, fallback_channel,
               language, consents: Mapping[str, str | None], expires_at) -> UUID
confirm_contact(s, contact_id) -> None
link_contact(s, case_id, contact_id) -> None
create_appointment(s, *, contact_id, case_id, starts_at, office_id) -> UUID
revoke_consents(s, contact_id) -> None          # azzera i consensi e annulla le notifiche programmate
delete_contact(s, contact_id) -> None           # cancella contatto e appuntamenti, toglie contact_ref dai casi
schedule_notification(s, *, case_id, kind, channel, due_at) -> UUID
due_notifications(s, *, now, limit=50) -> list[NotificationRow]
mark_notification(s, notification_id, *, status) -> None
approved_corrections(s) -> list[ApprovedCorrectionRow]
list_gaps(s, *, cause=None, service_id=None, status=None) -> list[GapRow]
get_gap(s, gap_id) -> GapRow | None
approve_gap(s, gap_id, *, approved_by, text_it, text_easy_it, text_en) -> UUID
archive_gap(s, gap_id, *, reason) -> None
log_access(s, *, role, action, object_id) -> None
```

Per i test: `onevisit_db.testing.migrated_database(admin_url: str) -> Iterator[str]` crea un database di test con nome univoco, applica le migrazioni, restituisce la URL e lo elimina alla fine. Fixture pytest `migrated_db_url` nel `conftest.py` di radice (salta se manca `DATABASE_URL_TEST`).

## 5. `onevisit_channels`: canali e messaggi (C5–C7, B5–B9)

```python
from onevisit_channels import (
    InboundMessage,
    OutboundMessage,
    ChannelCapabilities,
    ChannelAdapter,
    SmsProvider,
    FakeSmsProvider,
    TwilioSmsProvider,
    EmailSender,
    SmtpEmailSender,
    FakeEmailSender,
    render_notification,
    parse_sms_reply,
    SmsReply,
    normalize_phone,
    LinkSigner,
    informativa,
)
```

- `render_notification(kind, *, language: str, channel, days_left: int | None, link: str) -> RenderedMessage(subject | None, text, html | None)`. Due soli segnaposto: giorni mancanti e link. **Mai il nome del servizio.** Modelli in `templates/sms/` e `templates/email/`, italiano e inglese, SMS entro due segmenti.
- `parse_sms_reply(text) -> SmsReply(kind: Literal["1","2","3","STOP","AIUTO","other"])`, tollerante a spazi e maiuscole.
- `normalize_phone(raw, default_region="IT") -> str` (E.164) o `ValueError`.
- `LinkSigner(secret).sign(purpose, case_id, contact_id=None) -> str` / `.verify(token, purpose, max_age_s) -> dict`.
- `informativa(language) -> str` (testo breve; dice che si parla con un'intelligenza artificiale).

## 6. `onevisit_analytics`: lacune, metriche, sintesi (C10, C11, B13, D1)

```python
from onevisit_analytics import classify_outcome, group_into_gaps, draft_correction, weekly_summary, \
    generate_demo_data, DemoSummary
generate_demo_data(session, *, seed: int = 42, weeks: int = 8, today: date) -> DemoSummary  # ~400 casi sintetici
```

## 7. Applicazioni

| App | Porta locale | Ruolo DB | Cosa espone |
|---|---|---|---|
| `assistant_web` | 8000 | `app_assistant` | `/` chat (HTMX), `/chat` (POST), `/appointment`, `/contact`, `/c/{token}` checklist, `/o/{token}` esito, `/consents/{token}`, `/case.ics`, `/health` |
| `dashboard` | 8001 | `app_dashboard` | `/` panoramica, `/gaps`, `/gaps/{id}`, `/interventions`, `/summary`, `/context`, `/settings`, `/health` |
| `gateway` | 8002 | `app_assistant` | `/sms/inbound` (webhook firmato), `/r/{token}` link di risposta, `/demo/phone` (SMS finti), ciclo di invio delle notifiche, `/health` |

Variabili d'ambiente: quelle di `.env.example` (prefisso `ONEVISIT_`). In aggiunta: `ONEVISIT_DATA_DIR` (default `/app/data`), `ONEVISIT_ASSISTANT_BASE_URL`, `ONEVISIT_INCLUDE_DRAFTS` (solo sviluppo).

## 8. Modifiche dalla revisione privacy e correttezza (3 ottobre 2026, pomeriggio)

Aggiunte compatibili; nessuna firma esistente cambia.

```python
# onevisit_db.repo
MIN_K_THRESHOLD = 5                                  # set_config("k_threshold", <5) -> InvalidFieldError
def revoke_consents_by_phone_digest(s, phone_hmac: str) -> list[UUID]   # SMS STOP: tutti i contatti di quel numero
# record_outcome(...) ora annulla anche le notifiche "followup" e "followup_nudge" ancora programmate del caso.
# delete_contact(...) (e quindi purge_expired) CANCELLA le notifiche dei casi collegati:
#   due_at/sent_at derivano dal giorno esatto dell'appuntamento e non devono restare fuori da pii.
# Migrazione 0003: CHECK su analytics.config, k_threshold >= 5.

# onevisit_channels
DEV_LINK_SIGNING_KEY: str                            # pubblica, valida solo con environment == "development"
def resolve_link_signing_key(configured: str, *, environment: str) -> str   # LinkError fuori sviluppo se vuota
#   assistant_web e gateway usano entrambe questa funzione: stessi link validi nelle due app.

# onevisit_privacy
class ClaudeUnavailableError(PrivacyError)           # AnthropicFeedbackClient avvolge anthropic.APIError;
                                                     # structure_feedback ricade sulle regole.
# onevisit_analytics: AnthropicTextClient avvolge anthropic.APIError in ClaudeOutputError;
#   weekly_summary ricade sul modello di testo.

# onevisit_knowledge: un ApprovedCorrection con when vuoto eredita il when del requisito che sostituisce.
# onevisit_agent: get_procedure e' in FACT_TOOLS (has_facts = ci sono passi verificati);
#   il validatore copre anche portoghese e arabo.
```

Applicazioni:

- gateway: `NotifierStore` ha `revoke_consents_by_phone(digest)` e `purge_expired(now=) -> int`;
  il ciclo esegue `retention_purge` al primo giro e poi ogni `ONEVISIT_RETENTION_PURGE_INTERVAL_S`
  (default 86400). STOP revoca tutti i contatti del numero; 1/2/3 va al contatto piu' recente.
- assistant_web: `/contact` senza alcun consenso non salva nulla; un secondo invio nella stessa
  sessione cancella il contatto precedente; l'email di riserva (entrambi, SMS principale) riceve
  la conferma. Gli eventi `outcome_recorded` e `missing_procedure` scrivono su `core.cases`
  (servizio `non-in-catalogo`, causa `procedura-mancante`). I casi nascono con sede e settimana
  se l'appuntamento e' gia' noto.
- dashboard: `k_threshold` minimo 5 nel modulo; il dettaglio di una lacuna sotto soglia arriva
  al browser senza numero, riassunto, esempi e date. Il modulo di approvazione chiede il testo
  del requisito per il cittadino (le bozze per la pagina restano in sola lettura).
