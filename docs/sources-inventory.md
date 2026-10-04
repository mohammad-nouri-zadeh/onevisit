# Inventario delle fonti ufficiali

*Storia A1. Fonte di verità: [data/sources.csv](../data/sources.csv), mantenuto dal responsabile dei dati (@mohammad-nouri-zadeh). Questo documento lo riassume e ne elenca le lacune. Regole del catalogo: [data/README.md](../data/README.md) e [ADR 0007](adr/0007-catalogo-dal-livello-dati-del-team.md). Stato al 4 ottobre 2026.*

## Servizi coperti

| Servizio (file del catalogo) | Varianti (domande decisive) | Enti coinvolti | Verificati |
|---|---|---|---|
| Carta d'identità elettronica (`data/services/carta-identita.json`) | `motivo`: prima, rinnovo, smarrimento-furto; `eta`: adulto, minore; `cittadinanza`: italiana, ue, extra-ue; `scadenza` | Comune di Milano (anagrafe); Ministero dell'Interno per la CIE | 34 requisiti su 35, 3 passaggi su 3 |
| Cambio di residenza per persone straniere provenienti dall'estero, cittadini extra UE (`data/services/iscrizione-anagrafica-extra-ue.json`) | `permesso`: permesso, ricevuta-rinnovo, ricevuta-lavoro, ricevuta-famiglia, nessuno, altro; `famiglia`: solo, con-familiari; `alloggio`: proprieta, affitto, affitto-erp, comodato, ospite, lavoro-domestico; `scadenza` | Questura di Milano (permesso) → Agenzia delle Entrate o Questura (codice fiscale) → Comune di Milano (residenza, domanda online) | 44 requisiti su 45, 6 passaggi su 6 |

Le opzioni di `permesso` sono i quattro casi dell'Allegato A del Comune (permesso valido, in rinnovo, attesa del primo permesso per lavoro subordinato, attesa del primo permesso per ricongiungimento familiare), più "non l'ho ancora chiesto" e "altro".

## Fonti

