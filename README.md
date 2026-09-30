# Trackrecord: kennis die vertrouwen verdient

**Tectonic Hackathon 2026 · SD Worx-challenge "Unlock the Knowledge Within"**
Team: Arthur Pintelon, Lamine Dene, Mauro Devolder, Nathaniel Lala

> *Vertrouwen wordt niet verklaard, het wordt verdiend.*

**In het Engels.** Today, trust in a document rests on proxies: who wrote it, when it was updated, whether it looks official. None of them tell you whether it actually works. Trackrecord closes that loop. It measures where people hesitate before and after reading (*Find it*, *Understand it*) and links every use of a document to its real outcome: reopened tickets, payroll corrections, escalations (*Trust it*). Every document gets a transparent track record, broken down by context (e.g. blue- vs white-collar), and one of four diagnoses: **reliable, unclear, broken, or dangerous**. Dangerous means people trust it and it is wrong, which is invisible to ratings. Transparent rules decide; an optional LLM only phrases a hypothesis. We measure documents, not people. The rules are validated on synthetic worlds with planted problems: **72/80 planted problems found, 0 false alarms on 440 normal documents**.

---

## Het probleem

Vandaag vertrouwen we een document omdat het er officieel uitziet of recent is bijgewerkt. Of het **in de praktijk werkt**, weet niemand. De organisatie maakt nochtans elke dag zelf de waarheid aan: heropende tickets, correcties in de loonrun, escalaties, vervolgvragen in Teams. Dat signaal vloeit nooit terug naar de kennis.

## Het idee

We meten de drie woorden uit de opdracht:

| Opdracht | Wat we meten | Betekenis als het slecht is |
|---|---|---|
| **Find it** | zoeken zonder een bruikbaar document te vinden | kennis ontbreekt |
| **Understand it** | twijfel **na** het lezen (opnieuw zoeken, ander document, Teams-vraag) | het document is onduidelijk |
| **Trust it** | uitkomst **na** gebruik (heropend, gecorrigeerd, geëscaleerd) | het document is fout, of fout in een bepaalde situatie |

|  | **Goed resultaat** | **Slecht resultaat** |
|---|---|---|
| **Weinig twijfel** | ✅ Betrouwbaar | 🚨 **Gevaarlijk**: vertrouwd, maar fout |
| **Veel twijfel** | ✏️ Onduidelijk: herschrijven | ❌ Kapot: vervangen |

Het gevaarlijke kwadrant is de kern. Sterrenbeoordelingen zouden zo'n document net hoog scoren, omdat het overtuigend klinkt. Alleen uitkomsten ontmaskeren het.

## Wat elke rol ziet

- **Consultant (sara).** Een ticket met de relevante documenten. Bij elk document staat een trackrecord **voor de eigen context**. Voorbeeld: *"Bij arbeiders liep 24 van de 51 gebruiken mis. Oorzaak volgens de tickets: vakantiegeld, vakantiekas, werkgever."* Bij een ticket over een bediende toont hetzelfde document dat er in die situatie geen afwijking is.
- **Documenteigenaar (an).** Per document een dossier:
  - waarom dit oordeel;
  - wanneer het misloopt (tijdlijn);
  - waar het misloopt (context);
  - waarom het misloopt (woordanalyse van mislukte tickets);
  - wat lezers daarna vragen;
  - een nieuwe versie publiceren, waarna het trackrecord opnieuw begint.
- **Kennisbeheerder (kim).** Het raster twijfel × uitkomst, een prioriteitenlijst, ontbrekende kennis (bijvoorbeeld flexi-jobs), de evaluatie en demoknoppen (maand simuleren, reset).

