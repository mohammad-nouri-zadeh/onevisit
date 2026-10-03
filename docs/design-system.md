# Design system

Il design system di OneVisit sta in un pacchetto condiviso, [`libs/onevisit_ui`](../libs/onevisit_ui), usato dalle tre applicazioni: web chat dei cittadini, pannello del Comune e gateway (telefono demo e pagine di risposta).

## Origine

Viene dal prototipo di design del team: `design/onevisit-prototype.html` sul branch `momo/streamlit-demo` (commit "Restyle the design prototype: monochrome, language menu"). Il prototipo è una pagina statica con l'app del cittadino in un telefono e il pannello come registro; qui gli stessi token e componenti diventano un foglio di stile servito dalle app vere.

## Principi

- **Monocromatico.** Inchiostro, grafite, argento e carta. Nessun colore porta significato da solo: gli stati si leggono da testo, forma (pallino pieno o tratteggiato) e posizione. Il rosso (`--alert`) serve solo per errori e azioni distruttive.
- **Calmo per il cittadino, denso per il personale.** Il cittadino vede una colonna sola, bolle di chat, una checklist con segni tondi e la fonte in carattere monospaziato sotto ogni requisito. Il personale vede un registro con righe sottili e numeri grandi.
- **La fonte è sempre visibile.** Le citazioni (`.cite`, `.src`) usano IBM Plex Mono: si riconoscono a colpo d'occhio come "da dove viene questa informazione".
- **Niente terze parti nelle pagine dei cittadini.** Font, htmx e Chart.js sono serviti in locale da `/ui/`: nessun IP o user agent va a Google Fonts, unpkg o jsDelivr.
- **Accessibile.** Contrasto AA, focus visibile, uso da tastiera, tema scuro automatico, movimento ridotto rispettato.

## Token

| Token | Chiaro | Scuro | Uso |
|---|---|---|---|
| `--paper` | `#EDEEF0` | `#0C0C0E` | Fondo pagina |
| `--sheet` | `#FFFFFF` | `#17181B` | Superfici (schede, tabelle, campi) |
| `--ink` | `#111214` | `#F2F2F3` | Testo, pulsanti primari, segni pieni |
| `--graphite` | `#4A4D55` | `#B7B9C0` | Testo secondario |
| `--pewter` | `#5E626B` | `#8B8E97` | Testo terziario, note, fonti |
| `--silver` | `#C6C8CE` | `#3A3C42` | Righe e bordi |
| `--mist` | `#E4E5E9` | `#24252A` | Riempimenti, bolle dell'assistente |
| `--frost` | bianco 72% | grafite 72% | Barre "vetro" con sfocatura |
| `--alert` | `#8A1C1C` | `#F2A3A3` | Solo errori e cancellazioni |
| `--sans` | Titillium Web | | Testo |
| `--mono` | IBM Plex Mono | | Fonti, identificativi, numeri di dataset |
| `--r`, `--r-lg`, `--pill` | 14px, 22px, 999px | | Raggi |

**Unica modifica rispetto al prototipo:** `--pewter` passa da `#6E727C` a `#5E626B`. Il valore originale su `--paper` dava un contrasto di circa 4,1:1, sotto la soglia AA per il testo piccolo; il nuovo arriva a circa 4,8:1. Un test (`libs/onevisit_ui/tests`) lo verifica.

## Componenti

| Area | Classi |
|---|---|
| Struttura | `.wrap` (`.wide` per il pannello), `.top`, `.bar` con `.titles .t .s`, `.nav` (pillole, `aria-current="page"`), `.seg`, `.lang` |
| Superfici | `.card`, `.office`, `.facts`, `.callout`, `.notice`, `.error`, `.badge` (`.ink`, `.line`, `.dashed`), `.example` |
| Azioni | `.btn` (`.block`, `.line`, `.small`, `.danger`), `.opts` / `.opt` (risposte rapide), `.actions` |
| Moduli | campi, `fieldset`/`legend`, `.form`, `.choices` / `.choice`, `.toggle` / `.switch` |
| Chat | `.msgs`, `.msg.ai`, `.msg.me`, `.who`, `.cite`, `.composer` |
| Checklist | `.count`, `.ticks i.on`, `.list`, `.item.ok` / `.item.todo`, `.mark`, `.what`, `.src`, `.done` |
| Telefono demo | `.phone`, `.screen`, `.tabbar` |
| Pannello | `.stats` / `.stat .n .l`, `.cols`, `.sec`, `.row`, `.rep .n .kind .desc`, `.state`, `.insufficient`, `.draft`, `.foot`, tabelle a registro, `.chart`, `.info` |

## Uso in un'applicazione

```python
from fastapi.staticfiles import StaticFiles
import onevisit_ui

app.mount(onevisit_ui.MOUNT_PATH, StaticFiles(directory=onevisit_ui.STATIC_DIR), name="ui")
```

```html
<link rel="stylesheet" href="/ui/fonts.css">
<link rel="stylesheet" href="/ui/onevisit.css">
<script src="/ui/vendor/htmx.min.js" defer></script>
<!-- solo nel pannello -->
<script src="/ui/vendor/chart.umd.min.js" defer></script>
```

I grafici del pannello leggono i colori dai token con `getComputedStyle` e distinguono le serie con tratteggi e forme dei punti, non con il colore. Ogni grafico ha la sua tabella equivalente.

## Licenze

htmx 2.0.4 (0BSD), Chart.js 4.4.1 (MIT), Titillium Web e IBM Plex Mono (SIL Open Font License 1.1). Dettagli in `libs/onevisit_ui/src/onevisit_ui/static/vendor/NOTICE.md`.