| id | Ente | URL | Servizio | Cosa copre | Data | Lingua | Stato |
|---|---|---|---|---|---|---|---|
| `ds549` | Comune di Milano | https://dati.comune.milano.it/dataset/ds549-sedi-dei-servizi-anagrafici | Entrambi | Sedi, orari, regole di prenotazione (`su-appuntamento`, `prenotazione-senza-spid`) | 2026-10-03 (risorsa del 2026-01-28) | it | ok |
| `cie` | Comune di Milano | https://www.comune.milano.it/servizi/anagrafe/carta-d-identita | Carta d'identità | Documenti, casi (rinnovo, smarrimento, minori, extra UE), costo 22,20 euro, consegna, eccezioni senza appuntamento, carta provvisoria | 2026-10-04 (pagina aggiornata il 02/10/2026) | it | ok · 27 requisiti, 1 passaggio |
| `cie-ministero` | Ministero dell'Interno | https://www.cartaidentita.interno.gov.it/richiedi/rilascio-e-rinnovo-in-italia/ | Carta d'identità | Rinnovo da 180 giorni prima, cosa succede allo sportello, consegna in 6 giorni lavorativi | 2026-10-04 | it | ok · 4 requisiti, 2 passaggi |
| `prenotazione` | Comune di Milano | https://www.comune.milano.it/servizi/prenota-il-tuo-appuntamento-in-comune | Carta d'identità | Accettazione il giorno dell'appuntamento (QR code, codice fiscale o CIE) | 2026-10-04 (18/08/2026) | it | ok · 1 requisito |
| `residenza-estero` | Comune di Milano | https://www.comune.milano.it/servizi/anagrafe/cambio-di-residenza-per-persone-straniere-provenienti-dall-estero | Residenza extra UE | Domanda online, decorrenza dalla dichiarazione, accertamenti | 2026-10-04 (27/07/2026) | it | ok · 3 requisiti, 1 passaggio |
| `residenza-estero-modulistica` | Comune di Milano | https://www.comune.milano.it/servizi/anagrafe/richiesta-di-residenza-per-persone-straniere-provenienti-dall-estero/modulistica-richiesta-di-residenza-per-persone-straniere-provenienti-dall-estero | Residenza extra UE | Formati e peso dei file, documento d'identità, prova dell'alloggio per tipo, minori | 2026-10-04 (16/06/2026) | it | ok · 14 requisiti |
| `residenza-estero-extraue` | Comune di Milano (PDF) | https://www.comune.milano.it/documents/20118/42443/Elenco+documenti+per+persone+provenienti+da+Paesi+extraUE.pdf/f59656a6-d8aa-7960-fc88-60daf732aeb3 | Residenza extra UE | Allegato A: documenti per i quattro casi di permesso | 2026-10-04 (PDF creato nel 2013) | it | ok · 12 requisiti |
| `residenza-estero-modulo` | Comune di Milano (modulo online) | https://formshd4.comune.milano.it/rwe2/module_preview.jsp?MODULE_TAG=MOD_DDR_ESTERO | Residenza extra UE | Chi firma, caricamento solo online, email e protocollo, una domanda alla volta, assistenza | 2026-10-04 | it | ok · 6 requisiti, 1 passaggio |
| `dimora-abituale` | Comune di Milano | https://www.comune.milano.it/servizi/anagrafe/rinnovo-dichiarazione-dimora-abituale-per-persone-extra-ue | Residenza extra UE (dopo) | Entro 60 giorni dal rinnovo del permesso | 2026-10-04 (27/07/2026) | it | ok · 1 requisito, 1 passaggio |
| `cambio-residenza` | Comune di Milano | https://www.comune.milano.it/servizi/anagrafe/cambio-di-residenza | Residenza (dopo) | Cambio d'indirizzo o di Comune entro 20 giorni, online su ANPR. Non è la procedura per chi arriva dall'estero | 2026-10-04 (16/06/2026) | it | ok · 1 requisito |
| `permesso-soggiorno` | Polizia di Stato | https://www.poliziadistato.it/articolo/225 | Residenza extra UE, passaggio 1 | 8 giorni lavorativi dall'ingresso, Questura o uffici postali, 60 giorni in media | 2026-10-04 (modificata il 05/01/2024) | it | ok · 1 requisito, 1 passaggio |
| `permesso-soggiorno-come` | Polizia di Stato | https://www.poliziadistato.it/articolo/217 | Enti | Kit postale, Sportello Amico, Sportello Unico, costi | 2026-10-04 (modificata il 18/04/2019) | it | ok · usata in `enti.json` |
| `codice-fiscale` | Agenzia delle Entrate | https://www.agenziaentrate.gov.it/portale/codice-fiscale-e-tessera-sanitaria/che-cos- | Residenza extra UE, passaggio 2 | Codice fiscale dalla Questura con il permesso; primo codice per stranieri solo con appuntamento in presenza | 2026-10-04 (7 marzo 2025) | it | ok · 1 requisito, 1 passaggio |
| `yesmilano-students` | YesMilano (International Student Desk) | https://www.yesmilano.it/en/study/how-to/take-residence-milano-students | Residenza extra UE | Percorso studenti citato nel brief: correzioni, 45 giorni e visita a casa, nome sul citofono, contratto registrato, documento di chi ospita | 2026-10-04 | en | ok · 5 requisiti, 1 passaggio |
| `yesmilano-permesso` | YesMilano | https://www.yesmilano.it/en/study/how-to/residence-permit-students | Contesto | Permesso per studio, passo per passo | 2026-10-04 | en | ok · salvata, non ancora citata |
| `yesmilano-codice-fiscale` | YesMilano | https://www.yesmilano.it/en/study/how-to/get-italian-tax-code-codice-fiscale | Contesto | Codice fiscale per studenti, passo per passo | 2026-10-04 | en | ok · salvata, non ancora citata |
| `ds1702`, `ds1511`, `ds1512`, `ds1959`, `ds74` | Comune di Milano | dati.comune.milano.it | Contesto per il pannello e il pitch | Sondaggi sui servizi online, iscrizioni dall'estero, residenti stranieri | 2026-10-03 | it | ok · solo statistiche |

