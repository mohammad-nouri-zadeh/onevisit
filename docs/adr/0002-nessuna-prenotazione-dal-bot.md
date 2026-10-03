# 0002 · Nessuna prenotazione da parte del bot

- **Stato:** accettata
- **Data:** 2026-10-03
- **Storia:** B4

## Contesto

Prenotare un appuntamento all'anagrafe richiede di identificarsi. Se il bot prenotasse al posto del cittadino, riceverebbe dati di identità e credenziali che non gli servono per nessun'altra funzione e diventerebbe un punto di raccolta di dati sensibili.

## Decisione

L'assistente spiega come prenotare, cosa preparare e rimanda al link ufficiale del Comune. Non prenota, non chiede credenziali né numero di prenotazione. Dopo la prenotazione il cittadino può comunicare, se vuole, solo data, ora e sede dell'appuntamento (B4) per ricevere promemoria.

## Conseguenze

- OneVisit non tocca mai SPID, CIE o credenziali; il perimetro privacy resta piccolo.
- Il cittadino fa un passaggio in più fuori dal bot: va spiegato bene, nella sua lingua.
- Non conosciamo la prenotazione reale: la data dell'appuntamento è dichiarata dal cittadino.
- In futuro l'aggancio giusto è la conferma email già inviata dal sistema di prenotazione del Comune, non il bot.

## Alternative considerate

- Prenotazione tramite il bot con delega: scartata per i dati di identità e per il rischio di errore su un atto con effetti per la persona.
