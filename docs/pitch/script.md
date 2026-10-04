# Pitch di 2 minuti: testo da leggere

Struttura **SPIN** (Situazione, Problema, Implicazione, Need-payoff). Prima fa sentire il costo del problema, poi mostra il valore con il prodotto vero: l'app **dal vivo con Claude** su https://onevisit.streamlit.app, con la demo senza chiave (`?demo=1`) solo come piano B. I quattro tempi del regolamento (problema, demo, dove lavora Claude, primo giorno) ci sono tutti.

Circa 295 parole: 1:58 di parlato più una pausa da 2 secondi, a circa 150 parole al minuto. I tempi sono cumulativi.

| # | Cosa si vede | Fase | Tempo |
|---|---|---|---|
| 1 | Slide: la testimonianza e il team | Aggancio | 0:00–0:12 |
| 2 | Slide: 19.755 arrivi dall'estero (`ds1959`) | S · Situazione | 0:12–0:20 |
| 3 | Slide: 42,1% contro 28,2% (`ds1702`), le fonti sparse | P · Problema | 0:20–0:38 |
| 4 | Slide: la frase del modulo online (+ pausa) | I · Implicazione | 0:38–0:50 |
| 5 | **App dal vivo, scheda "Per i cittadini"**: si scrive la frase in arabo, la checklist in arabo, i file da caricare, il dossier | N · Valore per il cittadino | 0:50–1:18 |
| 6 | App: "Le tue prossime 3 azioni", le note con le fonti, "Cosa ha controllato Claude" | N · Dove lavora Claude | 1:18–1:32 |
| 7 | **App, scheda "Per il Comune"**: la mail di conferma, la bozza di correzione | N · Primo giorno e valore per il Comune | 1:32–1:55 |
| 8 | Slide finale con il link | Chiusura | 1:55–2:00 |

## 1 · Aggancio (0:00–0:12)

> «Ho dovuto prendere tre appuntamenti di quindici minuti per mettere a posto la mia residenza.» Siamo OneVisit: due italiani e tre arrivati dal mondo. Vogliamo che ne basti uno.

## 2 · Situazione (0:12–0:20)

> Nel 2024 quasi ventimila persone si sono iscritte all'anagrafe di Milano arrivando dall'estero. La comunità straniera più numerosa è quella egiziana.

## 3 · Problema (0:20–0:38)

> Il sondaggio del Comune sul servizio online di residenza: ha aiutato poco o niente il quarantadue per cento degli stranieri, il ventotto per cento degli italiani. E le regole sono sparse tra Comune, Questura, Agenzia delle Entrate e un elenco di documenti in PDF del 2013.

## 4 · Implicazione (0:38–0:50)

> La residenza si chiede online, una domanda alla volta: finché la prima non è conclusa, il sistema non ne accetta un'altra. Deve partire completa.

*(pausa di 2 secondi)*

## 5 · Valore per il cittadino: la demo (0:50–1:18)

> Lei è arrivata dal Cairo il mese scorso. Scrivo la sua frase in arabo, dal vivo. Claude capisce che le serve la residenza e chiede solo ciò che cambia la lista: permesso, famiglia, casa. Ecco la checklist in arabo: ventiquattro voci, ognuna con la frase esatta della pagina. I nove file da caricare, sezione per sezione. E il dossier, in italiano e arabo.

## 6 · Dove lavora Claude (1:18–1:32)

> Claude decide cosa chiedere, mette in ordine le prossime tre azioni e traduce. Ma non scrive mai un requisito a memoria: un controllo automatico blocca ogni risposta senza fonte o che dica «sei in regola», e scarta ogni azione fuori dalla checklist. Se non sa, lo dice. Decide l'operatore.

## 7 · Primo giorno e valore per il Comune (1:32–1:55)

> Per attivarlo basta una riga nelle mail che il Comune già manda: dalla conferma dell'appuntamento, OneVisit si apre con servizio, sede e data. Dopo, le segnalazioni anonime diventano bozze di correzione delle pagine, che un funzionario approva. La prima lacuna l'abbiamo trovata noi: l'elenco ufficiale non dice cosa serve a chi aspetta il primo permesso per studio.