Nessuna fonte proviene da siti non ufficiali. YesMilano è il portale della città per studenti e lavoratori internazionali citato nel brief del Comune: le sue indicazioni sono marcate come tali nel testo dei requisiti ("secondo la guida YesMilano").

## Lacune evidenti

Diventano casi di prova per la demo e righe del pannello.

1. **Allegato A vecchio.** L'elenco dei documenti per i cittadini extra UE è un PDF creato nel 2013: chiede "originale e fotocopia" e la ricevuta dell'ufficio postale, mentre oggi la domanda si fa online con scansioni. Causa "procedura non aggiornata".
2. **Casi non coperti dall'Allegato A**: chi aspetta il primo permesso per studio (o per altri motivi) non ha un elenco di documenti. Nel catalogo è il requisito `todo` `documenti-altri-permessi`. Causa "procedura mancante".
3. **Contratto d'affitto registrato**: la pagina del Comune elenca un documento solo per i contratti non ancora registrati; YesMilano chiede contratto ed estremi di registrazione. Causa "pagina incompleta".
4. **Documento di chi ospita**: lo chiede la guida YesMilano, non la pagina del Comune.
5. **Codice fiscale dall'estero**: l'Agenzia delle Entrate dice che chi risiede all'estero può chiederlo al consolato, YesMilano (maggio 2025) dice che non è più possibile. Le fonti non sono allineate.
6. **CIE e viaggi per adulti non italiani**: la pagina del Comune lo dice solo per i minorenni. Nel catalogo è il requisito `todo` `espatrio-adulti-non-italiani`.
7. **Dati del Comune non aggiornati (`ds549`)**: la sede di Via Passerini 5 non ha Municipio, telefono né note di prenotazione e negli orari riporta ancora "lunedì 5 gennaio 2026: CHIUSO". L'ingresso da Via Pecorari 3 della sede di via Larga 12 è confermato dalla pagina `cie`. Dettagli in `data/offices.json` (`data_issues`).

Risolte rispetto al 3 ottobre: tutte le pagine sono salvate; la dichiarazione di residenza per chi arriva dall'estero si presenta **online** (non allo sportello); gli enti `questura-milano` e `agenzia-entrate` hanno un ruolo verificato con citazione.

## Come aggiungere una pagina

comune.milano.it risponde 403 agli script (Azure Application Gateway): `onevisit ingest <id> --url` non funziona da lì. Le pagine si scaricano una volta con un browser, oppure con `curl` e normali intestazioni da browser, una richiesta al secondo e verifica TLS attiva. Poi:

```bash
.venv/bin/python data/tools/clean_html.py pagina.html pulita.html   # --select article, --unescape-inner, --pdf
.venv/bin/onevisit ingest <id> --html pulita.html --url <url-ufficiale>
# oppure, senza il kit:
python data/tools/save_page.py <id> --html pagina.html --url <url-ufficiale>
```

`clean_html.py` non cambia nessuna parola: tiene solo l'elemento principale della pagina, toglie grassetti e corsivi (così le citazioni non contengono asterischi), decodifica la descrizione dei moduli online del Comune ed estrae il testo dei PDF. `onevisit ingest` scrive `data/pages/<id>.md` con intestazione (`url`, `ente`, `servizio`, `verified_at`, `content_hash`) e aggiorna la riga di `data/sources.csv`; se la pagina è cambiata elenca i requisiti da riverificare.

Poi si copia in `quote` la frase esatta per ogni requisito, si scrivono `text_it` / `text_en`, `verified_at` e `status: "verified"`, e si controlla con `python data/tools/validate.py` e `onevisit catalog-check`.
