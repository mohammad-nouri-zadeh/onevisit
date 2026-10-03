# 0005 · Canali web, email e SMS dietro un gateway unico

- **Stato:** accettata
- **Data:** 2026-10-03
- **Storia:** C5, C6, C7

## Contesto

La conversazione completa avviene nella web chat, ma la web chat non può raggiungere il cittadino per i promemoria. Email e SMS servono a ricontattarlo. I fornitori cambieranno: in produzione il Comune sceglierà il fornitore SMS e userà il suo SMTP.

## Decisione

Tre soli canali: web chat, email, SMS. Un gateway normalizza i messaggi in arrivo (`InboundMessage`) e in uscita (`OutboundMessage`); ogni adattatore dichiara le sue capacità (`ChannelCapabilities`: pulsanti, lunghezza massima). L'agente sa cosa il canale permette, non quale canale è. SMS e email sono dietro interfacce (`SmsProvider`, `EmailSender`) con un'implementazione reale (Twilio, SMTP) e una finta per test e demo (`/demo/phone`, Mailpit).

## Conseguenze

- Cambiare fornitore o aggiungere un canale non tocca l'agente.
- Via SMS si accettano solo risposte brevi (1, 2, 3, STOP, AIUTO); per il testo libero si rimanda alla web chat con un link personale.
- App IO resta da valutare con il Comune: indirizza i messaggi con il codice fiscale, che OneVisit evita.

## Alternative considerate

- WhatsApp o Telegram: fornitori extra-UE, account personale obbligatorio, termini non adatti alla PA.
- Un adattatore diretto per ogni canale dentro l'agente: accoppiamento forte e test difficili.
