# Video script (2:00)

*Story E1. Spoken in English, Italian subtitles (`docs/video/subtitles.srt`, story E2). Recorded at 1920x1080 from the demo environment (`make demo`). Only synthetic data on screen: the test phone number `+39 333 000 0000`, emails `@example.org`, invented personas. Shot-by-shot details: [storyboard.md](storyboard.md). Read every line aloud with a stopwatch before recording; the word counts below assume about 150 words per minute.*

| Time | Scene | Shot | Words |
|---|---|---|---|
| 0:00–0:15 | 1 · The problem | Screen: title card, then City data | ~35 |
| 0:15–0:55 | 2 · Daniel plans his visit | Screen: web chat (localhost:8000) | ~95 |
| 0:55–1:10 | 3 · The reminder and the check | Phone: `/demo/phone`, then checklist | ~38 |
| 1:10–1:40 | 4 · Marco fixes the City's page | Screen: panel (localhost:8001) | ~75 |
| 1:40–1:55 | 5 · Where Claude works, and privacy | Screen: one summary slide | ~38 |
| 1:55–2:00 | 6 · Closing line | Screen: logo | ~12 |

---

## Scene 1 · The problem (0:00–0:15, 15 s)

**Spoken (EN):**
> You book an appointment at the registry office. You wait weeks. You get to the desk, and something is missing. You go home, and book again. And the slot you used? Someone else needed it.

**Italian subtitle:**
> Prenoti all'anagrafe. Aspetti settimane. Arrivi allo sportello e manca qualcosa. Torni a casa e prenoti di nuovo. E quello slot serviva a qualcun altro.

**On screen:** "One appointment. One closed procedure." then: "Foreign citizens: 42.1% said the online residence service helped little or not at all (City of Milan survey ds1702, 2022)".

## Scene 2 · Daniel plans his visit (0:15–0:55, 40 s)

**Spoken (EN):**
> Meet Daniel, an engineer from Brazil who just moved to Milan for work. He writes to OneVisit in English, in his own words. Claude understands the case: registering residence as a non-EU citizen. It asks only the questions that change the answer, then lays out the order: Questura first for the residence permit, Agenzia delle Entrate for the tax code, then the City registry office. Every requirement cites an official source, and the Italian terms stay next to the English. OneVisit doesn't book for him: it sends him to the City's booking page. Then it asks how he wants reminders. Daniel picks SMS.

**Italian subtitle:**
> Daniel è un ingegnere brasiliano appena arrivato a Milano per lavoro. Scrive a OneVisit in inglese, con parole sue. Claude capisce il caso: iscrizione anagrafica di un cittadino extra-UE. Fa solo le domande che cambiano la risposta, poi indica l'ordine: prima la Questura per il permesso di soggiorno, poi l'Agenzia delle Entrate per il codice fiscale, poi l'anagrafe del Comune. Ogni requisito cita una fonte ufficiale, con i termini italiani accanto all'inglese. OneVisit non prenota al posto suo: lo manda alla pagina di prenotazione del Comune. Poi chiede come vuole i promemoria. Daniel sceglie l'SMS.

**On screen:** chat bubbles; highlight "[fonte: ...]" citations; caption "Facts only from verified official sources"; caption "No name, no tax code, no documents asked".

## Scene 3 · The reminder and the check (0:55–1:10, 15 s)

**Spoken (EN):**
> Three days before the appointment, the SMS arrives. It never names the procedure: just the days left and a personal link. The check finds it: a document issued abroad needs a translation. Daniel gets it done in time.

**Italian subtitle:**
> Tre giorni prima arriva l'SMS. Non nomina mai la pratica: solo i giorni mancanti e un link personale. Il controllo lo trova: un documento rilasciato all'estero va tradotto. Daniel lo fa in tempo.

**On screen:** phone frame with the SMS; caption "Demo mode: 1 day = 60 seconds"; checklist item highlighted "Translation of documents issued abroad".

## Scene 4 · Marco fixes the City's page (1:10–1:40, 30 s)

**Spoken (EN):**
> Now the City's side. Marco works on the City website. His panel shows what really happens at the desks. Claude has grouped the outcomes and found a gap: a missing procedure for non-EU families, fourteen cases in a month, and no page covers it. The draft correction is already written, in Italian, plain Italian and English. Marco edits it and approves. From then on, the assistant uses it, and the panel measures the effect: first-visit closures, four weeks before and four weeks after.

**Italian subtitle:**
> Ora il lato del Comune. Marco lavora alla redazione web. Il suo pannello mostra cosa succede davvero agli sportelli. Claude ha raggruppato gli esiti e trovato una lacuna: una procedura mancante per le famiglie extra-UE, quattordici casi in un mese, e nessuna pagina la copre. La bozza di correzione è già scritta, in italiano, in italiano facile e in inglese. Marco la modifica e la approva. Da quel momento l'assistente la usa, e il pannello ne misura l'effetto: pratiche chiuse al primo appuntamento, quattro settimane prima e quattro dopo.

**On screen:** "Synthetic data" badge; gap card "Procedura mancante · 14 cases"; "Approve" click; before/after chart; caption "Aggregates only, cells under 5 cases hidden".

## Scene 5 · Where Claude works, and privacy (1:40–1:55, 15 s)

**Spoken (EN):**
> Claude works at every step: understanding, routing, checklists, diagnosing gaps, drafting fixes. People decide: the desk officer, the data owner, the editors. No identity data, contacts optional, free text never stored.

**Italian subtitle:**
> Claude lavora in ogni fase: capire, indirizzare, checklist, diagnosi delle lacune, bozze di correzione. Decidono le persone: l'operatore allo sportello, chi cura i dati, la redazione. Nessun dato di identità, contatti facoltativi, testo libero mai salvato.

**On screen:** the README table "Where does Claude work when someone uses this?" condensed into two columns; models `claude-sonnet-5-5` and `claude-haiku-4-5-20251001`.

## Scene 6 · Closing line (1:55–2:00, 5 s)

**Spoken (EN):**
> The City doesn't have to guess where it goes wrong. The appointments tell it.

**Italian subtitle:**
> Il Comune non deve chiedersi dove sbaglia: glielo dicono gli appuntamenti.

**On screen:** "OneVisit · Claude Impact Lab Milano · 3 October 2026" and the repository URL.

---

## Recording notes

- Record the demo path once end to end (story D4) and cut; do not stage fake screens.
- Turn off desktop notifications; use a clean browser profile; no real phone notifications in shot.
- If the real SMS is shown, the trial account prefix appears: keep it, it's honest.
- Numbers in Scene 4 come from `make seed-demo` (fixed seed 42); check them on screen before recording and adjust the spoken "fourteen" if the panel shows another count.
- Music, if any, royalty-free. Export MP4 H.264 plus `subtitles.srt`.