## 8 · Chiusura (1:55–2:00)

> La pratica chiusa al primo invio o al primo appuntamento: OneVisit.

**Tagli di riserva** se in prova si sfora: "La comunità straniera più numerosa è quella egiziana" (slide 2), "I nove file da caricare, sezione per sezione" (5), "Se non sa, lo dice" (6), l'ultima frase della 7.

## Note per la regia

- **Usare l'app dal vivo** (https://onevisit.streamlit.app, con la chiave nei Secrets di Streamlit). Dieci minuti prima aprirla in una finestra anonima, perché Streamlit Community Cloud addormenta le app inattive, e controllare in alto il badge "Dal vivo: risponde Claude". Fare una prova con la frase del Cairo: oltre a rispondere, scalda la cache.
- **La frase da scrivere** è quella dell'esempio: «وصلت من القاهرة الشهر الماضي للعمل وأحتاج إلى تسجيل إقامتي في ميلانو. من أين أبدأ؟». Tenerla negli appunti e incollarla nel campo in basso: la pagina passa all'arabo, da destra a sinistra. Le risposte di Claude dal vivo cambiano un po' da una volta all'altra; checklist, file e fonti no, perché vengono dai dati.
- **Piano B senza rete:** una seconda scheda con https://onevisit.streamlit.app/?demo=1 e il caso del Cairo già completo (home, "La stessa persona scrive in arabo", poi "أنتظر الأول، للعمل", "وحدي", "إيجار · العقد غير مسجّل بعد، أو لا أعرف"). Se Claude non risponde, l'app passa da sola alla demo e lo scrive in alto: si continua senza fermarsi. Con `?demo=1` il badge in alto dice "Replica dimostrativa · dati e fonti reali" e ogni risposta è firmata "OneVisit · replica": mostrandola si dice che è la replica (strumenti, checklist e fonti girano dal vivo; le frasi dal vivo le scrive Claude), mai che sta rispondendo Claude.
- **Terza scheda:** "Per il Comune". Durante la 7 si clicca il link della mail fac-simile; se c'è tempo, "Prova: arriva una segnalazione" con l'esempio pronto (si vede che il codice toglie email e data prima che Claude legga), poi "Mostra la bozza scritta da Claude" e "Approva la correzione".
- **Il deck del pitch è `docs/slides/onevisit-pitch-v2.pptx`.** Quello del 3 ottobre (`docs/slides/onevisit-pitch.pptx`) resta come riferimento: le sue slide 3–7 raccontano ancora il prodotto precedente (sondaggio degli studenti, SMS, KPI).

## Domande probabili della giuria

