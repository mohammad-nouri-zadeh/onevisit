# City data: what it says about our problem

Numbers computed by `data/tools/summarise_opendata.py` from the Comune di Milano open-data portal (dati.comune.milano.it, licence CC BY), downloaded on 3 Oct 2026. Each line names its dataset. These are for the **pitch and the panel**. The citizen-facing agent gets its facts from `data/services/` and `data/offices.json`, not from here.

## How many people this is for

- **19,755 people registered in Milan arriving from abroad in 2024**, 42.1% of all new registrations that year (26,359 in 2023, 44.4%). Source: `ds1959`, table `arrivals-from-abroad.csv`. "From abroad" means the previous residence was abroad, whatever the citizenship.
- **27,184 registered in Milan coming from another Italian comune in 2024** (every place of origin except abroad and the 14 not stated): the change-of-residence procedure. Same dataset and table, column `registrations_from_other_comuni`. The City tab's impact estimate uses these two 2024 figures as its bases; no dataset here counts ID cards issued, so the estimate leaves them out.

## Where the online service fails, and for whom

From the City's own satisfaction surveys on its online services. The question: "Ha facilitato la gestione della tua esigenza?" ("Did it make handling your request easier?"). The percentages are the people who answered "Poco" or "Per niente".

| Online service | Year | Responses | Helped little or not at all |
|---|---|---|---|
| Residence requests (`ds1702`) | 2022 | 10,194 | **30.4%** |
| Online appointments (`ds1511`) | 2021 | 4,646 | 24.4% |
| Registry certificates (`ds1512`) | 2021 | 10,915 | 2.3% |

Residence requests, by respondent (`ds1702`, table `residence-2022-helped-by-group.csv`):

| Group | Responses | Helped little or not at all |
|---|---|---|
| Italian citizens | 8,582 | 28.2% |
| Foreign citizens | 1,612 | **42.1%** |
| Request type: change of residence for foreign citizens arriving from abroad or another Italian municipality | 1,097 | **46.2%** |

**For the pitch:** certificates already work online (2.3% unhelped). Residence is where the City's online service fails most, and it fails foreign newcomers most: nearly half of them said it helped little or not at all. That is OneVisit's user, and the 42.1% vs 28.2% gap is the equity baseline the panel would track.

Two more facts from the same survey:
- All 10,194 responses were filled in Italian (`Lingua iniziale` = `it` for every row).
- The survey is about the **online** residence request service. In Milan, at least part of the residence process happens online, so check the official page before building the demo around a desk visit for residence.

These surveys have no free-text comments, only the four rated questions and the age band.

## Which languages to support

Largest foreign communities resident in Milan, 2025 (`ds74`, table `foreign-residents-2025-top20.csv`; 295,805 foreign residents in total):

1. Egypt 41,957 (14.2%)
2. China 37,641 (12.7%)
3. Philippines 35,638 (12.0%)
4. Peru 18,399 (6.2%)
5. Sri Lanka 15,629 (5.3%)

Peru, Ecuador and El Salvador together: 32,926 (11.1%). Citizenship isn't language, but this suggests Arabic, Chinese and Spanish (plus English) as the languages that would reach most people. It's a data-backed choice for the non-Italian demo conversation.

## From the hackathon brief (not City data)

The organisers' summary of their call with the Comune (hub repo `CHALLENGE.md`, slide 5 of the opening deck). It's context to build on, not an official source to cite to citizens:

- automatic emails already go to new residents and to people who change address;
- 16 of the 22 most-requested certificates are already online;
- a TARI pilot is at an advanced stage;
- YesMilano has an information path for international students;
- still open: knowing when someone has just arrived; clean data and reliable connectors; fragmented systems.
