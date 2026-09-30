# PARALLAX — Kennis in perspectief

Hackathonprototype voor de SD Worx-uitdaging. PARALLAX helpt een medewerker te
zien waar een antwoord vandaan komt, voor welke context het geldt en waar
bronnen elkaar tegenspreken.

De voorbeeldinhoud is fictief. Ze is geen SD Worx-beleid of payrolladvies.

## Start de website

Vereist Python 3.10 of nieuwer en een SQLite-versie met FTS5.

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m uvicorn app:app --host 127.0.0.1 --port 8000
```

Open daarna [http://127.0.0.1:8000](http://127.0.0.1:8000). De API-specificatie
staat op [http://127.0.0.1:8000/openapi.json](http://127.0.0.1:8000/openapi.json).
Om de server te stoppen, druk je op `Ctrl+C` in de terminal waar hij draait.

## Zo gebruik je de website

De website opent meteen met een voorbeeldvraag over de verwerkingsdeadline.
Een procedure zegt dinsdag; een Teams-notitie zegt woensdag. PARALLAX toont de
bronnen naast elkaar en vraagt om een beoordeling in plaats van één antwoord
te kiezen alsof de tegenspraak niet bestaat.

- **Scenario's** vullen een voorbeeldvraag in en voeren die uit. ‘Het oude
  draaiboek’ laat zien waarom een vervangen procedure geen actuele onderbouwing
  vormt. ‘De nieuwe collega’ demonstreert een klantoverdracht.
- **Land, klant en datum** bepalen de situatie waar de vraag over gaat. De demo
  Acme-afspraak is alleen van toepassing op Belgische klantvragen.
- **Bronnenkaart** toont de gevonden passages en geeft aan wie de bron beheert,
  wanneer de inhoud geldt, of ze formeel is goedgekeurd en of er tegenspraak is.
  Kies ‘Geldigheid’, ‘Bronhouder’ of ‘Verschillen’ om een signaal uit te lichten.
  ‘Lees de passage’ opent de oorspronkelijke tekst.
- **Perspectieven vergelijken** stelt dezelfde vraag voor Nederland en voor een
  eerdere datum. Zo zie je welke bron of uitkomst met de context mee verandert.
- **Leg de twijfel voor** bewaart de vraag, context en bronnen als een lokaal
  expertverzoek. In de tab **Kennislus** kies je voor deze demo een bron en
  motiveer je die keuze. De interface labelt dit uitdrukkelijk als simulatie;
  ze verstuurt geen bericht naar een echte expert.
- Na de beoordeling wordt dezelfde vraag alleen opnieuw beoordeeld als de
  vraag, het land, de klant, de datum en de gebruikte bronnen gelijk zijn.
  Verandert een bron, dan vervalt de eerdere beoordeling en komt de tegenspraak
  terug in beeld.
- **Bewaar de onderbouwing** downloadt het kennisdossier met de oorspronkelijke
  vraag, context, bronpassages en eventuele beoordeling.
- In **Bronnenatlas** kun je alle fictieve documenten bekijken en op land filteren.

## Hoe de website in elkaar zit

```mermaid
flowchart LR
    A[static/app.js<br/>website stuurt vraag] --> B[app.py<br/>FastAPI controleert invoer]
    B --> C[knowledge.py<br/>context en versies controleren]
    C --> D[(SQLite + FTS5<br/>bronnen en kennisdossiers)]
    C --> E[antwoord, signalen en bronverwijzingen]
    E --> A
    A --> F[bronnen bekijken of context vergelijken]
    A --> G[expertbeoordeling opslaan en hergebruiken]
    H[data/sources.json<br/>fictieve voorbeeldbronnen] --> D
