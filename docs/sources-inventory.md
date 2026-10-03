# Inventario delle fonti ufficiali

*Storia A1. Fonte di verità: [data/sources.csv](../data/sources.csv), mantenuto dal responsabile dei dati (@mohammad-nouri-zadeh). Questo documento lo riassume e ne elenca le lacune. Regole del catalogo: [data/README.md](../data/README.md) e [ADR 0007](adr/0007-catalogo-dal-livello-dati-del-team.md). Stato al 3 ottobre 2026, ore 14.*

## Servizi coperti

| Servizio (file del catalogo) | Varianti (domande decisive) | Enti coinvolti |
|---|---|---|
| Carta d'identità elettronica (`data/services/carta-identita.json`) | `motivo`: prima, rinnovo, smarrimento-furto; `eta`: adulto, minore; `cittadinanza`: italiana, ue, extra-ue; `scadenza` | Comune di Milano (anagrafe); Ministero dell'Interno per la CIE |
| Iscrizione anagrafica di un cittadino extra-UE arrivato dall'estero (`data/services/iscrizione-anagrafica-extra-ue.json`) | `permesso`: permesso, ricevuta, nessuno; `famiglia`: solo, con-familiari; `alloggio`: affitto, ospite, proprieta; `scadenza` | Questura di Milano (permesso di soggiorno) → Agenzia delle Entrate (codice fiscale) → Comune di Milano (residenza) |

## Fonti

| id | Ente | URL | Servizio | Varianti coperte | Data di verifica | Lingua | Stato |
|---|---|---|---|---|---|---|---|
| `ds549` | Comune di Milano | https://dati.comune.milano.it/dataset/ds549-sedi-dei-servizi-anagrafici | Entrambi: sedi anagrafiche, orari, regole di prenotazione | Tutte (requisiti `su-appuntamento`, `prenotazione-senza-spid` della CIE) | 2026-10-03 (risorsa modificata il 2026-01-28) | it | ok · 2 requisiti verificati |
| `ds1702` | Comune di Milano | https://dati.comune.milano.it/dataset/ds1702-rilevazione-qualita-servizio-richieste-residenza-anno-2022 | Contesto per il pannello (residenza online) | — | 2026-10-03 | it | ok · solo statistiche |
| `ds1511` | Comune di Milano | https://dati.comune.milano.it/dataset/ds1511-rilevazione-della-qualita-del-servizio-appuntamenti-on-line-anno-2021 | Contesto (appuntamenti online) | — | 2026-10-03 | it | ok · solo statistiche |
| `ds1512` | Comune di Milano | https://dati.comune.milano.it/dataset/ds1512-rilevazione-qualita-servizio-richieste-certificati-anno-2021 | Contesto (certificati online) | — | 2026-10-03 | it | ok · solo statistiche |
| `ds1959` | Comune di Milano | https://dati.comune.milano.it/dataset/ds1959-popolazione-iscrizioni-anagrafiche-per-luogo-di-provenienza | Contesto (iscrizioni dall'estero) | — | 2026-10-03 | it | ok · solo statistiche |
| `ds74` | Comune di Milano | https://dati.comune.milano.it/dataset/ds74-popolazione-residenti-stranieri-cittadinanza-e-municipio | Contesto (lingue da supportare) | — | 2026-10-03 | it | ok · solo statistiche |
| `cie` | Comune di Milano | da trovare su comune.milano.it | Carta d'identità | prima, rinnovo, smarrimento-furto, minore, extra-ue (8 requisiti in attesa) | — | it | **todo** · pagina da salvare |
| `residenza-estero` | Comune di Milano | da trovare su comune.milano.it | Iscrizione anagrafica extra-UE | tutte (6 requisiti e il passaggio 3 in attesa) | — | it | **todo** · pagina da salvare |
| `prenotazione` | Comune di Milano | da trovare su comune.milano.it | Entrambi: link di prenotazione | — | — | it | **todo** · pagina da salvare |
| `permesso-soggiorno` | Polizia di Stato / Questura | da trovare (fonte nazionale) | Iscrizione extra-UE, passaggio 1 | permesso, ricevuta, nessuno | — | it | **todo** · pagina da salvare |
| `codice-fiscale` | Agenzia delle Entrate | da trovare (fonte nazionale) | Iscrizione extra-UE, passaggio 2 | — | — | it (verificare versione en) | **todo** · pagina da salvare |
| `yesmilano-students` | YesMilano | da trovare | Percorso per studenti internazionali (citato nel brief) | — | — | it/en | **todo** · facoltativa |

Nessuna fonte proviene da siti non ufficiali.

## Lacune evidenti

Diventano casi di prova per la demo e righe del pannello.

1. **Pagine ancora da salvare: `cie`, `residenza-estero`, `prenotazione`, `permesso-soggiorno`, `codice-fiscale`.** Finché mancano, l'assistente risponde "non lo so" su quei requisiti e rimanda al link ufficiale (comportamento voluto, ADR 0003). Priorità per la demo: la denuncia di smarrimento o furto per la CIE e i documenti rilasciati all'estero (traduzione) per l'iscrizione extra-UE.
2. **Varianti senza pagina dedicata:** il caso extra-UE con familiari (`famiglia = con-familiari`, documenti esteri da tradurre e legalizzare) e il caso con sola ricevuta del permesso (`permesso = ricevuta`) non hanno, per quanto visto finora, una pagina che li descriva per intero: candidati alla causa "procedura mancante".
3. **Dati del Comune non aggiornati (`ds549`):** la sede di Via Passerini 5 non ha Municipio, telefono né note di prenotazione e negli orari riporta ancora "lunedì 5 gennaio 2026: CHIUSO"; la sede del Municipio 1 ha un ingresso "provvisorio" da Via Pecorari 3 da verificare. Dettagli in `data/offices.json` (`data_issues`). È la causa "procedura non aggiornata" trovata nei dati reali.
4. **Enti nazionali non ancora descritti:** `data/enti.json` ha `questura-milano` e `agenzia-entrate` in stato `todo`.
5. **Come si presenta la dichiarazione di residenza** (sportello, email, online) va verificato sulla pagina `residenza-estero`: il sondaggio `ds1702` riguarda il servizio online.

## Come aggiungere una pagina

La rete della sandbox cloud blocca comune.milano.it ([ADR 0009](adr/0009-sandbox-senza-build-docker.md)), quindi le pagine si salvano da un browser:

1. aprire la pagina ufficiale e salvarla con Ctrl+S ("Pagina web, solo HTML");
2. importarla:
   ```bash
   onevisit ingest <id> --html <file.html> --url <url-ufficiale>
   # oppure, senza il kit:
   python data/tools/save_page.py <id> --html <file.html> --url <url-ufficiale>
   ```
   Il comando converte l'HTML in Markdown, scrive `data/pages/<id>.md` con intestazione (`url`, `ente`, `servizio`, `verified_at`, `content_hash`) e aggiorna la riga di `data/sources.csv`. Da una rete libera `onevisit ingest <id> --url <url>` scarica la pagina rispettando `robots.txt` e al massimo una richiesta al secondo;
3. copiare in `quote` la frase esatta per ogni requisito, scrivere `text_it` / `text_en`, `verified_at` e `status: "verified"`;
4. controllare: `python data/tools/validate.py` e `onevisit catalog-check`.
