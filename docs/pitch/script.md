# Pitch di 2 minuti: testo da leggere

Struttura **SPIN** (Situazione, Problema, Implicazione, Need-payoff). Serve a convincere: prima fa sentire il costo del problema, poi mostra il valore. Dal modello STAR prendiamo solo l'"Azione" concreta, cioè le schermate del prodotto vero.

Circa 290 parole: 1:56 di parlato più due pause da 2 secondi, a circa 150 parole al minuto. I tempi sono cumulativi.

| # | Slide | Fase | Tempo |
|---|---|---|---|
| 1 | La testimonianza e il team | Aggancio | 0:00–0:10 |
| 2 | Un residente su cinque è straniero | S · Situazione | 0:10–0:20 |
| 3 | 12 su 14 bocciano l'esperienza | P · Problema | 0:20–0:39 |
| 4 | Ogni visita ripetuta costa a tutti (+ pausa) | I · Implicazione | 0:39–0:54 |
| 5 | Capire, prepararsi, arrivare pronti | N · Valore per il cittadino | 0:54–1:10 |
| 6 | Non una semplice chat con un agente | N · Dove ci differenziamo | 1:10–1:27 |
| 7 | KPI: cosa correggere, e quanto vale | N · Valore per il Comune | 1:27–1:46 |
| 8 | Il nostro spunto (pausa + chiusura) | Chiusura | 1:46–2:00 |

## 1 · Aggancio (0:00–0:10)

> «Ho dovuto prendere tre appuntamenti di quindici minuti per mettere a posto la mia residenza.» Siamo OneVisit: due italiani e tre arrivati dal mondo. Vogliamo che ne basti uno.

## 2 · Situazione (0:10–0:20)

> A Milano più di un residente su cinque è straniero. Solo nel 2024, quasi ventimila persone si sono iscritte all'anagrafe arrivando dall'estero.

## 3 · Problema (0:20–0:39)

> Abbiamo chiesto a quattordici studenti stranieri com'è ottenere un documento dal Comune. Dodici su quattordici: negativo. Nessuno positivo. Anche il sondaggio del Comune, nel 2022: il servizio online di residenza ha aiutato poco o niente il quarantadue per cento degli stranieri che hanno risposto.

## 4 · Implicazione (0:39–0:54)

> Tre visite invece di una: due slot sprecati. Anche solo per quattromilacinquecento persone, fino a novemila appuntamenti l'anno tolti ad altri cittadini. E i sondaggi dicono quanto non funziona, non quale pagina ha causato l'errore.

*(pausa di 2 secondi)*

## 5 · Valore per il cittadino (0:54–1:10)

> OneVisit in tre passi. Capire: il cittadino scrive nella sua lingua e Claude gli dice cosa portare, solo con requisiti verificati sulle fonti ufficiali. Prepararsi: riceve un SMS o un'email con il link alla sua lista. Arrivare pronti: allo sportello con quello che serve.

## 6 · Dove ci differenziamo (1:10–1:27)

> Perché non una semplice chat? Una chat risponde a memoria: se sbaglia, nessuno lo sa. OneVisit cita la fonte di ogni requisito, e se non sa, lo dice. Non dice mai «sei in regola»: decide l'operatore. E una chat finisce lì. OneVisit, dopo l'appuntamento, chiede com'è andata.

## 7 · Valore per il Comune: i KPI (1:27–1:46)

> Claude raggruppa gli esiti negativi per causa, senza dati personali, e scrive la bozza di correzione: la redazione la approva. La direzione vede quante pratiche si chiudono al primo appuntamento e se ogni correzione ha funzionato. Obiettivo: fino a novemila slot liberati l'anno.

## 8 · Chiusura (1:46–2:00)

*(pausa di 2 secondi)*

> Un appuntamento andato male non è un fallimento: è un dato. Una visita, una pratica chiusa: OneVisit.

**Tagli di riserva** se in prova si sfora: "che hanno risposto" (slide 3), "Perché non una semplice chat?" (slide 6, è il titolo della slide).

## Fonti e ipotesi dei numeri

- **Residenti e stranieri:** Portale Dati del Comune di Milano, "La popolazione a Milano nel 2025": 1,39 milioni di residenti, 295.805 stranieri (21,1% nel grafico della fonte). "Più di uno su cinque" vale in entrambi i casi.
- **Arrivi dall'estero:** dataset `ds1959`, 19.755 persone iscritte all'anagrafe di Milano nel 2024 con residenza precedente all'estero, di qualsiasi cittadinanza (26.359 nel 2023). A voce: "quasi ventimila".
- **Base prudente per il calcolo:** 4.500 nuovi residenti stranieri l'anno, stima del team (295.805 × 1,6% ≈ 4.733, arrotondata per difetto). È più bassa dei 19.755 arrivi: per questo diciamo "anche solo".
- **Sondaggio del team:** 14 studenti stranieri di un International MBA. Domanda (refusi corretti): "On a scale from 1 (very bad) to 5 (very good), how would you rate the experience for the process to get the administrative documents from the city". Risposte: 1 → 11, 2 → 1, 3 → 2, 4 → 0, 5 → 0. Negativi 12 su 14 (85,7%), positivi 0. Campione piccolo e non rappresentativo: per questo diciamo "12 su 14" e non una percentuale. Nella slide originale del sondaggio il titolo dice "10 studenti": va corretto in 14. Lo screenshot del sondaggio mostra le foto dei votanti: nel deck lo sostituisce un grafico.
- **Sondaggio del Comune:** dataset `ds1702`, 2022, servizio online di residenza, 10.194 risposte. "Ha aiutato poco o per niente": 42,1% dei 1.612 stranieri che hanno risposto, 28,2% degli 8.582 italiani (`data/context/residence-2022-helped-by-group.csv`). Non ci sono commenti liberi: il sondaggio misura quanto non funziona, non dove.
- **Slot sprecati e liberati:** ipotesi della testimonianza, tre visite invece di una. 4.500 × 2 visite in più = fino a 9.000 appuntamenti l'anno; 9.000 × 15 minuti = 2.250 ore di sportello, circa 281 giornate di 8 ore. È un ordine di grandezza, non una misura: il pannello serve proprio a misurarlo. Attenzione: il conto "4.500 × 45 minuti = 422 giornate perse" della slide originale conta anche la visita necessaria.
- **Prodotto:** le schermate sono del prodotto vero con dati sintetici (`onevisit seed-demo`, 400 casi inventati): i numeri del pannello non sono risultati. Il catalogo oggi ha 2 requisiti verificati su 19: se un requisito non è verificato, l'assistente lo dice e dà il link alla pagina del Comune. L'agente non è ancora stato provato con la vera API (serve la chiave in `.env`). Ruoli del pannello: redazione, ufficio, direzione. Le email e gli SMS esistono in italiano e inglese.
- **Per partire** (sulla slide 8, non a voce): non serve toccare il sistema di prenotazione. Servono un link nelle email che il Comune già invia ai nuovi residenti e i requisiti verificati una volta dagli uffici. Gli altri prerequisiti sono nella sezione "Day one" del README.
