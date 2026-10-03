# Privacy e protezione dei dati

*Storia A4. Documento preliminare per il confronto con il DPO del Comune di Milano: non è una DPIA completa. Modello dei dati: [data-model.md](data-model.md). Confini di fiducia: [architecture.md](architecture.md#confini-di-fiducia).*

## Il principio

OneVisit lavora sui **fatti della situazione**, non sui dati di identità. L'assistente non chiede mai nome, codice fiscale, indirizzo, foto di documenti, credenziali né numero di prenotazione; non prenota al posto del cittadino ([ADR 0002](adr/0002-nessuna-prenotazione-dal-bot.md)).

**L'unica eccezione è il contatto (email o telefono), ed è una scelta dichiarata.** È facoltativo, viene chiesto solo dopo la prenotazione, per finalità separate (promemoria, domanda sull'esito, avviso di correzione), e il servizio funziona per intero anche senza: chi non lascia un contatto riceve i promemoria come evento di calendario (`.ics`).

## Dati trattati

| Dato | Dove sta | Chi lo vede | Per quanto |
|---|---|---|---|
| Descrizione della situazione | Nella sessione; al modello arriva dopo `redact()` | Il modello | Non viene salvata come testo, solo come campi strutturati |
| Email e telefono (facoltativi) | `pii.contacts`, cifrati; al momento dell'invio anche presso il fornitore di SMS o email | Solo il servizio di notifica | Fino alla fine del follow-up (`expires_at`) |
| Lingua preferita | Nella sessione; in `pii.contacts` se c'è un contatto; nelle metriche solo come aggregato | Servizio di notifica; il pannello solo in forma aggregata | Come il dato a cui è associata |
| Data e sede dell'appuntamento | Sul dispositivo (`.ics`); in `pii.appointments` se il cittadino sceglie i promemoria; in `core.cases` solo la settimana | Il cittadino e il servizio di notifica | Fino alla fine del follow-up |
| Documenti | Mai caricati | Nessuno | — |
| Esiti e suggerimenti | `core.cases` (campi strutturati); suggerimenti riassunti e generalizzati | Pipeline di analisi | Pseudonimizzati finché esiste il contatto, poi anonimi |
| Segnalazioni (lacune) | `core.gaps`, `core.interventions` | Uffici sopra soglia; redazione anche sotto soglia, senza sede né date | Per tutta la vita del servizio |
| Credenziali e prenotazione | Sistema ufficiale del Comune | Il Comune, come oggi | Fuori dal perimetro di OneVisit |

## Cosa non viene mai salvato

- **Il testo libero del cittadino.** Le conversazioni restano in memoria durante la sessione; Claude ne estrae campi strutturati (servizio, variante, risposte come id di opzione, esito, causa) e il testo viene scartato. Lo stesso vale per i suggerimenti dopo l'appuntamento: si salva solo una sintesi generalizzata senza dati personali.
- Documenti, foto, nomi, codici fiscali, indirizzi, credenziali, numeri di prenotazione.
- Il testo delle notifiche: `core.notifications` contiene solo tipo, canale, scadenza e stato.
- Dati personali nei log: ogni messaggio passa da `PiiLogFilter`, che applica `redact()`; eccezioni e messaggi di errore contengono solo identificativi opachi.

## Pipeline privacy (C9)

1. **Regex**, sempre: email, telefoni, codici fiscali, IBAN e numeri di documento diventano `[EMAIL]`, `[TELEFONO]`, `[CODICE_FISCALE]`, `[IBAN]`, `[DOCUMENTO]` prima che il testo arrivi al modello o ai log.
2. **Claude Haiku** (`claude-haiku-4-5-20251001`), sugli esiti: estrae `missing_requirement`, `probable_cause`, `tone` e un suggerimento generalizzato; ciò che resta di identificante viene tolto.
3. **Contatti cifrati** con AES-256-GCM (`ContactCipher`), con un'impronta HMAC-SHA256 per trovare duplicati senza decifrare. Le chiavi stanno in `.env` (mai nel repository).

## La soglia k = 5

`k_threshold` è un parametro documentato in `analytics.config` (default 5, variabile `ONEVISIT_K_THRESHOLD`). Ogni vista di `analytics` nasconde le celle con meno di k casi **dentro la vista**, così il pannello non può aggirarla. Le segnalazioni agli uffici partono solo quando un gruppo supera la soglia (`ONEVISIT_GAP_THRESHOLD_CASES`=5 in `ONEVISIT_GAP_THRESHOLD_WEEKS`=4 settimane). Sotto soglia la redazione vede il gruppo, ma senza sede né date dei singoli casi, e l'ufficio che gestisce l'agenda non lo vede.

Il motivo: una segnalazione singola, anche senza nome, può essere ricondotta alla persona da chi gestisce l'agenda.

## Fornitori terzi (responsabili del trattamento)

