# Storyboard (2:00)

*Story E1. Spoken text in full: [script.md](script.md). Every shot from the demo environment (`make demo`), 1920x1080, synthetic data only.*

| # | Time | Duration | Shot | What we see | On-screen text | Audio |
|---|---|---|---|---|---|---|
| 1a | 0:00–0:07 | 7 s | Screen, title card | Dark background, a calendar with a crossed-out appointment | "One appointment. One closed procedure." | VO scene 1, first half |
| 1b | 0:07–0:15 | 8 s | Screen, data card | Bar: foreign 42.1% vs Italian 28.2% "helped little or not at all" | "City of Milan survey ds1702, 2022" | VO scene 1, second half |
| 2a | 0:15–0:25 | 10 s | Screen, web chat localhost:8000 | Daniel's first message in English, Claude's summary of the case and one deciding question with buttons | "Daniel (persona, invented)" | VO scene 2 |
| 2b | 0:25–0:40 | 15 s | Screen, web chat, zoom on the answer | Enti in order: Questura → Agenzia delle Entrate → Comune; Italian terms in brackets; `[fonte: ...]` citations highlighted | "Facts only from verified official sources" | VO scene 2 |
| 2c | 0:40–0:48 | 8 s | Screen, web chat | Link to the City's booking page; Daniel enters date and office | "OneVisit never books for you" | VO scene 2 |
| 2d | 0:48–0:55 | 7 s | Screen, contact form | Channel choice: SMS selected, number `+39 333 000 0000`, separate consent boxes | "Optional. No name, no tax code" | VO scene 2 |
| 3a | 0:55–1:02 | 7 s | Phone: gateway localhost:8002/demo/phone in a phone frame (or real phone filmed) | SMS: days left + personal link, no procedure name | "Demo mode: 1 day = 60 s" | VO scene 3 |
| 3b | 1:02–1:10 | 8 s | Phone/screen: checklist `/c/{token}` | Item by item; "documents issued abroad: translation" flagged, with source and date | "Checked against official sources" | VO scene 3 |
| 4a | 1:10–1:18 | 8 s | Screen, panel localhost:8001 overview | First-visit rate by service, gaps by cause; "Synthetic data" badge | "Marco · City web team (persona)" | VO scene 4 |
| 4b | 1:18–1:28 | 10 s | Screen, gap detail `/gaps/{id}` | "Procedura mancante", case count, recipient, Claude's draft in it / italiano facile / en | "Drafted by Claude, approved by a person" | VO scene 4 |
| 4c | 1:28–1:33 | 5 s | Screen, gap detail | Marco edits one word, clicks Approve | — | VO scene 4 |
| 4d | 1:33–1:40 | 7 s | Screen, `/interventions` | Before/after chart: 4 weeks before vs 4 after | "Cells under 5 cases hidden" | VO scene 4 |
| 5 | 1:40–1:55 | 15 s | Screen, one slide | Two columns: "Claude does" / "A person confirms"; models; privacy line | "No identity data · contacts optional · free text never stored" | VO scene 5 |
| 6 | 1:55–2:00 | 5 s | Screen, logo card | OneVisit, event, repo URL | "The appointments tell it." | VO scene 6, then silence |

Total: 2:00.

## Assets to prepare

- Phone frame for `/demo/phone` (browser at 390x844, or the real test phone filmed).
- Slide for scene 5, taken from the README section "Where does Claude work when someone uses this?".
- Data card for scene 1 from `data/context/residence-2022-helped-by-group.csv`.
- Subtitles `docs/video/subtitles.srt` from the Italian lines in the script.