## Snel starten

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m uvicorn trackrecord.web:app --port 8000
```

Open http://127.0.0.1:8000. Bij de eerste start bouwt de app een fictieve wereld van 12 maanden op. Het wachtwoord van de demo-accounts (`sara`, `an`, `kim`) staat dan in `data/demo-login.txt` (niet in git). Je kan het ook vastzetten met `TRACKRECORD_DEMO_PASSWORD`.

```sh
.venv/bin/python -m unittest discover -s tests -v   # 18 tests: regels, privacy, toegangscontrole
.venv/bin/python -m trackrecord.evaluate --seeds 20  # meet of geplante problemen gevonden worden
.venv/bin/python -m trackrecord.generate             # demo-wereld opnieuw opbouwen
```

## Demo in 3 minuten

1. **sara** opent *"Vakantiegeld voor arbeider die in juni uit dienst ging"*. Het meest gebruikte vakantiegelddocument staat bovenaan, met een waarschuwing voor arbeiders en de oorzaak.
2. Ze opent ticket *"Dubbel vakantiegeld voor bediende"*: hetzelfde document, maar *"Bij bedienden: 56 van 60 keer zonder correctie. Jouw ticket valt daar niet onder"*. Bij het maaltijdchequesticket ziet ze *"In de laatste 90 dagen liep 8 van de 23 gebruiken mis"*.
3. **kim** opent het overzicht: *Vakantiegeld* in het gevaarlijke vak, *Loonbeslag* kapot, *Eindejaarspremie* onduidelijk, *Maaltijdcheques* recent verslechterd (sinds 1 juli), plus de lacune *flexi-jobs*.
4. **an** opent het dossier van *Vakantiegeld*. De woordanalyse vindt "vakantiekas", "werkgever" en "arbeiders" in 22 van de 24 mislukte tickets. Ze publiceert versie 2 met de uitbetaling via de vakantiekas voor arbeiders.
5. **kim** klikt *Simuleer volgende maand*. Versie 2 wordt betrouwbaar, en de effectkaart toont de vermeden mislukte tickets.
6. Evaluatiekaart: 72/80 gevonden, 0 valse alarmen. Afsluiter: *"We meten documenten, geen mensen."*

## Hoe we rekenen (open en controleerbaar)

Alles zit in [`trackrecord/scoring.py`](trackrecord/scoring.py). De AI beslist niets.

- **Gebruik** = een document dat als bron bij een ticket werd gevoegd. **Mislukt** = het ticket werd heropend, in de loonrun gecorrigeerd of geëscaleerd.
- **Twijfel na lezen** = binnen 15 minuten na het lezen:
  - opnieuw zoeken;
  - een ander document openen;
  - een Teams-vraag stellen;
  - "dit hielp niet" aanklikken.

  Wie korter dan 10 seconden leest, telt als **vindbaarheidssignaal**, niet als twijfel.
- **Recentheid.** Gebruiken wegen minder naarmate ze ouder zijn (halfwaardetijd 90 dagen). "De laatste 90 dagen" is daarnaast een eigen contextsegment, zodat *recent verslechterd*, bijvoorbeeld na een regelwijziging, apart zichtbaar wordt.
- **Afvlakking.** Scores worden afgevlakt naar het **typische document** (de mediaan, sterkte 10). Een paar slechte documenten kunnen de lat dus niet verhogen.
- **Oordeel.**
  - Pas vanaf **5 gebruiken door 5 verschillende collega's**.
  - En alleen als de kans dat de score echt boven 1,5× het typische document ligt **≥ 90%** is (Beta-posterior, exact berekend).
- **Context.** Per statuut, paritair comité, land, klantgrootte en periode zoeken we waar een document duidelijk vaker misloopt dan elders: minstens 15 procentpunt verschil, met ≥ 95% zekerheid.
- **Oorzaak.** De kernwoorden van mislukte tickets worden vergeleken met de mislukte tickets elders, via log-odds met een informatieve Dirichlet-prior (Monroe et al., 2008; z ≥ 1,96). Elk woord is terug te voeren tot de commentaren.
- **Integriteit.**
  - Eén ticket telt één keer per document.
  - Eén persoon telt hoogstens 10 keer per maand mee per documentversie.
  - Eén stem "dit hielp niet" per persoon per versie.
  - Uitkomsten komen alleen van de server.

## Werkt het? Gemeten, niet beweerd

We hebben geen echte SD Worx-data, dus [`generate.py`](trackrecord/generate.py) bouwt fictieve werelden: 30 consultants, 24 klanten, 26 documenten, ongeveer 1.600 tickets en 5.500 signalen over 12 maanden. In elke wereld zijn problemen **verstopt** (zie [`world.py`](trackrecord/world.py)):

- een document dat alleen voor arbeiders fout is;
- een onduidelijk document;
- een kapot document;
- een document dat na een regelwijziging op 1 juli verouderd is;
- een kennislacune.

Trackrecord weet niet waar die zitten.

Resultaten op **20 werelden die niet gebruikt werden om de regels te ontwerpen** (seeds 101-120; `docs/evaluation.json`):

| | Resultaat |
|---|---|
| Geplante documentproblemen juist geclassificeerd | **72 / 80** (vakantiegeld 20/20, eindejaarspremie 20/20, loonbeslag 19/20, maaltijdcheques 13/20) |
| Valse alarmen op normale documenten | **0 / 440** |
| Juiste context gevonden (arbeiders) | 20 / 20 |
| Kennislacune gevonden | 19 / 20, 0 valse lacunes |
| Gevaarlijk document opgemerkt na | mediaan 12 gebruiken |
| Regelwijziging van 1 juli opgemerkt na | mediaan 49 dagen (gemist in 6/20) |
| **Ablatie:** zonder afvlakking en minimumbewijs | 77/80 gevonden, maar **143 / 440 valse alarmen** |
| **Ablatie:** zonder recentheid | 69/80 gevonden, regelwijziging gemist in 11/20 |

De ablaties tonen waarom de veiligheidsregels nodig zijn: zonder die regels zou elk derde normaal document onterecht rood kleuren.

De demowereld (seed 12) is gekozen omdat alle vier de patronen erin zichtbaar zijn. De cijfers hierboven komen niet uit die wereld.

## Privacy: we meten documenten, geen mensen

Dit is een HR-context, dus privacy is een ontwerpbeslissing (in lijn met de GDPR en de principes van cao nr. 81: finaliteit, proportionaliteit, transparantie).

- **Pseudoniemen.** Signalen worden opgeslagen onder een HMAC-pseudoniem, nooit onder een gebruikers-id. Tickets bevatten geen consultantnaam.
- **Geen overzichten per persoon.** Er bestaat **geen endpoint met statistieken per persoon**. Een test controleert dat er geen pseudoniemen of namen van collega's in de antwoorden zitten.
- **Minimale groepsgrootte.** Cijfers per document of context verschijnen pas bij **≥ 5 verschillende collega's**.
- **Opgekuiste vrije tekst.** Rijksregisternummers, IBAN's, e-mailadressen en gsm-nummers worden uit Teams-vragen, zoekopdrachten en commentaren gefilterd voordat ze getoond of naar een LLM gestuurd worden.

## Beveiliging

| Risico | Maatregel |
|---|---|
| Authenticatie | scrypt-wachtwoordhashes, server-side sessies (gehashte tokens), cookie `HttpOnly` + `SameSite=Strict` (+ `Secure` op https), 8 uur geldig, rate limiting op login per naam en per IP, geen user enumeration (dummy-hash) |
| Autorisatie | Rollen per endpoint. Consultant: alleen de eigen portefeuille. Eigenaar: alleen de eigen documenten. Beheerder: kijken, niet publiceren. |
| IDOR | Elk ticket, elke werksessie en elk dossier wordt server-side gecontroleerd op eigendom en portefeuille. Anders volgt een 404 zonder te verraden dat het object bestaat. |
| Businesslogica | Uitkomsten kunnen niet vanuit de browser geschreven worden. De user-id komt uit de sessie, nooit uit de body (`extra="forbid"`). Eén stem per versie, één uitkomst per ticket, een cap per persoon, alleen de huidige versie kan gebruikt worden. |
| CSRF | Token per sessie in een header, plus een controle op dezelfde origin. Alleen JSON wordt aanvaard. |
| Injectie en XSS | Alleen geparametriseerde SQL. De front-end gebruikt uitsluitend `textContent`. Strikte CSP zonder inline scripts of stijlen. |
| Headers | CSP, `X-Frame-Options: DENY`, `nosniff`, `Referrer-Policy`, `Permissions-Policy`, `Cache-Control: no-store`, TrustedHost |
| LLM | Optioneel. Alleen https, geen redirects (de sleutel lekt niet), commentaren zijn data, output via een JSON-schema gevalideerd. Beïnvloedt nooit een score. |
| Geheimen | Niets in git. `.env.example` bevat geen waarden. Het demo-wachtwoord en het pseudoniemgeheim worden lokaal gegenereerd (`chmod 600`). |

## Optioneel: AI-hypothese

Zet een OpenAI-compatibel chat/completions-endpoint in de omgeving, bijvoorbeeld Gemini:

```sh
export LLM_ENDPOINT=https://generativelanguage.googleapis.com/v1beta/openai/chat/completions
export LLM_MODEL=gemini-2.5-flash
export LLM_API_KEY=...   # nooit committen
```

Het dossier van een gevaarlijk of kapot document toont dan één zin als hypothese. Zonder deze variabelen werkt alles volledig offline.

## Deploy (bv. Cloud Run)

```sh
docker build -t trackrecord .
docker run -p 8080:8080 -e TRACKRECORD_DEMO_PASSWORD=... -e TRACKRECORD_ALLOWED_HOSTS=jouw-host trackrecord
```

Zet `TRACKRECORD_DEMO_CONTROLS=0` voor alles buiten een demo.

## Bestanden

```
trackrecord/
  scoring.py    rekenregels: twijfel, uitkomst, kwadranten, context, lacunes
  explain.py    oorzaakanalyse (woordanalyse) + optionele AI-hypothese
  generate.py   synthetische wereld met geplante problemen, maand simuleren
  world.py      fictieve klanten, documenten, onderwerpen en de geplante problemen
  evaluate.py   evaluatie over niet-geziene werelden + ablaties
  web.py        FastAPI-app: rollen, toegangscontrole, API
  auth.py       wachtwoorden, sessies, rate limiting
  privacy.py    pseudoniemen en het opkuisen van persoonsgegevens
  db.py         SQLite-schema
