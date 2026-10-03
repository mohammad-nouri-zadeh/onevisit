# Definizione delle metriche del pannello

*Storia A5. Ogni numero del pannello ha qui formula, origine, periodo, soglia e limiti, così chi lo cita (Paola, dirigente dei servizi civici) può difenderlo. Viste SQL: migrazione `0002_core_pii_analytics`. Parametri: `analytics.config` e variabili `ONEVISIT_*`.*

## Parametri comuni

| Parametro | Dove | Default | Significato |
|---|---|---|---|
| `k_threshold` | `analytics.config`, `ONEVISIT_K_THRESHOLD` | 5 | Casi minimi per mostrare una cella aggregata. Applicato dentro le viste |
| `window_weeks` | `analytics.config` | 4 | Settimane prima e dopo una correzione |
| `cost_per_slot_eur` | `analytics.config`, `ONEVISIT_COST_PER_SLOT_EUR` | 0 | Costo medio di uno slot allo sportello. **Lo fornisce il Comune**; finché è 0 il pannello mostra solo gli appuntamenti evitati |
| Soglia delle segnalazioni | `ONEVISIT_GAP_THRESHOLD_CASES`, `ONEVISIT_GAP_THRESHOLD_WEEKS` | 5 casi in 4 settimane | Quando una lacuna parte verso l'ufficio |
| Fonte "vecchia" | `ONEVISIT_SOURCE_STALE_DAYS` | 30 giorni | Oltre questa età di verifica una fonte è segnalata |