```

De browser toont de pagina uit `static/index.html`. De opmaak staat in
`static/style.css`; interacties staan in `static/app.js`. Deze bestanden gebruiken
geen externe lettertypen of CDN's. JavaScript verstuurt een vraag als JSON naar
de Python-server.

`app.py` is de FastAPI-laag: die valideert invoer, beperkt de aanvraaggrootte,
weigert ongewenste browseraanvragen en verbindt de website met de Pythonfuncties.
De routes zijn:

| Route | Doel |
| --- | --- |
| `POST /api/ask` | Beantwoord de vraag en bewaar een momentopname van de gevonden bronnen. |
| `GET /api/sources` | Toon de bronnenatlas. |
| `GET /api/assessments/{id}/compare` | Vergelijk dezelfde vraag met een ander land of een eerdere datum. |
| `GET /api/assessments/{id}/receipt` | Download het kennisdossier als Markdown. |
| `POST /api/reviews` | Leg een lokaal beoordelingsverzoek vast voor een momentopname. |
| `GET /api/reviews` | Toon open en afgeronde beoordelingsverzoeken. |
| `POST /api/reviews/{id}/resolve` | Leg een gemotiveerde demobeoordeling vast. |

`knowledge.py` zoekt met SQLite FTS5 in de bronpassages. De vraag wordt eerst
opgeschoond; waar een herkenbaar onderwerp, zoals een deadline, aanwezig is,
gebruikt de zoekfunctie de termen voor dat onderwerp. Land en klant worden al
tijdens de databasezoekopdracht toegepast. Daarna controleert de code datum,
opvolgende versies, bronhouder en formele goedkeuring. Elke controle blijft een
apart zichtbaar signaal; een goedgekeurde bron maakt een tegenspraak niet weg.

Conflicten worden vergeleken op claims die voor deze demo vooraf in
`data/sources.json` zijn gestructureerd. De code groepeert die claims op onderwerp
en vergelijkt gevonden actieve bronnen. Ook een afwijkende formulering kan een
conflict tonen als de bronnen dezelfde gestructureerde claim delen. Verschillende
landen, geldigheidsperioden en klantbereiken worden bij die vergelijking
meegewogen.

Een onderzoek wordt als momentopname met bronvingerafdruk opgeslagen. De Kennislus
kan een gemotiveerde keuze koppelen aan die momentopname. Als de gebruikte bronnen
veranderen, vervalt de keuze automatisch. De export gebruikt de opgeslagen
momentopname, zodat een later gewijzigde bron het eerdere dossier niet herschrijft.

`model.py` bevat een optionele verbinding met een compatibele
chat/completions-provider. Zonder provider toont PARALLAX de gevonden tekst letterlijk.
Met een provider gebruikt het model alleen passages van een onderbouwd antwoord;
ongeldige verwijzingen of providerfouten leiden terug naar de oorspronkelijke
passages. Een juiste bronverwijzing bewijst op zichzelf niet dat een AI-antwoord
inhoudelijk klopt.

## Voorbeeldbronnen aanpassen

Pas `data/sources.json` aan. Elk document bevat onder meer een uniek `id`, een
`title`, `country`, een optionele `client_id`, een `owner`, `approved`, de
geldigheidsdatums, `supersedes`, tekstpassages en handmatig gestructureerde
`claims`. Deze velden bepalen wat in de interface verschijnt en welke
demo-conflicten gevonden kunnen worden.

De applicatie importeert dit bestand wanneer de database geen bronnen bevat. Stop
de server en maak een reservekopie voordat je de database verwijdert om de
bronnen opnieuw te importeren. Dezelfde database bevat ook dossiers en
beoordelingsverzoeken.

## Belangrijke grenzen

De demo analyseert geen willekeurige documenten automatisch op verborgen
tegenstrijdigheden. Alleen vooraf vastgelegde claims tellen mee in de
conflictcontrole. ‘Geen conflict gevonden’ betekent dus niet dat twee documenten
inhoudelijk met elkaar overeenstemmen. Zoeken op woorden en beperkte synoniemen
is ook geen semantische zoekfunctie.

De website heeft geen aanmeldscherm, rechtenbeheer of klantisolatie. De filters
op land en klant helpen de juiste kennis te vinden, maar beveiligen echte
bedrijfsgegevens niet. Gebruik daarom uitsluitend fictieve gegevens en start de
server alleen op localhost. Voor inzending is de Aikido AI Code Audit uit de
hackathongids nog vereist; deze lokale regressietests vervangen die audit niet.

## Tests

De tests gebruiken tijdelijke databases en een nagebootste modelrespons.
Installeer ook de testafhankelijkheid en voer alle regressietests uit:

```sh
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m unittest discover -s tests -v
```

Tests staan in `tests/test_api.py`, `tests/test_knowledge.py` en
`tests/test_workflow.py`.

## Projectbestanden

| Bestand | Inhoud |
| --- | --- |
| `app.py` | Python-API en koppeling tussen website en kennisfuncties. |
| `knowledge.py` | Zoeken, controles, momentopnamen en beoordelingen. |
| `model.py` | Optionele AI-formulering met gecontroleerde bronverwijzingen. |
| `static/index.html` | Pagina-indeling van PARALLAX. |
| `static/style.css` | Kleuren, opmaak en schermformaten. |
| `static/app.js` | Vraag afhandelen en schermen bijwerken. |
| `data/sources.json` | De fictieve voorbeeldbronnen en demo-claims. |
| `docs/hackathon.md` | Aansluiting op de SD Worx-uitdaging en een kort videoscript. |
| `tests/` | Tests van zoeken, beveiligingscontroles en de beoordelingsflow. |
