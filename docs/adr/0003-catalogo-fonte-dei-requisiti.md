# 0003 · Il catalogo come unica fonte dei requisiti

- **Stato:** accettata
- **Data:** 2026-10-03
- **Storia:** A2, C3, C4

## Contesto

Un chatbot generico risponde "a memoria" e può inventare un documento, un costo o un orario. Un requisito sbagliato provoca esattamente il viaggio a vuoto che OneVisit vuole evitare, e nella PA una risposta inventata è un danno di fiducia.

## Decisione

Claude decide quale servizio e quale variante si applicano e come spiegarli, ma prende requisiti, sedi, orari e costi solo dagli strumenti che leggono il catalogo. Ogni affermazione porta una citazione `[fonte: <source_id>]`. Solo i requisiti con `status: "verified"` arrivano al cittadino. Il validatore `validate_reply` blocca le risposte con fonti inesistenti, senza citazioni quando il turno ha usato fatti del catalogo, o con parole di idoneità ("idoneo", "in regola", "garantito", "eligible", ...). Dopo una rigenerazione fallita l'assistente manda un messaggio di cortesia con il link ufficiale.

## Conseguenze

- Quando il catalogo non sa, l'assistente dice che non sa e rimanda alla pagina ufficiale: è un comportamento voluto e va mostrato nella demo.
- La qualità dell'assistente dipende dalla copertura del catalogo: oggi pochi requisiti sono verificati.
- Il catalogo diventa un artefatto da mantenere, con una persona responsabile (ADR 0007).

## Alternative considerate

- Ricerca libera sulle pagine (RAG puro): più copertura, ma nessuna garanzia che la frase citata dica davvero il requisito.
- Fidarsi del modello con un prompt prudente: non verificabile.
