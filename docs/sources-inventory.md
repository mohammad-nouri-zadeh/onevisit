# Inventario delle fonti ufficiali

*Storia A1. Fonte di verità: [data/sources.csv](../data/sources.csv), mantenuto dal responsabile dei dati (@mohammad-nouri-zadeh). Questo documento lo riassume e ne elenca le lacune. Regole del catalogo: [data/README.md](../data/README.md) e [ADR 0007](adr/0007-catalogo-dal-livello-dati-del-team.md). Stato al 4 ottobre 2026, sera (catalogo completo della carta d'identità, rivisto dopo la verifica dei casi).*

## Servizi coperti

| Servizio (file del catalogo) | Varianti (domande decisive) | Enti coinvolti | Verificati |
|---|---|---|---|
| Carta d'identità elettronica (`data/services/carta-identita.json`) | in quest'ordine: `residenza`: milano, domicilio-milano, altro-comune-lombardia, aire, non-residente; `motivo`: prima, rinnovo, deteriorata, chip, smarrimento-furto, pin-puk, gia-cie; `eta`: adulto, minore; `cittadinanza`: italiana, ue, extra-ue; `presenza`: sportello, domicilio-salute | Comune di Milano (anagrafe, sportello o servizio a domicilio); Ministero dell'Interno (CIE, blocco, PIN e PUK); Poste Italiane (consegna); Questura (dichiarazione di accompagno dei minori) | 143 requisiti su 146, 5 passaggi su 5 (più 2 percorsi alternativi) |
| Cambio di residenza per persone straniere provenienti dall'estero, cittadini extra UE (`data/services/iscrizione-anagrafica-extra-ue.json`) | `permesso`: permesso, ricevuta-rinnovo, ricevuta-lavoro, ricevuta-famiglia, nessuno, altro; `famiglia`: solo, con-familiari; `alloggio`: proprieta, affitto, affitto-erp, comodato, ospite, lavoro-domestico; `scadenza` | Questura di Milano (permesso) → Agenzia delle Entrate o Questura (codice fiscale) → Comune di Milano (residenza, domanda online) | 44 requisiti su 45, 6 passaggi su 6 |

Le opzioni di `permesso` sono i quattro casi dell'Allegato A del Comune (permesso valido, in rinnovo, attesa del primo permesso per lavoro subordinato, attesa del primo permesso per ricongiungimento familiare), più "non l'ho ancora chiesto" e "altro".

## Carta d'identità: copertura per aspetto

Ogni requisito della carta d'identità sta in un aspetto; la tabella dice quanti sono verificati e quali pagine citano (le citazioni sono nel catalogo e le controlla `data/tools/validate.py`). Dove le fonti tacciono c'è un requisito "da verificare" che rimanda alla pagina ufficiale.

| Aspetto | Requisiti verificati | Fonti |
|---|---|---|
| Chi può chiederla a Milano (residenza, domicilio, AIRE) | 9; da verificare: `residenza-in-corso`, `domiciliati-altri-casi` | `cie-faq-00302`, `yesmilano-id-card`, `yesmilano-work-registering-resident`, `cie`, `cie-faq-00413`, `circ-dait-054-2026` |
| Prenotazione e check-in | 9 | `ds549`, `cie-faq-00578`, `cie-faq-03767`, `cie`, `cie-faq-03790`, `prenotazione`, `cie-faq-03783`, `cie-faq-00307` |
| Documenti e identificazione | 8; da verificare: `primo-permesso-in-attesa` | `cie`, `cie-ministero`, `cie-faq-00564` |
| Fototessera | 8 | `cie`, `cie-ministero`, `cie-faq-00308`, `cie-ministero-foto`, `cie-faq-00414` |
| Costo | 2 | `cie`, `cie-faq-04023` |
| Allo sportello (impronte, contatti, donazione, dichiarazioni) | 9 | `cie-ministero`, `cie-ministero-impronte`, `cie`, `cie-faq-00542`, `cie-donazione-organi`, `circ-dait-081-2023` |
| Rinnovo e carte cartacee | 9 | `cie-faq-00405`, `cie-faq-00303`, `cie-faq-04180`, `cie`, `cie-ministero-faq` |
| Furto e smarrimento (anche all'estero) | 9 | `cie`, `pds-denunce-online`, `cie-ministero-faq`, `cie-ministero-furto-smarrimento`, `cie-ministero-viaggiare`, `cie-faq-00580`, `cie-faq-00355` |
| Carta rovinata e chip guasto | 5 | `cie`, `cie-faq-00418`, `cie-faq-00310`, `cie-faq-00409` |
| Senza appuntamento: ticket e orari | 2 | `cie` |
| Urgenze | 6 | `cie`, `cie-faq-00306` |
| Carta d'identità provvisoria | 7 | `cie`, `cie-faq-04349`, `cie-provvisoria-modulo` |
| Minorenni | 17 | `cie`, `cie-faq-00302`, `cie-faq-00354`, `cie-faq-00353`, `pds-espatrio-minori`, `cie-ministero-minori`, `cie-ministero-attiva` |
| Cittadinanza e viaggi | 4 | `circ-dait-004-2017`, `cie-faq-00472`, `rettifica-dati-stranieri`, `circ-dait-060-2026` |
| Servizio a domicilio per motivi di salute | 10 | `cie-domicilio-salute`, `cie-faq-00392`, `cie-faq-04024`, `cie`, `cie-domicilio-modulo`, `cie-faq-04028` |
| Consegna e ricevuta | 13 | `cie`, `cie-ministero-spedizione`, `cie-faq-00471`, `cie-faq-00407`, `cie-ministero-ricevuta`, `cie-faq-00304` |
| Durata | 5 | `cie-faq-00517`, `cie` |
| PIN, PUK e identità digitale | 10 | `cie-ministero-pin-puk`, `cie-ministero-credenziali`, `cie`, `cie-ministero-recupero-puk`, `cie-faq-00470`, `cie-faq-04366` |
| Ho già la CIE (cambio di indirizzo o stato civile) | 1 | `cie-faq-00518` |

Chi vede cosa: tutto ciò che riguarda la richiesta a Milano vale solo per chi risponde `residenza` milano, domicilio-milano o aire; chi è residente in un altro Comune lombardo o non è ancora residente vede solo dove andare (niente prenotazione, costo o consegna). Prenotazione, check-in, costo allo sportello, eccezioni senza appuntamento e carta provvisoria valgono solo per `presenza` sportello; il servizio a domicilio solo per domicilio-salute. Testimoni, impronte allo sportello e donazione sono per gli adulti; i minorenni hanno le loro regole. I viaggi (15 e 5 giorni prima, carta provvisoria all'estero, E.T.D. del Consolato) solo per chi ha cittadinanza italiana. La carta provvisoria sostituisce una carta precedente, quindi non compare per la prima carta. Le risposte `altro-comune-lombardia` e `non-residente` portano a uno stop (nessun link di prenotazione), `domicilio-salute` al modulo online del servizio a domicilio, `pin-puk` alle prenotazioni del duplicato e del cambio contatti: sono gli `option_routes` delle domande, e `validate.py` controlla che ogni link sia nella pagina salvata della sua fonte.

Nessuna pagina nuova è servita per la revisione della sera del 4 ottobre: ogni correzione cita pagine già salvate.

## Fonti

| id | Ente | URL | Servizio | Cosa copre | Data | Lingua | Stato |
|---|---|---|---|---|---|---|---|
| `ds549` | Comune di Milano | https://dati.comune.milano.it/dataset/ds549-sedi-dei-servizi-anagrafici | Entrambi | Sedi, orari, regole di prenotazione e ticket per le urgenze (`su-appuntamento`) | 2026-10-03 (risorsa del 2026-01-28) | it | ok |
| `cie` | Comune di Milano | https://www.comune.milano.it/servizi/anagrafe/carta-d-identita | Carta d'identità | Documenti, casi (rinnovo, smarrimento, minori, extra UE, AIRE, domiciliati), costo 22,20 euro, consegna, eccezioni senza appuntamento, carta provvisoria, 70 anni, PIN e PUK, donazione di organi | 2026-10-04 (pagina aggiornata il 02/10/2026; riscaricata due volte la sera del 4 ottobre: identica) | it | ok · 55 requisiti, 1 passaggio, 1 percorso, i link di prenotazione per PIN/PUK e contatti |
| `cie-ministero` | Ministero dell'Interno | https://www.cartaidentita.interno.gov.it/richiedi/rilascio-e-rinnovo-in-italia/ | Carta d'identità | Cosa succede allo sportello, testimoni, consegna in 6 giorni lavorativi (la validità per gli adulti ora cita KA-00517: la pagina del Ministero la basa su un regolamento UE dichiarato invalido) | 2026-10-04 | it | ok · 4 requisiti, 2 passaggi |
| `cie-faq-<numero KA>` (77 salvati, 35 usati) | Comune di Milano (centro di supporto) | https://servizicrm.comune.milano.it/centro-supporto/KA-<numero>/… | Carta d'identità | Domande e risposte "Anagrafe / Carta d'identità", ciascuna datata (dal 31/08/2025 al 02/10/2026): chi può chiederla a Milano, foto, permesso scaduto, neonati, un solo genitore, viaggi urgenti e atti notarili, chip, check-in, riprogrammazione, consegna, servizio a domicilio, carta provvisoria, nuovi cittadini, 70 anni | 2026-10-04 | it | ok · 47 requisiti, 1 passaggio; `cie-faq-00393` per il requisito `todo` sul primo permesso |
| `cie-domicilio-salute`, `cie-domicilio-modulo` | Comune di Milano | https://www.comune.milano.it/servizi/anagrafe/servizi-anagrafici-a-domicilio-per-motivi-di-salute e il modulo online https://formshd3.comune.milano.it/rwe2/module_preview.jsp?MODULE_TAG=SERVIZIO_ANAGRAFICO_DOMICILIO | Carta d'identità (a domicilio) | Per chi è ricoverato, in RSA o allettato: modulo con SPID o CIE, certificato medico, documento, delega, ricontatto da 02.884 non prima di 15 giorni lavorativi | 2026-10-04 (14/09/2026) | it | ok · 5 requisiti, 1 percorso, il link del modulo online |
| `cie-donazione-organi`, `cie-provvisoria-modulo`, `rettifica-dati-stranieri` | Comune di Milano | pagina della donazione di organi, modulo PDF della carta provvisoria, pagina della rettifica dei dati per stranieri | Carta d'identità | Cambiare idea sulla donazione; dichiarazione per la carta provvisoria; dati diversi da passaporto o permesso | 2026-10-04 | it | ok · 1 requisito ciascuna |
| `cie-ministero-*` (14 salvate, 12 usate) | Ministero dell'Interno | https://www.cartaidentita.interno.gov.it/ (minori, foto, impronte, spedizione, ricevuta, furto e smarrimento, assistenza, PIN e PUK, recupero PUK, credenziali, attivazione, viaggiare; per contesto: caratteristiche, la carta) | Carta d'identità | Regole nazionali che la pagina del Comune richiama | 2026-10-04 | it | ok · 18 requisiti, 1 passaggio |
| `circ-dait-004-2017`, `circ-dait-054-2026`, `circ-dait-060-2026`, `circ-dait-081-2023` (e `circ-dait-008-2026`, salvata) | Ministero dell'Interno (circolari, PDF) | https://dait.interno.gov.it/documenti/… | Carta d'identità | La CIE è documento di viaggio solo per i cittadini italiani; AIRE in qualsiasi Comune; 3 anni per i richiedenti asilo; dichiarazione dei genitori per l'espatrio | 2026-10-04 | it | ok · 1 requisito ciascuna |
| `pds-denunce-online`, `pds-espatrio-minori` | Polizia di Stato | https://www.poliziadistato.it/articolo/denunce-online, https://www.poliziadistato.it/articolo/passaporto-per-i-minori-e-espatrio | Carta d'identità | Denuncia di smarrimento online (si entra con SPID o CIE); dichiarazione di accompagno in Questura | 2026-10-04 | it | ok · 2 requisiti e 1 |
| `yesmilano-id-card`, `yesmilano-work-registering-resident` (e 2 guide salvate per contesto) | YesMilano | https://studyandwork.yesmilano.it/en/study/how-to/id-card, https://studyandwork.yesmilano.it/en/work/getting-started-guide/registering-resident-milano | Carta d'identità | Prima la residenza; la residenza non è il permesso di soggiorno | 2026-10-04 | en | ok · 1 requisito ciascuna |
| `sedi-anagrafiche`, `cie-foto-requisiti`, `cie-cabine-foto`, `oggetti-smarriti`, 6 notizie del Comune | Comune di Milano | comune.milano.it | Contesto e pannello | Orari delle sedi (i ticket per urgenze fino a mezz'ora prima della chiusura, citati nel testo di `senza-appuntamento-orario`), guida foto del 2007, elenco cabine del 2022 non aggiornato, campagna per le carte cartacee, priority lane (2024), detenuti (2023) | 2026-10-04 | it | ok · salvate, non citate |
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
6. **CIE e viaggi per adulti non italiani**: la pagina del Comune lo dice solo per i minorenni. Dal 4 ottobre il requisito `espatrio-adulti-non-italiani` è verificato con la circolare del Ministero n. 4/2017 ("per i soli cittadini italiani"); lo conferma la guida YesMilano.
7. **Dati del Comune non aggiornati (`ds549`)**: la sede di Via Passerini 5 non ha Municipio, telefono né note di prenotazione e negli orari riporta ancora "lunedì 5 gennaio 2026: CHIUSO". L'ingresso da Via Pecorari 3 della sede di via Larga 12 è confermato dalla pagina `cie`. Dettagli in `data/offices.json` (`data_issues`).
8. **CIE, fonti non allineate** (tutte in `unknowns_it` di `carta-identita.json`): copricapo nella foto ("capo scoperto" per il Comune, ammesso per motivi religiosi, culturali o medici dal Ministero); orari senza appuntamento (8:30-15:00 sulla pagina della CIE, ticket fino a mezz'ora prima della chiusura sulla pagina delle sedi e in `ds549`); documenti per il viaggio urgente diversi tra gli articoli su smarrimento, furto e carta rovinata; durata illimitata dai 70 anni ("dal", "dopo" o "prima" del 30 luglio 2026); donazione di organi facoltativa o con modulo da firmare, e due e-mail diverse per cancellarla; servizio a domicilio con certificato di impossibilità "di muoversi" o "in modo permanente"; consegna in 6 giorni lavorativi (Comune) o dieci (YesMilano); elenco delle cabine foto del 2022 con una sede che non esiste più; pagina inglese della CIE che traduce male la regola dei 70 anni.
9. **CIE, cosa nessuna fonte dice**: se si può chiedere la carta mentre la domanda di residenza è in verifica (requisito `todo` `residenza-in-corso`); se basta la ricevuta del primo permesso di soggiorno (requisito `todo` `primo-permesso-in-attesa`); se chi abita a Milano ed è residente fuori dalla Lombardia può fare a Milano la prima carta, sostituire una carta persa o il chip guasto (le fonti parlano solo del rinnovo: requisito `todo` `domiciliati-altri-casi`); come firma l'assenso per l'espatrio del minore un genitore che vive all'estero, e cosa serve se un genitore lo nega; documenti in più per i cittadini UE; iscritti all'AIRE di altri Comuni a Milano; carta di credito allo sportello; costo di un duplicato; come si annulla un appuntamento; quali sedi rilasciano la CIE; margine del check-in; aiuto in altre lingue allo sportello; dati stampati sbagliati; adulto con tutore allo sportello; chi ha solo la dimora temporanea; persone senza dimora o detenute.

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
