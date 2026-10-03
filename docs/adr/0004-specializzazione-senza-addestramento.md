# 0004 · Specializzazione senza addestramento sui cittadini

- **Stato:** accettata
- **Data:** 2026-10-03
- **Storia:** C10, C13, B11

## Contesto

Vogliamo che il sistema diventi più preciso grazie agli esiti degli appuntamenti. La via ovvia sarebbe riaddestrare il modello sulle conversazioni, ma per il GDPR è una finalità diversa da quella del servizio (art. 5), le conversazioni sono difficili da anonimizzare e un modello addestrato non permette di cancellare il contributo di una persona.

## Decisione

Nessun addestramento né fine-tuning su dati dei cittadini. La specializzazione passa da tre strade controllabili:

1. le correzioni approvate dalla redazione entrano nel catalogo come `ApprovedCorrection` e compaiono nella checklist con `origin="approved_correction"`;
2. scenari di valutazione sintetici (`data/eval/*.yaml`, comando `onevisit eval`) verificano ogni modifica dell'agente;
3. le metriche indicano quali fonti e istruzioni migliorare.

## Conseguenze

- Ogni miglioramento è tracciabile, reversibile e ha un responsabile umano.
- Le conversazioni non vengono salvate come testo: non c'è un corpus da proteggere.
- Il prompt di sistema è versionato nel repository.

## Alternative considerate

- Fine-tuning su conversazioni anonimizzate: costoso, lento da verificare, incompatibile con il diritto alla cancellazione.