- **«E se Claude sbaglia?»** Claude non può aggiungere requisiti: checklist e dossier li costruisce il codice dai dati verificati. Ogni risposta passa un controllo automatico (fonti inesistenti o non lette, frasi di idoneità in sette lingue, fatti senza fonte). Una risposta bloccata viene rigenerata una volta; se è bloccata di nuovo, la persona riceve un messaggio sicuro con la pagina ufficiale. `onevisit/validator.py`.
- **«Perché non basta una chat generica?»** Una chat risponde a memoria. OneVisit ha 110 voci verificate parola per parola (96 requisiti, 12 passaggi, 2 strade alternative) su 16 pagine ufficiali salvate, e per le 3 voci che le fonti non coprono dice che non lo sa.
- **«Cosa fa Claude che il codice non fa?»** Capisce il caso da una frase in qualsiasi lingua, decide le domande, mette in ordine le prossime tre azioni, traduce i testi che mancano, classifica le segnalazioni e scrive le bozze di correzione. Il codice controlla ognuna di queste cose prima che qualcuno le veda: fonti, voci della checklist, parole di idoneità, dati personali tolti prima.
- **«La traduzione è affidabile?»** È di Claude e lo dice l'etichetta; il testo italiano e la frase della fonte sono a un tocco, e il dossier li stampa per primi. Prima dell'adozione la deve rivedere una persona che conosce la lingua.
- **«Come fa a sapere che uno è appena arrivato?»** Il primo giorno non ne ha bisogno: sta nei canali da cui il nuovo arrivato passa già (mail di conferma, mail di benvenuto, guida YesMilano). Per diventare proattivo servono lo stato della pratica da ANPR tramite PDND, l'accesso con SPID o CIE e App IO: è la tabella "Per renderlo proattivo" nella scheda del Comune.
- **«Quanto impatto?»** È una stima, non un risultato, e la scheda del Comune mostra la formula: (19.755 iscritti dall'estero × quota che ripresenta la domanda + 27.184 iscritti da altri Comuni × quota che ripresenta la dichiarazione) × quota che usa OneVisit × quota di secondi tentativi evitati. Con le ipotesi di partenza (20%, 10%, 30%, 50%) fa circa mille secondi tentativi evitati all'anno, solo sulle due pratiche di residenza; le carte d'identità non le contiamo perché nessuna fonte salvata dice quante ne rilascia il Comune.
- **«Cosa serve al Comune domani?»** Una riga nel modello della mail di conferma, la stessa nelle mail di benvenuto e su YesMilano, e un funzionario che verifica le citazioni una volta per servizio. Nessun accesso ai sistemi, nessun dato personale.
- **«E chi arriva da Torino, o cambia casa dentro Milano?»** È la pratica più frequente: nel 2024 27.184 iscritti a Milano venivano da un altro Comune italiano (`ds1959`). OneVisit la riconosce dalla frase ("mi sono trasferito da Torino") e la distingue dalla residenza dall'estero: dichiarazione online sull'Anagrafe Nazionale (ANPR) con SPID o CIE, entro 20 giorni, gratuita, con 18 voci verificate su due pagine (Comune e ANPR). Se le parole non dicono da dove arriva la persona, lo chiede.
- **«Dati personali?»** Non chiede nome, codice fiscale, indirizzo né foto dei documenti. Il link porta solo servizio, sede, data e lingua. Delle segnalazioni si salvano solo la causa e una frase anonima.

## Fonti e ipotesi dei numeri

- **Testimonianza:** è la frase d'apertura del pitch del 3 ottobre (slide 1 di `docs/slides/onevisit-pitch.pptx`).
- **Arrivi dall'estero:** dataset `ds1959`, 19.755 persone iscritte all'anagrafe di Milano nel 2024 con residenza precedente all'estero, di qualsiasi cittadinanza (42,1% delle nuove iscrizioni; 26.359 nel 2023). A voce: "quasi ventimila". Tabella `data/context/arrivals-from-abroad.csv`.
- **Comunità egiziana:** dataset `ds74`, 2025: 41.957 residenti con cittadinanza egiziana, il 14,2% dei 295.805 stranieri residenti, la prima comunità per numero (`data/context/foreign-residents-2025-top20.csv`). La persona della demo è inventata.
- **Sondaggio del Comune:** dataset `ds1702`, 2022, servizio online di residenza, 10.194 risposte, tutte compilate in italiano. "Ha aiutato poco o per niente": 42,1% dei 1.612 stranieri, 28,2% degli 8.582 italiani (`data/context/residence-2022-helped-by-group.csv`). Non ci sono commenti liberi: il sondaggio misura quanto non funziona, non dove.
- **Regole sparse e PDF del 2013:** le 16 pagine salvate in `data/pages/` vengono da Comune di Milano, Ministero dell'Interno, Polizia di Stato, Agenzia delle Entrate e YesMilano (`data/sources.csv`). L'elenco dei documenti per i cittadini extra UE (`residenza-estero-extraue`, Allegato A) è un PDF creato nel 2013 secondo i suoi metadati: chiede ancora "originale e fotocopia", mentre oggi la domanda si fa online con le scansioni.
- **Online, una domanda alla volta:** pagina `residenza-estero` (la domanda si presenta online) e modulo `residenza-estero-modulo`: «Il sistema non consente di inviare una nuova dichiarazione di residenza se non si è concluso l'iter della dichiarazione precedentemente inviata.» "Deve partire completa" è la nostra conclusione da questa frase, non una frase del Comune.
- **Ventiquattro voci, nove file:** la checklist per le risposte "aspetto il primo permesso per lavoro", "da sola", "affitto, contratto non ancora registrato o non lo so", calcolata da `data/services/iscrizione-anagrafica-extra-ue.json` (10 da preparare, 6 su come funziona, 8 per il dopo), e i 9 file da caricare: un solo contratto d'affitto, perché l'app chiede se è già registrato. Se i dati cambiano cambiano anche i numeri: ricontrollarli nell'app prima del pitch. Nel catalogo sono verificati 96 requisiti su 99, 12 passaggi su 12 e 2 strade alternative per il codice fiscale: 110 voci verificate, 3 aperte.
- **La lacuna sul permesso per studio:** l'Allegato A copre quattro casi (permesso valido, in rinnovo, attesa del primo permesso per lavoro subordinato o per ricongiungimento familiare). Chi aspetta il primo permesso per studio non è coperto: nel catalogo è il requisito aperto `documenti-altri-permessi`, e nella scheda del Comune è un gruppo di segnalazioni **simulate** con la bozza di correzione registrata.
- **Controllo automatico:** `onevisit/validator.py`; parole di idoneità in italiano, inglese, spagnolo, francese, portoghese, arabo e cinese.
- **Prodotto:** le schermate nel README sono dell'app vera nella replica dimostrativa; le segnalazioni pre-caricate nella scheda del Comune sono simulate e marcate SIMULATE. Il percorso dal vivo con Claude nella versione del 4 ottobre (conversazione, prossime azioni, traduzioni mancanti, classificazione, bozze) è provato con un client finto, perché nell'ambiente di sviluppo non c'era una chiave; la prima versione è stata provata con la vera API il 3 ottobre. Prima del pitch, con la chiave: `python -m onevisit.evaluate --usd-to-eur <cambio>` sui 20 scenari; scrive `docs/eval-results.md` con esito, secondi, token e costo per scenario. Finché non c'è, non si cita nessun numero sul costo o sulla qualità dal vivo.
- **Non detti a voce, utili alle domande:**
  - **Residenti stranieri:** Portale Dati del Comune di Milano, "La popolazione a Milano nel 2025": 1,39 milioni di residenti, 295.805 stranieri (21,1% nel grafico della fonte): più di uno su cinque.
  - **Sondaggio del team** (3 ottobre): 14 studenti stranieri di un International MBA, voto da 1 a 5 sull'esperienza per ottenere i documenti dal Comune. Risposte: 1 → 11, 2 → 1, 3 → 2, 4 → 0, 5 → 0, quindi 12 negativi su 14 e nessun positivo. Campione piccolo e non rappresentativo: si dice "12 su 14", mai una percentuale.
  - **Impatto atteso:** la scheda del Comune mostra la formula "(iscrizioni dall'estero × quota che ripresenta la domanda + iscrizioni da altri Comuni italiani × quota che ripresenta la dichiarazione) × quota che usa OneVisit × quota di secondi tentativi evitati da chi lo usa". Le due basi sono dati del 2024 (`ds1959`, colonne `registrations_from_abroad` e `registrations_from_other_comuni` di `data/context/arrivals-from-abroad.csv`): 19.755 e 27.184. Le quattro quote sono ipotesi spostabili; con quelle di partenza (20%, 10%, 30%, 50%) fa (19.755 × 20% + 27.184 × 10%) × 30% × 50% ≈ 1.000 secondi tentativi evitati all'anno. Un secondo tentativo è una domanda ripresentata o un ritorno allo sportello. È una **stima, non un risultato**. Le carte d'identità sono escluse: nessuna fonte salvata né dataset in `data/` dice quante ne rilascia il Comune in un anno. Il conto del 3 ottobre ("fino a 9.000 appuntamenti", cioè 4.500 nuovi residenti stranieri × 2 visite in più) era un ordine di grandezza basato sulla testimonianza: non lo usiamo più.