static/         front-end zonder framework (index.html, app.js, style.css)
tests/          18 tests
```

## Wat (nog) niet af is

- **Alle data is synthetisch en fictief.** Namen, klanten, documenten en payrollregels zijn verzonnen: geen SD Worx-beleid, geen payrolladvies. Echte koppelingen (ticketsysteem, correctielog van de loonrun, Teams via Microsoft Graph) zijn niet gebouwd. Het datamodel is erop voorzien.
- **Gebruik is een expliciete klik.** Een document telt als gebruikt via de knop "Gebruik als bron". Automatische detectie (tekstgelijkenis tussen antwoord en document) is niet gebouwd.
- **Correlatie is geen oorzaak.** Trackrecord toont een signaal met bewijs, en een mens beslist. De simulatie na een nieuwe versie neemt aan dat de nieuwe tekst het probleem oplost. In de echte wereld is dat precies wat Trackrecord zou meten.
- **Een recente regelwijziging is het moeilijkst.** Die werd in 13/20 werelden op tijd herkend, omdat er dan nog weinig afgeronde tickets zijn.
- **Eén proces.** Rate limiting zit in het geheugen van één proces. Er is geen SSO. SQLite volstaat voor de demo.
- **De AI-koppeling is optioneel** en niet live getest tegen een provider tijdens de hackathon. Zonder die koppeling werkt alles.
