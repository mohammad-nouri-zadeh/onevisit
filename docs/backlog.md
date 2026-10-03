# OneVisit: backlog per l'implementazione

*Questo documento porta dal concept (`onevisit.md`) al codice. Le user story sono divise in cinque epiche: analisi e documentazione, cosa deve fare il sistema, come lo farà, implementazione e consegna, video. I vincoli dell'hackathon citati qui (durata del video, orario di consegna, sezione obbligatoria del README) vanno ricontrollati sulle slide.*

## Scelte di base

### Linguaggio: Python

Il linguaggio è Python, per quattro ragioni:

- **SDK ufficiale di Anthropic per Python** (`anthropic`), con uso di strumenti e prompt caching. Documentazione: https://docs.claude.com/en/api/overview
- **Pydantic** permette di usare gli stessi modelli per validare il catalogo, gli strumenti dell'agente e le API.
- **Ecosistema maturo** per web, database, code di lavoro e trattamento del testo.
- **Pubblica amministrazione**: è un linguaggio diffuso nella PA e facile da mantenere da fornitori diversi.

Nessun componente richiede Windows né software proprietario: tutto gira su Linux, in container. Il codice viene rilasciato con licenza aperta (EUPL-1.2), così il Comune e altre amministrazioni possono riusarlo.

### Stack

