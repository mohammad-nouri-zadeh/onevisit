# 0006 · Contenuto minimo delle notifiche

- **Stato:** accettata
- **Data:** 2026-10-03
- **Storia:** B5, B7, C6, C7

## Contesto

Un SMS compare sullo schermo bloccato del telefono, dove chiunque può leggerlo; l'oggetto di un'email compare nelle anteprime. Nominare la pratica ("denuncia di smarrimento", "permesso di soggiorno") rivela informazioni sulla persona.

## Decisione

SMS ed email contengono solo due variabili: i giorni mancanti all'appuntamento e un link personale firmato (`LinkSigner`) che apre la checklist o la domanda sull'esito. Mai il nome del servizio, della sede o del documento. I testi stanno nei template (`templates/sms/`, `templates/email/`) in italiano e inglese; un SMS resta entro due segmenti. Il link è casuale, scade alla fine del follow-up e non richiede un account. `core.notifications` non contiene testo.

## Conseguenze

- Il fornitore SMS o email vede solo numero/indirizzo, giorni e link.
- Il messaggio è meno informativo da solo: il valore sta dietro il link.
- Ogni messaggio permette la revoca (STOP o link ai consensi).

## Alternative considerate

- Promemoria con l'elenco dei documenti nell'SMS: più comodo, ma espone dati personali e supera i due segmenti.