Unità di misura: il **caso con esito**, cioè una riga di `core.cases` con `outcome` non nullo (il cittadino ha detto com'è andata). I casi sintetici (`synthetic = true`) sono marcati come tali e nel pannello della demo compare la dicitura "dati sintetici".

## Metriche

### 1. Pratiche chiuse al primo appuntamento

| | |
|---|---|
| Formula | `casi con outcome = 'ok'` / `casi con outcome non nullo` |
| Origine | `core.cases` → vista `analytics.first_visit_rate` (per servizio, categoria, lingua) e `analytics.weekly_first_visit` (per servizio e settimana) |
| Periodo | Settimana dell'appuntamento (`appointment_week`, lunedì); nel pannello ultime 8 settimane |
| Soglia | Righe con meno di k=5 casi escluse dalla vista |
| Limiti | Conta solo chi risponde dopo l'appuntamento (autoselezione: chi ha avuto problemi può rispondere di più o di meno). L'esito è dichiarato dal cittadino, non verificato con l'anagrafe. Chi usa OneVisit è probabilmente più attento della media |

### 2. Pratiche chiuse in tempo utile

| | |
|---|---|
| Definizione | **Tempo utile**: la pratica si è chiusa entro la scadenza dichiarata dal cittadino nella fase "Capire" (B1, domanda `scadenza`, salvata in `deadline_days`). Il cittadino lo conferma nella domanda dopo l'appuntamento (`closed_in_time`) |
| Formula | `casi con closed_in_time = true` / `casi con deadline_days non nullo e closed_in_time non nullo` |
| Origine | `core.cases` (`deadline_days`, `closed_in_time`) |
| Periodo | Settimana dell'appuntamento |
| Soglia | k=5 |
| Limiti | Solo per chi ha dichiarato una scadenza; la risposta è soggettiva. Nell'hackathon non c'è ancora una vista dedicata: si calcola come le altre con lo stesso filtro k |

### 3. Lacune aperte, per causa e servizio

| | |
|---|---|
| Formula | Numero di `core.gaps` con `status` in (`nuova`, `in-revisione`), per `cause`; somma di `case_count` |
| Origine | `analytics.gaps_by_cause`; dettaglio in `core.gaps` |
| Periodo | Lacune non archiviate, qualsiasi data |
| Soglia | Il numero di casi è null sotto k=5; il gruppo resta visibile alla redazione senza sede né date |
| Limiti | La causa è proposta da Claude (Haiku) tra sei categorie fisse e può essere sbagliata; la redazione la conferma o la cambia prima di approvare |

### 4. Procedure mancanti più richieste

| | |
|---|---|
| Formula | Lacune con `cause = 'procedura-mancante'` ordinate per `case_count` |
| Origine | `core.gaps` (eventi `missing_procedure` dell'agente quando non trova alcuna fonte) |
| Soglia | k=5 per il numero di casi |
| Limiti | Conta le richieste arrivate all'assistente, non il bisogno reale della città |

### 5. Tempo dalla prima segnalazione alla correzione

| | |
|---|---|
| Formula | `core.interventions.approved_at` − `core.gaps.first_seen`, mediana per servizio |
| Origine | `core.gaps`, `core.interventions` |
| Limiti | Misura l'approvazione nel pannello, non la pubblicazione sulla pagina del Comune |

### 6. Effetto di una correzione (prima e dopo)

| | |
|---|---|
| Formula | `tasso_dopo − tasso_prima`, dove ciascun tasso è la metrica 1 per il servizio della correzione, calcolata sulle **4 settimane prima** e sulle **4 settimane dopo** `approved_at` (`window_weeks`) |
| Origine | `analytics.intervention_effect` (`cases_before`, `rate_before`, `cases_after`, `rate_after`) |
| Soglia | **Almeno k=5 casi con esito in ciascuna finestra**: sotto soglia la vista restituisce null e il pannello scrive "dati insufficienti". Per una lettura affidabile raccomandiamo almeno 30 casi per finestra |
| Limiti | Confronto prima/dopo, non esperimento controllato: stagionalità o altri cambiamenti nelle stesse settimane possono influire. È comunque la prova più solida, perché la correzione vale per tutti i cittadini e non solo per chi usa il bot |

### 7. Appuntamenti a vuoto evitati e costo risparmiato (stima)

| | |
|---|---|
| Formula | `appuntamenti evitati = Σ max(tasso_dopo − tasso_prima, 0) × casi_dopo` per ogni correzione del servizio; `costo risparmiato = appuntamenti evitati × cost_per_slot_eur` |
| Origine | `analytics.avoided_visits`, che usa `analytics.intervention_effect` |
| Soglia | Eredita il filtro k della vista dell'effetto |
| Limiti | **È una stima e va presentata come tale.** Tende a essere troppo alta, perché chi usa l'assistente è probabilmente più attento della media e perché ignora altre cause del miglioramento. Il costo per slot è un parametro configurabile che deve fornire il Comune; finché è 0 non si mostra alcun valore in euro. Il confronto con un dato storico del Comune (non disponibile oggi) sovrastimerebbe ancora di più |

### 8. Divario tra cittadini extra-UE e gli altri

| | |
|---|---|
| Formula | `tasso(extra-ue) − tasso(italiana + ue)`, metrica 1 per categoria |
| Origine | `analytics.first_visit_rate` (colonna `category`) |
| Soglia | k=5 per ciascuna categoria |
| Contesto | Base di partenza dal Comune: nel sondaggio 2022 sul servizio online di residenza (`ds1702`) il 42,1% dei cittadini stranieri ha risposto che il servizio ha aiutato poco o per niente, contro il 28,2% degli italiani (vedi [data/context/README.md](../data/context/README.md)) |
| Limiti | La categoria è dichiarata nella conversazione; mai usata per decisioni sulla singola persona |

### 9. Pagine non verificate da tempo

| | |
|---|---|
| Formula | Fonti di `data/sources.csv` con `retrieved_at` più vecchio di `ONEVISIT_SOURCE_STALE_DAYS` o con stato `todo` |
| Origine | Catalogo (`catalog.is_stale`) |
| Limiti | La data di recupero non dice se la pagina è cambiata; serve un nuovo `onevisit ingest` e il confronto dell'hash |

### 10. Soddisfazione

| | |
|---|---|
| Formula | Media di `rating` (1-5) per servizio |
| Origine | `core.cases.rating` |
| Soglia | k=5 |
| Limiti | Risposta facoltativa, campione piccolo e autoselezionato |

## Metriche nel perimetro dell'hackathon

Il pannello della demo mostra le quattro metriche del perimetro del concept: chiuse al primo appuntamento (1), lacune per causa (3), effetto prima e dopo (6), costo stimato (7). Le altre sono definite qui per il seguito.