| Area | Scelta | Perché |
|---|---|---|
| Runtime e strumenti | Python 3.13; uv per progetto e workspace; ruff; mypy in modalità strict; pytest | Un comando per installare e lanciare tutto |
| Web chat del cittadino | FastAPI, Jinja2, HTMX; risposte in streaming con Server-Sent Events | Pagine generate dal server, poco JavaScript, più facili da rendere accessibili |
| Pannello del Comune | FastAPI, Jinja2, HTMX, Chart.js, come applicazione separata | Il pannello sta fuori dal bot |
| Gateway e scheduler | FastAPI per i webhook; Procrastinate per code e lavori programmati su Postgres | Niente Redis: un database in meno da gestire |
| Agente | SDK `anthropic`, modelli Pydantic | Strumenti tipizzati, output strutturato, prompt caching |
| Modelli | `claude-sonnet-5-5` per conversazione e analisi; `claude-haiku-4-5-20251001` per la rimozione dei dati personali e le classificazioni brevi | Qualità dove serve, costo e latenza bassi dove basta |
| Database | PostgreSQL 17, SQLAlchemy 2, Alembic, psycopg 3 | Schemi e ruoli per separare i dati |
| Connettori | SDK del fornitore SMS (Twilio nell'hackathon), aiosmtplib, `phonenumbers` | Interfaccia unica, fornitore sostituibile |
| Riga di comando | Typer, con i comandi `onevisit ingest`, `catalog-check`, `seed-demo`, `eval` | Gli stessi comandi in locale e in CI |
| Test | pytest, pytest-asyncio, Playwright per Python | Test unitari ed end-to-end |
| Ambiente locale | Docker Compose: Postgres, Mailpit, le tre applicazioni, con il codice montato nei container | Sull'host servono solo Docker e make |
| Produzione | Docker Compose con Caddy, che ottiene i certificati HTTPS in automatico | Un server Linux qualsiasi, nessun servizio proprietario |
| CI | GitHub Actions per la consegna dell'hackathon | La pipeline è fatta di comandi standard, quindi si sposta su GitLab CI o sulla piattaforma del Comune |

### Struttura del repository

```
onevisit/
  pyproject.toml           workspace uv
  apps/
    assistant_web/         web chat del cittadino (FastAPI + HTMX)
    dashboard/             pannello del Comune (FastAPI + HTMX)
    gateway/               webhook SMS, link di risposta, worker Procrastinate
  libs/
    onevisit_agent/        agente Claude: prompt, strumenti, validazione
    onevisit_knowledge/    fonti, catalogo delle procedure, caricamento
    onevisit_db/           modelli SQLAlchemy, migrazioni Alembic, ruoli
    onevisit_channels/     interfaccia, adattatori, modelli dei messaggi
    onevisit_privacy/      rimozione dei dati personali, pseudonimizzazione, scadenze
    onevisit_analytics/    lacune, metriche, confronto prima e dopo
    onevisit_cli/          comandi Typer
  data/
    sources/               pagine ufficiali in Markdown con metadati
    procedures/            catalogo delle procedure in YAML
    eval/                  scenari di valutazione dell'agente
  docs/                    architettura, ADR, privacy, metriche, runbook, video
  docker/                  inizializzazione di Postgres, configurazione di Caddy
  e2e/                     test end-to-end con Playwright
  Dockerfile               un'immagine per tutti i servizi (runtime, test, e2e)
  compose.yaml             stack di base
  compose.override.yaml    aggiunte per lo sviluppo (porte, ricarica, Mailpit, test)
  compose.prod.yaml        aggiunte per la produzione (Caddy, log)
  Makefile                 tutti i comandi, eseguiti nei container
```

### Personas

| Persona | Chi è | Cosa le serve |
|---|---|---|
| Giulia | 24 anni, studentessa arrivata da Palermo, ha perso la carta d'identità | Sapere cosa portare e arrivare pronta |
| Daniel | Ingegnere brasiliano appena assunto a Milano, deve iscriversi all'anagrafe | Capire quali enti, in che ordine, nella sua lingua |
| Marco | Redazione web del Comune | Sapere cosa correggere questa settimana, con il testo già pronto |
| Laura | Responsabile di un ufficio anagrafe | Segnalazioni aggregate sulle sue procedure, senza esserne sommersa |
| Paola | Dirigente dei servizi civici | Poche metriche affidabili e una stima di quanto vale il miglioramento |
| Team | Sviluppatori del tavolo | Fondamenta solide per costruire in fretta senza rompere nulla |

### Formato delle storie

Ogni storia riporta:

- identificativo e titolo;
- priorità MoSCoW (Must, Should, Could);
- stima in story point (scala di Fibonacci);
- rilascio: Hackathon o Dopo;
- dipendenze;
- testo nella forma "Come… voglio… così che…";
- criteri di accettazione;
- note su come realizzarla;
- artefatti prodotti.

### Definition of Ready

Una storia è pronta quando:

- i criteri di accettazione sono verificabili;
- le dipendenze sono chiuse, oppure hanno un sostituto temporaneo (mock);
- è chiaro quali dati personali tocca, o che non ne tocca nessuno;
- si chiude in mezza giornata di lavoro. Altrimenti va spezzata.

### Definition of Done

Una storia è fatta quando:

- il codice è nel ramo principale tramite PR, con CI verde;
- i criteri di accettazione sono verificati, con test automatici dove possibile;
- nessun dato personale finisce nei log (lo verifica C9);
- i testi rivolti al cittadino esistono in italiano e in inglese;
- la documentazione interessata è aggiornata;
- se tocca l'agente, passano gli scenari di valutazione veloci (C13).

---

## Epica A · Analisi e documentazione

### A1 · Inventario delle fonti ufficiali

**Priorità** Must · **Stima** 3 · **Rilascio** Hackathon · **Dipende da** nessuna

**Storia.** Come team, voglio un inventario delle pagine ufficiali che descrivono i due servizi scelti, così che ogni requisito mostrato dall'assistente ha una fonte verificabile.

**Contesto.** I servizi sono due:

- carta d'identità, con tre varianti: rinnovo, smarrimento o furto, minore;
- iscrizione anagrafica di un cittadino extra-UE.

Le fonti sono comune.milano.it e gli enti nazionali coinvolti: Ministero dell'Interno per la carta d'identità, Questura per il permesso di soggiorno, Agenzia delle Entrate per il codice fiscale.

**Criteri di accettazione**

- Per ogni pagina di un servizio, l'inventario riporta URL, ente proprietario, servizio, varianti coperte, data di verifica e lingua.
- Ogni pagina è salvata in `data/sources/` come file Markdown con un'intestazione di metadati: `url`, `ente`, `servizio`, `verified_at`, `content_hash`.
- L'inventario elenca le lacune già evidenti: varianti senza pagina e informazioni in contrasto. Diventano casi di prova per la demo.
- Nessuna pagina proviene da fonti non ufficiali.

**Come.** Il comando `onevisit ingest` scarica le pagine con httpx, le converte da HTML a Markdown con markdownify, calcola l'hash SHA-256 e scrive l'intestazione. Rispetta `robots.txt` e fa al massimo una richiesta al secondo.

**Artefatti.** `docs/sources-inventory.md`, `data/sources/*.md`, comando di ingestione.

### A2 · Catalogo delle procedure

**Priorità** Must · **Stima** 5 · **Rilascio** Hackathon · **Dipende da** A1

**Storia.** Come team, voglio un catalogo strutturato di servizi, varianti, enti, passaggi e requisiti, così che l'assistente ragiona su dati verificati invece di ricostruire le regole a ogni conversazione.

**Contesto.** Questa scelta rende affidabile l'agente. Claude decide quale variante si applica e come spiegarla, ma prende i requisiti dal catalogo, che a sua volta punta alle fonti.

**Criteri di accettazione**

- Per ogni servizio esiste un file YAML in `data/procedures/` con:
  - identificativo e nome ufficiale;
  - varianti e domande che le distinguono;
  - enti, in ordine, con il motivo di ciascun passaggio;
  - ufficio comunale;
  - requisiti per variante.
- Ogni requisito ha un nome ufficiale in italiano, una descrizione semplice, i tempi tipici se noti (per esempio per una traduzione) e un `source_id` che rimanda a una pagina di A1.
- Il comando `onevisit catalog-check` fallisce se un requisito non ha fonte, se una fonte non esiste o se una variante non ha requisiti.
- Claude propone il catalogo a partire dalle pagine e una persona del team lo valida riga per riga. La validazione è registrata nel file con `reviewed_by` e `reviewed_at`.

**Come.** I modelli Pydantic in `onevisit_knowledge` sono condivisi da validatore, agente e pannello. Il prompt di estrazione sta in `onevisit_cli/propose_catalog.py`. Nessun file entra nel catalogo senza revisione umana.

**Artefatti.** `data/procedures/carta-identita.yaml`, `data/procedures/iscrizione-anagrafica-extra-ue.yaml`, modelli e validatore.

### A3 · Architettura e decisioni

**Priorità** Must · **Stima** 3 · **Rilascio** Hackathon · **Dipende da** nessuna

**Storia.** Come team, voglio l'architettura e le decisioni principali per iscritto, così che tutti costruiscono la stessa cosa e la giuria capisce le scelte.

**Criteri di accettazione**

- `docs/architecture.md` contiene:
  - i quattro schemi del concept;
  - la struttura del repository;
  - i flussi principali: conversazione, notifica, analisi;
  - i confini di fiducia: cosa vede il modello, cosa vede il pannello, cosa vedono i fornitori di SMS ed email.
- Esiste un ADR breve (contesto, decisione, conseguenze) per ciascuna decisione:
  - Python e componenti aperti;
  - nessuna prenotazione da parte del bot;
  - il catalogo come fonte dei requisiti;
  - specializzazione senza addestramento;
  - canali web, email e SMS dietro un gateway unico;
  - contenuto minimo delle notifiche.
- Ogni ADR ha uno stato (proposta o accettata) e una data.

**Artefatti.** `docs/architecture.md`, `docs/adr/0001-python.md` … `docs/adr/0006-notifiche-minime.md`.

### A4 · Modello dei dati e privacy

**Priorità** Must · **Stima** 5 · **Rilascio** Hackathon · **Dipende da** A3

**Storia.** Come team, voglio il modello dei dati e la mappa dei trattamenti scritti prima del codice, così che la separazione tra contatti, casi e metriche è garantita dallo schema e non dalla buona volontà.

**Criteri di accettazione**

- `docs/data-model.md` contiene il diagramma entità-relazioni in Mermaid con i tre schemi Postgres:
  - `pii`: contatti e appuntamenti;
  - `core`: sessioni, casi, lacune, interventi, notifiche;
  - `analytics`: viste aggregate.
- Per ogni tabella sono indicati campi, chi scrive, chi legge, scadenza e presenza di dati personali.
- `docs/privacy.md` contiene:
  - la tabella dei dati del concept;
  - l'elenco dei fornitori terzi: Anthropic, fornitore SMS, fornitore email;
  - le domande aperte per il DPO;
  - una valutazione d'impatto preliminare.
- L'informativa breve esiste in italiano e in inglese e dice esplicitamente che si sta parlando con un'intelligenza artificiale.
- La soglia minima per mostrare un dato aggregato (k = 5) è un parametro documentato.

**Artefatti.** `docs/data-model.md`, `docs/privacy.md`, `libs/onevisit_channels/messages/informativa.it.md` e `.en.md`.

### A5 · Definizione delle metriche

**Priorità** Should · **Stima** 3 · **Rilascio** Hackathon · **Dipende da** A4

**Storia.** Come Paola, voglio una definizione scritta per ogni numero del pannello, così che posso citarlo senza che qualcuno lo smonti.

**Criteri di accettazione**

- `docs/metrics.md` definisce per ogni metrica formula, tabelle di origine, periodo, soglia di visualizzazione e limiti noti.
- Il costo risparmiato è definito come stima:
  - il costo per slot è un parametro configurabile;
  - una nota avverte che la stima tende a essere troppo alta, perché chi usa l'assistente è probabilmente più attento della media.
- L'effetto di una correzione è la differenza nel tasso di pratiche chiuse al primo appuntamento tra le quattro settimane prima e le quattro dopo. È indicato il numero minimo di casi per mostrarlo.
- Il "tempo utile" è definito come pratica chiusa entro la scadenza dichiarata dal cittadino in B1.

**Artefatti.** `docs/metrics.md`.

### A6 · README e sezione obbligatoria

**Priorità** Must · **Stima** 2 · **Rilascio** Hackathon · **Dipende da** A3

**Storia.** Come membro della giuria, voglio un README che spieghi in pochi minuti cosa fa OneVisit e dove lavora Claude, così che posso valutare "AI at work" senza leggere il codice.

**Criteri di accettazione**

- Il README contiene:
  - il problema e la soluzione in una frase;
  - lo schema 1;
  - l'avvio rapido con un comando;
  - la sezione obbligatoria "Where does Claude work when someone uses this?", con la tabella momento / cosa fa Claude / conferma umana;
  - le scelte sulla privacy e i limiti noti;
  - il link al video.
- L'avvio rapido funziona su una macchina pulita con solo Docker e make installati.
- Il README è in inglese, come il titolo della sezione obbligatoria, con un riassunto in italiano.

**Artefatti.** `README.md`.

---

## Epica B · Cosa deve fare

### B1 · Descrivere la situazione e ottenere il servizio giusto

**Priorità** Must · **Stima** 5 · **Rilascio** Hackathon · **Dipende da** A2, C3

**Storia.** Come Giulia, voglio descrivere la mia situazione con parole mie, così che l'assistente capisce di quale servizio ho bisogno anche se non ne conosco il nome burocratico.

**Criteri di accettazione**

- Dato il messaggio "ho perso la carta d'identità e tra un mese parto", l'assistente riconosce il servizio "carta d'identità" e la variante "smarrimento". Poi chiede solo le domande che distinguono le varianti e a cui il cittadino non ha già risposto.
- Se la situazione è ambigua tra due servizi, l'assistente chiede quale dei due con una sola domanda.
- Se il servizio non è nel catalogo, l'assistente lo dice, rimanda al sito del Comune e registra una lacuna di tipo "procedura mancante".
- L'assistente chiede se c'è una scadenza ("ti serve entro una data?") e la salva come numero di giorni rispetto all'appuntamento, non come data.
- Alla fine della fase mostra un riepilogo del caso, che il cittadino conferma o corregge.
- L'assistente non chiede mai nome, codice fiscale, indirizzo o foto dei documenti. Se il cittadino li scrive comunque, non vengono salvati (C9).

**Come.** Lo strumento `identify_case` restituisce un output strutturato con servizio, variante, risposte e scadenza. Il catalogo del servizio entra nel contesto con prompt caching.

### B2 · La lingua del cittadino

**Priorità** Must · **Stima** 3 · **Rilascio** Hackathon · **Dipende da** C3

**Storia.** Come Daniel, voglio che l'assistente risponda nella lingua in cui scrivo o in quella che chiedo, così che non devo cercare un'impostazione né tradurre da solo.

**Criteri di accettazione**

- Se il primo messaggio è in inglese, la risposta è in inglese.
- Dopo la richiesta "parlami in spagnolo", le risposte successive sono in spagnolo.
- Durante una conversazione in spagnolo, un messaggio completo in italiano fa passare l'assistente all'italiano. Un semplice "ok" non cambia la lingua.
- Il messaggio di benvenuto usa la lingua del browser (intestazione `Accept-Language`), altrimenti l'italiano.
- I termini ufficiali compaiono in italiano accanto alla traduzione, per esempio "permesso di soggiorno (residence permit)".
- La lingua corrente è salvata nella sessione e, se il cittadino lascia un contatto, anche nella tabella contatti. Serve per inviare SMS ed email nella lingua giusta.
- Con una lingua fuori dall'elenco supportato (italiano, inglese e una terza da concordare), l'assistente risponde comunque, avvisa che la traduzione può essere imprecisa e propone l'inglese.

**Come.** Il rilevamento è affidato al modello: ogni turno restituisce un campo `language` con codice ISO 639-1. Gli scenari di valutazione (C13) includono messaggi in almeno quattro lingue.

### B3 · Sapere dove andare

**Priorità** Must · **Stima** 3 · **Rilascio** Hackathon · **Dipende da** B1

**Storia.** Come Daniel, voglio sapere quali enti devo visitare, in che ordine e in quale ufficio del Comune, così che non vado nel posto sbagliato.

**Criteri di accettazione**

- Per un caso confermato, l'assistente mostra la sequenza degli enti (per esempio prima la Questura, poi il Comune) e il motivo di ogni passaggio.
- Per la parte comunale mostra ufficio, indirizzo, orari e link alla pagina ufficiale, con la data di verifica.
- Se la fonte dell'ufficio non è stata verificata da più giorni della soglia (default 30), l'indicazione mostra un avviso.
- Ogni indicazione ha almeno una fonte. Il validatore (C3) blocca le risposte senza fonte.

### B4 · Prenotare e registrare l'appuntamento

**Priorità** Must · **Stima** 2 · **Rilascio** Hackathon · **Dipende da** B3

**Storia.** Come Giulia, voglio sapere come prenotare e poter dire all'assistente quando ho l'appuntamento, così che mi aiuta a prepararmi in tempo.

**Criteri di accettazione**

- L'assistente mostra il link al sistema di prenotazione ufficiale e cosa tenere pronto per prenotare.
- L'assistente non chiede credenziali, codice fiscale né numero di prenotazione.
- Il cittadino può indicare data, ora e sede dell'appuntamento, e l'assistente le conferma.
- Se l'appuntamento è troppo vicino per un requisito che richiede tempo (per esempio una traduzione), l'assistente lo segnala subito.
- Se il cittadino non indica l'appuntamento, l'assistente offre subito la checklist e non programma promemoria.

### B5 · Scegliere come essere ricontattato

**Priorità** Must · **Stima** 5 · **Rilascio** Hackathon · **Dipende da** B4, C2

**Storia.** Come Giulia, voglio scegliere se lasciare un'email, un numero di telefono o entrambi, così che i promemoria mi arrivano dove li leggo davvero.

**Criteri di accettazione**

- La richiesta del contatto arriva dopo la registrazione dell'appuntamento, mai prima.
- Il cittadino ha quattro opzioni:
  - email;
  - numero di telefono, per gli SMS;
  - entrambi, scegliendo il canale principale;
  - nessun contatto, con un evento .ics da scaricare.
- Se ha lasciato entrambi i contatti, il secondo si usa solo quando l'invio sul principale fallisce. L'email viene proposta come principale perché non ha costi per messaggio, ma decide il cittadino.
- I consensi sono tre, separati e non preselezionati:
  - promemoria;
  - domanda dopo l'appuntamento;
  - avviso quando una segnalazione porta a una correzione.
- Prima del salvataggio:
  - l'email viene validata nel formato e confermata con un link; i promemoria si attivano solo dopo la conferma;
  - il numero viene normalizzato in formato E.164 con `phonenumbers`. Nell'hackathon la verifica con codice via SMS è facoltativa, in produzione è obbligatoria.
- L'informativa breve compare prima del salvataggio.

**Come.** Il contatto viene salvato nello schema `pii` (C2). Il caso riceve solo un riferimento opaco al contatto.

### B6 · Rispondere via SMS

**Priorità** Must · **Stima** 3 · **Rilascio** Hackathon · **Dipende da** C5, C6

**Storia.** Come Daniel, voglio rispondere direttamente all'SMS con un numero o una parola, così che non devo aprire il browser per le risposte semplici.

**Criteri di accettazione**

- A un SMS di follow-up il cittadino può rispondere 1, 2 o 3. La risposta viene registrata come se avesse premuto il pulsante corrispondente sul web.
- STOP revoca tutti i consensi.
- AIUTO restituisce un messaggio breve con il link alla web chat e alla gestione dei consensi.
- A qualsiasi altro testo il sistema risponde con un messaggio breve e il link personale alla web chat. Il testo ricevuto non viene salvato.
- Nessun messaggio inviato supera due segmenti SMS.
- Il mittente (numero o nome) è configurabile.

### B7 · Promemoria e controllo prima dell'appuntamento

**Priorità** Must · **Stima** 5 · **Rilascio** Hackathon · **Dipende da** B5, C8

**Storia.** Come Giulia, voglio ricevere qualche giorno prima un promemoria con il controllo dei documenti, così che arrivo allo sportello con tutto.

**Criteri di accettazione**

- Il promemoria parte 3 giorni prima (valore configurabile), alle 10:00 ora di Roma. Se l'appuntamento è più vicino, parte subito dopo la registrazione.
- Né il testo dell'SMS né l'oggetto dell'email nominano il servizio o la variante. Il messaggio contiene solo un link personale che apre la checklist.
- La checklist mostra per ogni requisito: nome ufficiale, spiegazione nella lingua del cittadino, fonte e data di verifica.
- Il cittadino spunta ciò che ha. L'assistente segnala ciò che manca e cosa fare, con i tempi se noti.
- Il risultato finale dice "in base alle fonti citate risultano presenti tutti i documenti richiesti", mai "idoneo" o "tutto in regola".
- Un secondo promemoria la sera prima ricorda solo ora e sede. Nell'hackathon è Could.
- Se il cittadino ha revocato il consenso, non parte nessun promemoria.

### B8 · Dire com'è andata

**Priorità** Must · **Stima** 5 · **Rilascio** Hackathon · **Dipende da** B7, C9, C10

**Storia.** Come Giulia, voglio dire con un tocco com'è andato l'appuntamento e, se voglio, lasciare un suggerimento, così che il Comune sa cosa migliorare.

**Criteri di accettazione**

- Il giorno dopo l'appuntamento, alle 18:00, arriva la domanda con tre risposte: tutto a posto, mancava qualcosa, altro.
- Con "mancava qualcosa" il cittadino sceglie dall'elenco della sua checklist oppure scrive. Con "altro" scrive.
- Due domande facoltative: se la pratica si è chiusa in tempo utile (sì o no), e un voto da 1 a 5 con un suggerimento libero.
- Le risposte hanno la forma adatta al canale: link-pulsanti nell'email, 1, 2 o 3 nell'SMS, pulsanti nella web chat.
- Il testo libero passa dalla pipeline privacy (C9) prima del salvataggio. Il testo originale non viene mai scritto nel database.
- Se il cittadino non risponde, riceve un solo sollecito dopo 3 giorni e poi nient'altro.
- Se una lacuna collegata al suo caso viene corretta e il cittadino ha dato il consenso, riceve un breve messaggio che glielo comunica.

### B9 · Gestire i propri dati

**Priorità** Must · **Stima** 3 · **Rilascio** Hackathon · **Dipende da** B5, C2

**Storia.** Come Daniel, voglio revocare i consensi o cancellare il mio contatto in qualsiasi momento, così che controllo io cosa succede ai miei dati.

**Criteri di accettazione**

- Ogni messaggio contiene un link per gestire i consensi. Negli SMS anche la parola STOP revoca tutti i consensi.
- La cancellazione rimuove subito il contatto e il suo collegamento con il caso. Il caso resta solo in forma anonima.
- Dopo la revoca non parte più nessun messaggio. Lo verifica un test sullo scheduler.
- Il cittadino riceve una conferma della revoca, ed è l'ultimo messaggio che riceve.

### B10 · Vedere le lacune in ordine di priorità

**Priorità** Must · **Stima** 5 · **Rilascio** Hackathon · **Dipende da** C10, C12

**Storia.** Come Marco, voglio vedere le lacune ordinate per numero di casi e per servizio, così che so cosa correggere questa settimana.

**Criteri di accettazione**

- La lista mostra per ogni lacuna: causa (una delle sei), servizio, pagina, numero di casi nel periodo, stato (nuova, in revisione, corretta, archiviata) e destinatario.
- I gruppi sotto soglia stanno in una sezione separata, senza sede né date dei singoli casi.
- Si può filtrare per causa, servizio e stato, e ordinare per numero di casi.
- Ogni lacuna ha un riassunto scritto da Claude, esempi generalizzati (mai il testo originale dei cittadini) e la bozza di correzione.
- Le lacune su norme nazionali sono marcate come "fonte non comunale", con il nome dell'ente proprietario.

### B11 · Approvare una correzione

**Priorità** Must · **Stima** 5 · **Rilascio** Hackathon · **Dipende da** B10

**Storia.** Come Marco, voglio approvare o modificare la bozza di correzione, così che pagina e assistente si aggiornano in pochi minuti.

**Criteri di accettazione**

- Posso approvare la bozza, modificarne il testo o archiviarla con una motivazione.
- Quando approvo:
  - l'intervento viene registrato (chi, quando, testo);
  - il requisito entra nel catalogo con fonte "correzione approvata", finché la pagina ufficiale non viene aggiornata;
  - l'assistente lo usa dalla conversazione successiva.
- La bozza ha tre versioni: italiano, italiano facile e inglese. Ognuna si può modificare separatamente.
- Dall'approvazione in poi il pannello misura l'effetto della correzione (B13).
- Chi non ha il ruolo redazione non vede il pulsante di approvazione.

### B12 · Ricevere segnalazioni aggregate

**Priorità** Should · **Stima** 3 · **Rilascio** Hackathon nel pannello; Dopo anche via email · **Dipende da** C10

**Storia.** Come Laura, voglio ricevere solo segnalazioni aggregate sulle procedure del mio ufficio, così che intervengo sui problemi ricorrenti senza esserne sommersa.

**Criteri di accettazione**

- Una segnalazione parte solo quando una lacuna supera la soglia, configurabile (default: 5 casi in 4 settimane).
- La segnalazione contiene causa, procedura, numero di casi, periodo, pagina e bozza. Non contiene mai date od orari dei singoli appuntamenti né riferimenti ai dipendenti.
- Nell'hackathon le segnalazioni compaiono in una casella del pannello. Dopo l'hackathon arrivano anche all'email istituzionale dell'ufficio.
- Le richieste fatte allo sportello ma non previste dalla procedura sono riportate per procedura e per sede.

### B13 · Pannello delle metriche e sintesi settimanale

**Priorità** Must · **Stima** 8 · **Rilascio** Hackathon · **Dipende da** C11, C12, A5

**Storia.** Come Paola, voglio un pannello con poche metriche affidabili e una sintesi settimanale in linguaggio semplice, così che so se il servizio migliora e quanto vale.

**Criteri di accettazione**

- Metriche minime nell'hackathon:
  - pratiche chiuse al primo appuntamento, per servizio, per categoria (UE o extra-UE) e per lingua, in forma aggregata;
  - lacune per causa;
  - effetto prima e dopo di ogni correzione;
  - appuntamenti a vuoto evitati e costo stimato.
- Metriche da aggiungere dopo l'hackathon:
  - pratiche chiuse in tempo utile;
  - tempo tra segnalazione e correzione;
  - procedure mancanti più richieste;
  - pagine non verificate da tempo;
  - soddisfazione.
- Nessuna cella mostra meno di 5 casi. Al loro posto compare "dati insufficienti".
- Il costo stimato mostra la formula e il costo per slot usato, con la dicitura "stima".
- Ogni lunedì Claude scrive una sintesi di massimo 200 parole: cosa è migliorato, cosa è peggiorato e tre interventi consigliati, con rimando ai numeri del pannello. La sintesi usa solo dati presenti nelle viste aggregate.
- Accanto a ogni metrica c'è un'icona informazioni con la definizione di A5.

---

## Epica C · Come lo farà

### C1 · Monorepo e ambiente locale

**Priorità** Must · **Stima** 3 · **Rilascio** Hackathon · **Dipende da** nessuna

**Storia.** Come sviluppatore del team, voglio un repository pronto che si avvia con un solo comando, così che tutti lavorano nello stesso ambiente dal primo minuto.

**Criteri di accettazione**

- Il repository ha la struttura descritta sopra, con workspace uv, ruff, mypy in modalità strict e pytest.
- `make up` avvia in Docker Postgres 17, Mailpit e le tre applicazioni, con il codice montato nei container e il ricaricamento automatico. Sull'host servono solo Docker e make.
- `.env.example` elenca tutte le variabili senza valori reali: chiave Anthropic, credenziali del fornitore SMS, SMTP, chiavi di cifratura e HMAC, soglie, identificativi dei modelli.
- I segreti non entrano mai nel repository. La CI lo controlla.
- `make migrate` e `make seed-demo` funzionano su un database vuoto.
- `make test` esegue l'intera batteria in un container, con un database di test dedicato.

### C2 · Database, schemi e ruoli

**Priorità** Must · **Stima** 5 · **Rilascio** Hackathon · **Dipende da** A4, C1

**Storia.** Come team, voglio che la separazione tra contatti, casi e metriche sia imposta dal database, così che il pannello non può leggere dati personali nemmeno per errore.

**Criteri di accettazione**

- `pii.contacts` contiene:
  - `id`;
  - `email` e `phone`, cifrati a livello applicativo con AES-256-GCM (libreria `cryptography`, chiave in una variabile d'ambiente), più un HMAC con una chiave separata per deduplica e ricerca;
  - `preferred_channel` e `fallback_channel` (email o SMS);
  - `language`;
  - `consents` (jsonb, una voce per finalità con data);
  - `confirmed_at` ed `expires_at`.
- `pii.appointments` contiene data, ora e sede esatte, collegate al contatto. Le usa solo lo scheduler.
- Lo schema `core` contiene:
  - `sessions`;
  - `cases`, con identificativo casuale, servizio, variante, categoria, lingua, ufficio, settimana dell'appuntamento, esito, causa e un `contact_ref` facoltativo;
  - `case_answers`, `gaps`, `gap_cases`, `interventions`;
  - `notifications`, con lo stato degli invii ma senza testo.
- Lo schema `analytics` contiene viste materializzate con filtro k ≥ 5.
- Il database ha quattro ruoli:
  - `app_assistant` scrive `core` e `pii`;
  - `app_notifier` legge `pii`;
  - `app_analysis` legge `core` e scrive `gaps`;
  - `app_dashboard` legge solo `analytics`, `core.gaps` e `core.interventions`.
- Un test automatico verifica i permessi: se il ruolo del pannello interroga `pii`, riceve un errore.
- Una fixture di sessione applica le migrazioni al database di test (`DATABASE_URL_TEST`) prima dei test marcati `db`.

**Come.** Modelli SQLAlchemy 2 e migrazioni Alembic. Ruoli e permessi sono definiti in una migrazione, non a mano.

### C3 · Agente: prompt, strumenti, validazione

**Priorità** Must · **Stima** 8 · **Rilascio** Hackathon · **Dipende da** A2, C1

**Storia.** Come team, voglio un agente con strumenti tipizzati e un validatore delle risposte, così che ogni requisito ha una fonte e nessuna risposta promette l'idoneità.

**Criteri di accettazione**

- `onevisit_agent` espone `run_turn(session, message, capabilities)`. La funzione non dipende dal canale e restituisce messaggi, risposte rapide e aggiornamenti dello stato del caso.
- Il prompt di sistema è versionato in `libs/onevisit_agent/prompts/` e contiene:
  - il ruolo;
  - le regole sulla lingua (B2);
  - le regole sulle fonti;
  - il divieto di chiedere dati di identità;
  - il divieto di dichiarare l'idoneità;
  - il formato dei termini ufficiali.
- Gli strumenti sono `identify_case`, `get_procedure`, `get_office`, `build_checklist`, `record_appointment`, `request_contact`, `record_outcome` e `report_missing_procedure`. Ognuno ha un modello Pydantic, dal quale si genera lo schema JSON passato all'API.
- Dopo ogni risposta un validatore controlla che:
  - ogni requisito citato abbia un `source_id` esistente;
  - non compaiano parole vietate ("idoneo", "in regola", "garantito" e le loro traduzioni).
- Se il validatore blocca una risposta, l'agente la rigenera una volta. Se la seconda è ancora bloccata, il cittadino riceve un messaggio di cortesia con il link alla pagina ufficiale. Ogni blocco viene registrato per la valutazione.
- Catalogo e fonti del servizio entrano nel contesto con prompt caching.
- I modelli si configurano tramite variabili d'ambiente: `claude-sonnet-5-5` per la conversazione, `claude-haiku-4-5-20251001` per i compiti brevi.
- Le chiamate al modello hanno timeout e nuovi tentativi con attesa crescente. Se il modello non risponde, il cittadino riceve un messaggio chiaro e il link alla pagina ufficiale.

### C4 · Base di conoscenza

**Priorità** Must · **Stima** 3 · **Rilascio** Hackathon · **Dipende da** A1, A2

**Storia.** Come team, voglio caricare fonti e catalogo in modo verificabile, così che l'assistente usa sempre la versione approvata e sa quando una pagina è cambiata.

**Criteri di accettazione**

- `onevisit_knowledge` carica catalogo e fonti, li valida e li espone per servizio.
- Le correzioni approvate (B11) si sovrappongono al catalogo, ciascuna con la sua provenienza.
- Quando `onevisit ingest` viene rieseguito, segnala le pagine il cui hash è cambiato e marca come "da riverificare" i requisiti collegati.
- Le date di verifica sono disponibili per l'avviso sulle pagine non verificate da tempo.

**Come.** Nell'hackathon non serve un database vettoriale: due servizi stanno interi nel contesto. Quando i servizi aumentano, si aggiunge la ricerca con pgvector.

### C5 · Gateway dei canali

**Priorità** Must · **Stima** 5 · **Rilascio** Hackathon · **Dipende da** C3

**Storia.** Come team, voglio un gateway con un'interfaccia unica per web, email e SMS, così che cambiare fornitore o aggiungere un canale non richiede modifiche all'agente.

**Criteri di accettazione**

- `ChannelAdapter` è un `typing.Protocol` con tre elementi:
  - `parse_inbound(request)`, che restituisce un `InboundMessage`;
  - `send(OutboundMessage)`;
  - `capabilities`: conversazione completa, pulsanti, lunghezza massima, invio proattivo.
- Esistono tre adattatori: web, email, SMS.
- Il messaggio normalizzato contiene sessione, testo, risposta rapida scelta, lingua del browser (se nota) e canale.
- I messaggi in arrivo sono idempotenti: l'identificativo del messaggio del canale viene registrato. C'è un limite di frequenza per sessione.
- Il webhook SMS verifica la firma del fornitore. I link di risposta delle email sono token firmati con scadenza. Le richieste non valide vengono rifiutate e registrate senza contenuto.

### C6 · Connettore SMS

**Priorità** Must · **Stima** 5 · **Rilascio** Hackathon · **Dipende da** C5

**Storia.** Come team, voglio inviare e ricevere SMS tramite un fornitore sostituibile, così che chi non ha l'email viene comunque ricontattato e la demo mostra il promemoria su un telefono vero.

**Criteri di accettazione**

- Nell'hackathon si usa l'account di prova di Twilio, che invia solo a numeri verificati. In produzione il fornitore lo sceglie il Comune.
- Nessun tipo specifico del fornitore esce dall'adattatore.
- Il webhook di ricezione verifica la firma del fornitore.
- I modelli dei messaggi (promemoria, follow-up, avviso di correzione, conferma della revoca, risposta ad AIUTO) stanno in `libs/onevisit_channels/templates/sms/`, in italiano e in inglese. Ammettono solo due segnaposto: giorni mancanti e link.
- I testi stanno entro i 160 caratteri GSM-7 dove possibile, e mai oltre due segmenti.
- Le risposte 1, 2, 3, STOP e AIUTO vengono riconosciute anche con spazi e maiuscole o minuscole diverse.
- I numeri sono normalizzati in E.164 con `phonenumbers`.

### C7 · Connettore email

**Priorità** Must · **Stima** 2 · **Rilascio** Hackathon · **Dipende da** C5

**Storia.** Come team, voglio inviare email con gli stessi contenuti degli SMS, così che chi sceglie l'email ha la stessa esperienza.

**Criteri di accettazione**

- L'invio usa aiosmtplib su SMTP. In sviluppo passa da Mailpit, che ha un'interfaccia web per mostrare le email durante la demo.
- I modelli Jinja2 esistono in italiano e in inglese, in versione HTML e testo semplice. I pulsanti di risposta sono link con token firmato.
- L'oggetto non nomina mai la pratica.
- Ogni email ha l'intestazione `List-Unsubscribe` e il link per gestire i consensi.
- Prima di attivare i promemoria, il cittadino conferma l'indirizzo tramite un link.

### C8 · Scheduler di promemoria e follow-up

**Priorità** Must · **Stima** 3 · **Rilascio** Hackathon · **Dipende da** C2, C5

**Storia.** Come team, voglio uno scheduler affidabile su Postgres, così che i messaggi partono all'ora giusta anche dopo un riavvio.

**Criteri di accettazione**

- Procrastinate gira nel servizio gateway con questi lavori:

| Lavoro | Quando |
|---|---|
| `reminder` | 3 giorni prima dell'appuntamento, alle 10:00 |
| `eve_reminder` | la sera prima, alle 18:00 (facoltativo) |
| `followup` | il giorno dopo l'appuntamento, alle 18:00 |
| `followup_nudge` | 4 giorni dopo l'appuntamento |
| `correction_notice` | quando viene approvata una correzione collegata |
| `analysis` | periodico (vedi C10) |
| `retention_purge` | ogni giorno |

- Il fuso orario è `Europe/Rome`, con `zoneinfo`, e l'ora legale è gestita.
- Prima di ogni invio il lavoro ricontrolla consenso e stato del contatto. Se il consenso è stato revocato, si chiude senza inviare.
- Se l'invio fallisce: tre tentativi con attesa crescente, poi il canale di riserva se esiste, poi stato "fallito" nel registro.
- Una variabile di modalità demo comprime i tempi, per esempio un giorno diventa un minuto, così il ciclo si mostra dal vivo.
- Lo schema di Procrastinate è applicato con una migrazione Alembic, con i permessi sulle sue tabelle per `app_notifier` e `app_analysis`. Solo dopo si rimuove il profilo `workers` da `compose.yaml`, così `make up` avvia anche i worker.

### C9 · Pipeline privacy

**Priorità** Must · **Stima** 5 · **Rilascio** Hackathon · **Dipende da** C2, C3

**Storia.** Come team, voglio che ogni testo libero sia ripulito e trasformato in campi strutturati prima del salvataggio, così che nel database non finiscono mai le parole esatte scritte dal cittadino.

**Criteri di accettazione**

- Il primo passaggio è deterministico: espressioni regolari per email, numeri di telefono, codici fiscali, IBAN e i numeri dei documenti più comuni.
- Il secondo passaggio usa `claude-haiku-4-5-20251001`. Rimuove nomi, indirizzi e dettagli identificativi ed estrae i campi strutturati: requisito mancante, causa probabile, tono, suggerimento generalizzato.
- Si salva solo l'output strutturato. Il testo originale resta in memoria per la sola durata della richiesta.
- I log applicativi non contengono testo dei messaggi né contatti. Un test cerca email e numeri di telefono nei log prodotti dai test end-to-end.
- `retention_purge` cancella i contatti scaduti, rimuove `contact_ref` dai casi e accorpa le date al mese.
- Un insieme di prova contiene 20 frasi con dati personali, e nessuno di quei dati deve uscire dalla pipeline.

### C10 · Analisi delle lacune

**Priorità** Must · **Stima** 8 · **Rilascio** Hackathon · **Dipende da** C4, C9

**Storia.** Come team, voglio che Claude classifichi gli esiti, li raggruppi in lacune e scriva le bozze, così che il pannello mostra diagnosi e non solo conteggi.

**Criteri di accettazione**

- Ogni esito negativo riceve una delle sei cause, con una motivazione breve e un livello di confidenza.
- Per servizio e pagina, Claude confronta l'esito con le lacune aperte e decide se aggiungerlo a una di queste o crearne una nuova. La decisione viene registrata.
- Claude assegna un destinatario:
  - la redazione;
  - l'ufficio titolare della procedura;
  - l'ente nazionale;
  - "migliorare l'assistente", per la causa "pagina chiara ma non seguita".
- Quando una lacuna supera la soglia, Claude scrive la bozza di correzione in italiano, italiano facile e inglese, indicando la pagina e il testo da cambiare.
- Le richieste allo sportello non previste vengono aggregate per procedura e per sede, mai per persona. Il prompt lo vieta, e un controllo verifica che nessun nome proprio compaia nei campi salvati.
- L'analisi gira come lavoro periodico, per esempio ogni ora. In modalità demo parte su richiesta.

### C11 · Metriche e confronto prima e dopo

**Priorità** Must · **Stima** 5 · **Rilascio** Hackathon · **Dipende da** C2, A5

**Storia.** Come team, voglio metriche calcolate in viste aggregate con soglia, così che il pannello è veloce e non mostra mai casi singoli.

**Criteri di accettazione**

- Per ogni metrica di A5 esiste una vista materializzata in `analytics`, creata con una migrazione Alembic. Le viste si aggiornano dopo ogni analisi e ogni notte.
- Il filtro k ≥ 5 è applicato nella vista, non nell'interfaccia.
- Per ogni intervento si calcola il tasso di pratiche chiuse al primo appuntamento nelle quattro settimane prima e nelle quattro dopo, con il numero di casi. Sotto soglia il risultato è nullo.
- I parametri (costo per slot, soglia k, finestre temporali) stanno in una tabella di configurazione, modificabile dal ruolo direzione.
- Test con dati sintetici verificano che i risultati siano quelli attesi.

### C12 · Applicazione del pannello

**Priorità** Must · **Stima** 8 · **Rilascio** Hackathon · **Dipende da** C11; dà forma a B10–B13

**Storia.** Come team, voglio un'applicazione web per il Comune, separata dall'assistente e con accesso per ruoli, così che redazione, uffici e direzione vedono ciascuno ciò che gli serve.

**Criteri di accettazione**

- È un'applicazione FastAPI con Jinja2, HTMX e Chart.js, separata da `assistant_web` e con il proprio ruolo database `app_dashboard`.
- Nell'hackathon l'accesso avviene con utenti dimostrativi per ruolo: redazione, ufficio, direzione. In produzione avviene con il sistema di accesso aziendale del Comune tramite OIDC (Authlib).
- Le pagine sono:
  - Panoramica (metriche);
  - Lacune, compresi i gruppi sotto soglia;
  - Dettaglio lacuna, con bozza e approvazione;
  - Segnalazioni dell'ufficio;
  - Interventi, con il confronto prima e dopo;
  - Sintesi settimanale;
  - Impostazioni (parametri).
- Un registro degli accessi annota chi ha visto o approvato cosa.
- Il pannello è accessibile: contrasto AA, navigazione da tastiera, e per ogni grafico una tabella equivalente.
- Nessuna pagina mostra un singolo caso.

### C13 · Valutazione dell'agente

**Priorità** Must · **Stima** 5 · **Rilascio** Hackathon · **Dipende da** A2, C3

**Storia.** Come team, voglio un insieme di scenari che verifichi l'agente a ogni modifica, così che la specializzazione si basa su prove e non su impressioni.

**Criteri di accettazione**

- `data/eval/` contiene almeno 15 scenari, tra cui:
  - le varianti dei due servizi;
  - quattro lingue;
  - un servizio fuori catalogo;
  - un cittadino che scrive il proprio codice fiscale;
  - un tentativo di farsi dire "sei in regola".
- Ogni scenario indica i messaggi del cittadino, il servizio e la variante attesi, i requisiti attesi, la lingua attesa e i divieti.
- `uv run onevisit eval` esegue gli scenari e produce un report che verifica, per ciascuno:
  - variante corretta;
  - requisiti presenti;
  - fonti presenti;
  - lingua corretta;
  - assenza di parole vietate;
  - nessun dato personale salvato.
- La CI esegue un sottoinsieme veloce di 5 scenari a ogni PR. L'insieme completo si esegue prima di ogni consegna.
- I casi anonimi raccolti in produzione possono diventare nuovi scenari dopo una revisione umana. È questa la specializzazione descritta nel concept.

---

## Epica D · Implementazione e consegna

### D1 · Dati sintetici e scenario demo

**Priorità** Must · **Stima** 3 · **Rilascio** Hackathon · **Dipende da** C2, C10, C11

**Storia.** Come team, voglio un generatore di dati sintetici che racconta una storia, così che il pannello è credibile e la demo mostra un miglioramento misurabile.

**Criteri di accettazione**

- `uv run onevisit seed-demo` genera 8 settimane di casi (circa 400) per i due servizi, con una distribuzione realistica di esiti, lingue e categorie.
- I dati raccontano questa storia:
  - dalla settimana 2 emerge una lacuna "procedura mancante" per un caso extra-UE;
  - nella settimana 4 la lacuna supera la soglia;
  - nella settimana 5 viene corretta;
  - nelle settimane successive sale il tasso di chiusura al primo appuntamento per quel servizio.
- Tutti i dati sono marcati come sintetici. Non c'è nessun dato reale.
- Il generatore è deterministico, con un seme fisso, così i numeri nel video sono sempre gli stessi.

### D2 · Integrazione continua

**Priorità** Must · **Stima** 2 · **Rilascio** Hackathon · **Dipende da** C1

**Storia.** Come team, voglio controlli automatici a ogni PR, così che nessuno rompe il percorso demo a mezz'ora dalla consegna.

**Criteri di accettazione**

- La pipeline esegue tutto nei container, come `make test` in locale:
  - formattazione e lint con ruff;
  - mypy;
  - pytest con Postgres e copertura minima, compresi i test dei permessi del database;
  - valutazione veloce dell'agente (C13), con la chiave salvata nei segreti del repository;
  - build dell'immagine di produzione.
- Una ricerca di segreti nel codice (gitleaks) fa fallire la build se ne trova.
- Il ramo principale è protetto: si fonde solo con la CI verde.
- I passaggi sono comandi standard, quindi la stessa pipeline si sposta su GitLab CI senza modifiche di sostanza.

### D3 · Ambiente demo e runbook

**Priorità** Must · **Stima** 3 · **Rilascio** Hackathon · **Dipende da** C1–C8

**Storia.** Come team, voglio un ambiente demo riproducibile e un runbook, così che la demo funziona anche se cade la rete o un servizio.

**Criteri di accettazione**

- `make demo` avvia tutto con dati sintetici e scheduler in modalità compressa.
- Un tunnel pubblico (cloudflared o ngrok) serve solo a ricevere le risposte SMS. L'invio funziona anche senza.
- `docs/runbook.md` descrive:
  - avvio, verifica e azzeramento dei dati;
  - cosa fare se manca la rete: video di riserva già registrato, email su Mailpit in locale.
- Il numero di prova verificato e l'account del fornitore SMS sono preparati e annotati, senza scrivere segreti nel documento.

### D4 · Prova generale del percorso demo

**Priorità** Must · **Stima** 2 · **Rilascio** Hackathon · **Dipende da** D1, D3, B1–B13

**Storia.** Come team, voglio provare il percorso demo dall'inizio alla fine almeno due volte, così che il pitch non dipende dalla fortuna.

**Criteri di accettazione**

- Un test Playwright per Python, nella cartella `e2e/` ed eseguito con `make e2e`, ripete il percorso web: descrizione, inglese, enti e ufficio, appuntamento, contatto SMS, controllo, esito.
- Una prova manuale con un telefono vero conferma che il promemoria SMS arriva in modalità compressa e che la risposta "2" viene registrata.
- Una prova del pannello conferma che la lacuna è visibile, che si può approvare, che la nuova checklist contiene il requisito e che il confronto prima e dopo è visibile.
- I tempi di ogni passaggio sono annotati. Il percorso completo sta in 90 secondi.

### D5 · Consegna

**Priorità** Must · **Stima** 1 · **Rilascio** Hackathon · **Dipende da** A6, D4, E3

**Storia.** Come team, voglio consegnare repository, README e video entro la scadenza, così che la giuria può valutare tutto.

**Criteri di accettazione**

- Il repository è pubblico, o accessibile alla giuria, con licenza EUPL-1.2, README, documentazione e istruzioni di avvio.
- Il link al video è nel README.
- Il commit consegnato ha il tag `v0.1-hackathon`.
- La consegna avviene entro l'orario del brief (da verificare sulle slide), con almeno 15 minuti di margine.

---

## Epica E · Video

### E1 · Sceneggiatura e storyboard

**Priorità** Must · **Stima** 2 · **Rilascio** Hackathon · **Dipende da** l'avanzamento delle epiche B e C

**Storia.** Come team, voglio una sceneggiatura di due minuti con tempi precisi, così che il video racconta il valore e non un elenco di funzioni.

**Criteri di accettazione**

- La durata totale resta entro 2:00 (limite da verificare sulle slide).
- La struttura è questa:

| Tempo | Scena |
|---|---|
| 0:00–0:15 | Il problema: un secondo viaggio, uno slot sprecato |
| 0:15–0:55 | Daniel: descrizione in inglese, enti in ordine, prenotazione, scelta dell'SMS |
| 0:55–1:10 | L'SMS arriva sul telefono; il controllo trova la traduzione mancante |
| 1:10–1:40 | Marco: lacuna nel pannello, bozza, approvazione, confronto prima e dopo |
| 1:40–1:55 | Dove lavora Claude e le scelte sulla privacy, in una sola schermata |
| 1:55–2:00 | Frase di chiusura |

- Per ogni scena sono indicati inquadratura (schermo o telefono), testo parlato, testo a schermo e durata.
- Il testo parlato è scritto per intero e cronometrato leggendolo ad alta voce.

**Artefatti.** `docs/video/script.md`, `docs/video/storyboard.md`.

### E2 · Registrazione e montaggio

**Priorità** Must · **Stima** 3 · **Rilascio** Hackathon · **Dipende da** E1, D4

**Storia.** Come team, voglio registrare e montare il video dall'ambiente demo, così che mostra il prodotto vero e non una simulazione.

**Criteri di accettazione**

- La registrazione è in 1920×1080 dall'ambiente demo. Il telefono è ripreso o duplicato sullo schermo per mostrare l'SMS.
- La voce è registrata con un microfono, nella lingua richiesta dal brief, con sottotitoli nell'altra lingua tra italiano e inglese.
- A schermo compaiono solo dati sintetici e il numero di prova. Nessuna notifica personale.
- La musica, se c'è, è libera da diritti.
- Il video è esportato in MP4 H.264 e i sottotitoli in `.srt`.
- Il video si registra e si monta con strumenti aperti, per esempio OBS Studio e Shotcut o Kdenlive.

**Artefatti.** Il file video o il suo link, `docs/video/subtitles.srt`.

### E3 · Revisione e consegna del video

**Priorità** Must · **Stima** 1 · **Rilascio** Hackathon · **Dipende da** E2

**Storia.** Come team, voglio far vedere il video a qualcuno che non l'ha costruito, così che il messaggio arriva anche a chi lo guarda per la prima volta.

**Criteri di accettazione**

- Una persona esterna al tavolo guarda il video e sa ripetere in una frase cosa fa OneVisit e dove lavora Claude.
- Durata, formato e caricamento rispettano il brief. Il link funziona anche da una finestra in incognito.
- Il link è nel README (D5).

---

## Ordine di lavoro e divisione del team

### Le cinque ondate

| Ondata | Storie | Risultato |
|---|---|---|
| 1 · Fondamenta | C1, A1, A3, A4 in parallelo | Repository avviabile, fonti raccolte, decisioni scritte |
| 2 · Nucleo | A2, C2, C3, C4, C5 | Agente che risponde nella web chat citando le fonti |
| 3 · Percorso | B1–B7, C6, C7, C8 | Percorso del cittadino completo, con promemoria via SMS ed email |
| 4 · Ciclo | C9, C10, C11, C12, D1, B8, B10, B11, B13 | Lacune, approvazione, metriche nel pannello |
| 5 · Consegna | D3, D4, E1–E3, A6, D5 | Demo provata, video, README, consegna |

### Divisione del team

| Persona | Storie |
|---|---|
| 1 · Fonti e dati | A1, A2, A5, C4, D1 |
| 2 · Agente | C3, C9, C10, C13, B1–B4 (lato agente) |
| 3 · Canali e backend | C1, C2, C5–C8, B5, B6, B9 |
| 4 · Pannello, pitch e video | A3, A4, A6, C11, C12, B10–B13, E1–E3, D5 |

### Se il tempo è quello di una sola giornata

Si tengono le storie Must con rilascio Hackathon. Si tagliano, in quest'ordine:

1. B12 via email;
2. il secondo promemoria di B7;
3. la sintesi settimanale di B13;
4. la ricezione delle risposte SMS di B6, tenendo solo l'invio, così non serve nemmeno il tunnel.

Il percorso demo regge con web chat, SMS in uscita ed email su Mailpit.

### Cosa resta per dopo l'hackathon

- Fornitore SMS scelto dal Comune, preferibilmente con trattamento dei dati nell'Unione europea.
- SMTP istituzionale.
- Accesso al pannello con il sistema aziendale del Comune.
- Verifica del numero di telefono con codice.
- Segnalazioni agli uffici via email.
- Ricerca con pgvector quando aumentano i servizi.
- Valutazione di App IO insieme al Comune.
- DPIA completa insieme al DPO.
- Pubblicazione del codice per il riuso da parte di altre amministrazioni.