| Fornitore | Cosa riceve | Note e verifiche necessarie |
|---|---|---|
| **Anthropic** (API di Claude) | Testo del cittadino già redatto; catalogo; risultati degli strumenti; esiti strutturati | Accordo di trattamento (DPA); verifica dei termini su conservazione, uso per l'addestramento (per l'API commerciale non previsto di default, da confermare per iscritto), localizzazione e trasferimenti extra-UE |
| **Fornitore SMS** (Twilio, account di prova, nell'hackathon) | Numero di telefono, testo minimo (giorni mancanti + link) | In produzione il Comune sceglie il fornitore, preferibilmente con trattamento nell'UE. Da indicare nell'informativa |
| **Fornitore email** (Mailpit locale nell'hackathon; SMTP istituzionale in produzione) | Indirizzo email, oggetto e testo minimi | In demo nessuna email esce dalla macchina |

## Consenso, base giuridica, diritti

- Consenso separato per ogni finalità (`consents` in `pii.contacts`), revocabile da ogni messaggio con un link o rispondendo STOP; la revoca annulla le notifiche programmate.
- Cancellazione su richiesta (`delete_contact`): elimina contatto e appuntamenti e toglie il collegamento dai casi.
- Nessuna decisione automatizzata con effetti sulla persona (art. 22 GDPR): l'assistente non dichiara mai i documenti "idonei", "in regola" o "garantiti"; decide l'operatore allo sportello.
- Trasparenza sull'IA (art. 50 AI Act): l'informativa breve, in italiano e inglese (`libs/onevisit_channels/src/onevisit_channels/messages/informativa.it.md` e `.en.md`), dice esplicitamente che si sta parlando con un'intelligenza artificiale.

## Valutazione d'impatto preliminare

| Rischio | Probabilità | Gravità | Misure | Rischio residuo |
|---|---|---|---|---|
| Il cittadino scrive dati personali nella chat | Alta | Media | Redazione prima del modello e dei log; testo mai salvato; l'assistente non li chiede | Basso |
| Notifica letta da altri sullo schermo bloccato | Media | Media | Testo senza nome della pratica; dettagli solo dietro link firmato e a scadenza ([ADR 0006](adr/0006-notifiche-minime.md)) | Basso |
| Reidentificazione da segnalazioni o metriche | Media | Alta | Soglia k=5 nelle viste; date accorpate alla settimana; sotto soglia niente sede né date; collegamento con il contatto cancellato a fine follow-up | Medio-basso |
| Accesso del pannello ai dati personali | Bassa | Alta | Ruolo `app_dashboard` senza permessi su `pii.*` e `core.cases` (verificato da test); registro accessi | Basso |
| Lingua o categoria come indizio di origine | Media | Media | Solo aggregati sopra soglia; mai decisioni sulla singola persona | Basso |
| Fiducia eccessiva nell'assistente | Media | Media | Fonte e data per ogni requisito; nessuna garanzia di idoneità; "non lo so" con link ufficiale | Medio-basso |
| Pannello usato per valutare i dipendenti | Bassa | Alta | Dati per procedura e sede, mai per persona; `approved_by` è un ruolo, non un nome | Basso |
| Trasferimento extra-UE (modello, SMS) | Alta | Media | DPA, valutazione dei trasferimenti; fornitore SMS europeo in produzione | Da valutare con il DPO |

In produzione, con un database che collega contatti ed esiti, una **DPIA completa** va messa in conto insieme al DPO.

## Scadenze (retention)

| Dato | Scadenza | Stato nell'hackathon |
|---|---|---|
| `pii.contacts`, `pii.appointments` | Fine del ciclo di follow-up (`expires_at`) | Cancellazione manuale (B9); automatica rimandata |
| `core.cases` | Collegamento `contact_ref` azzerato alla cancellazione del contatto; date da accorpare al mese | Accorpamento rimandato |
| `core.notifications` | Fine del follow-up | Annullate alla revoca |
| `core.gaps`, `core.interventions`, viste | Vita del servizio | — |
| `core.access_log` | Da definire con il DPO | — |
| Sessione della chat | Fine della sessione (solo in memoria) | Attivo |

## Domande aperte per il DPO

1. Base giuridica: consenso o interesse pubblico (art. 6.1.e) per promemoria e follow-up? Il consenso di un ente pubblico ha limiti propri.
2. Il contatto facoltativo è compatibile con il vincolo "niente dati personali" del brief se dichiarato e separato per finalità?
3. Per quanto tempo conservare `core.access_log` e i casi anonimi?
4. L'aggregazione per settimana e la soglia k=5 bastano per considerare anonimi i casi dopo la cancellazione del contatto, o servono il mese e k più alto?
5. Il trasferimento verso l'API di Claude richiede clausole aggiuntive? Quali termini sulla conservazione dei dati vanno firmati?
6. Il fornitore SMS può essere extra-UE in una fase pilota?
7. App IO come canale: è accettabile usare il codice fiscale, che oggi OneVisit evita?
8. Serve una DPIA completa già per una sperimentazione su un solo servizio e una sola sede?

## Dati di prova

Tutti i dati della demo e dei test sono sintetici e marcati `synthetic = true`: email `@example.org`, numeri `+39 333 000 0000`, il codice fiscale di esempio dei manuali `RSSMRA80A01F205X`. Nessun dato reale in codice, dati, schermate o video.
