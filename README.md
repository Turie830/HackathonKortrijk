# HackathonKortrijk
## Teammates: Arthur Pintelon, Lamine Dene, Mauro Devolder, Nathaniel Lala


hell yeah cmon lads

\begin{statementLamine}
  WE GAAN WINNEN WE GAAN WINNEN WE GAAN WINNEN
\end{statementLamine}

## Knowledge Within — SD Worx prototype

Python-app voor het vinden en beoordelen van verspreide kennis. Inclusief een
webinterface, SQLite FTS5-zoekindex, zichtbare broncontroles, gestructureerde
conflictdetectie en lokaal opgeslagen verzoeken voor expertbeoordeling.

Alle voorbeeldprocedures zijn **fictief** en zijn geen SD Worx-beleid of payrolladvies.

### Starten

Python 3.10+ met SQLite FTS5-ondersteuning:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m uvicorn app:app --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000. API-documentatie: http://127.0.0.1:8000/docs.

### Demo

- **Klantoverdracht:** een antwoord met goedgekeurde bronpassages.
- **Looncorrectie:** de oude procedure wordt getoond als vervangen; de huidige wordt geciteerd.
- **Deadline maandverwerking:** een procedure en Teams-notitie spreken elkaar tegen; beoordeling is nodig.
- Kies **Nederland** om de landspecifieke bronfilter te zien.
- Kies **Demo Acme** bij een overdrachtsvraag voor een aanvullende klantafspraak.
- Vraag naar **archiveren van dossiers** voor een bron zonder eigenaar en goedkeuring.
- Vraag iets zonder passende bronnen voor een expliciete kennislacune.
- Verander de datum naar 2025 bij looncorrecties om historische geldigheid te zien.

### Werking en grenzen

`knowledge.py` haalt passages op met FTS5 en past land- en klantfilters toe in
de zoekquery. Geldigheid, goedkeuring, bronhouder en expliciete opvolgversies
worden afzonderlijk gecontroleerd. Een bron die deze controles doorstaat is
niet automatisch inhoudelijk juist. De datum waarop een bestand is bijgewerkt
wordt getoond, maar is geen bewijs voor de juistheid of geldigheid van de inhoud.

Conflictdetectie vergelijkt handmatig vastgelegde claims in `data/sources.json`,
binnen hetzelfde land en klantbereik, voor bronnen die op de gekozen datum actief
zijn. Verschillende landen, historische versies en klantspecifieke aanvullingen
worden daardoor niet zomaar als tegenstrijdig beschouwd. Vrije tekst krijgt in
dit MVP geen automatische claimextractie; de detector bewijst niet dat bronnen
zonder gevonden conflict met elkaar overeenstemmen. Zoeken gebruikt woorden en
enkele synoniemen, geen semantische embeddings.

Zonder modelsleutel zijn antwoorden letterlijk opgebouwd uit bronpassages.
Optioneel kan `model.py` deze formuleren via een compatibele chat/completions API.
Exporteer `LLM_ENDPOINT` (de volledige endpoint-URL), `LLM_MODEL` en indien nodig
`LLM_API_KEY` in de shell; zie `.env.example`. Alleen bij antwoorden met geslaagde
broncontroles worden de vraag, context en relevante passages naar die provider
gestuurd. Elke modeluitspraak moet een bestaand bron-ID citeren. Ontbrekende of
verzonnen verwijzingen, ongeldige JSON en API-fouten leiden tot de oorspronkelijke
passages als fallback. De controle bewijst geen inhoudelijke ondersteuning van
modeluitspraken; de interface vermeldt dit expliciet.

Expertverzoeken worden opgeslagen in `data/knowledge.sqlite3`. Er worden geen
berichten verstuurd. Deze demo heeft **geen authenticatie of autorisatie**; land-
en klantfilters dienen voor relevantie, niet als beveiligingsgrens. Gebruik alleen
fictieve gegevens en bind lokaal. Voor echte bedrijfsdata zijn identity, bronrechten
bij retrieval én bronweergave, tenantisolatie en een goedgekeurde modelprovider nodig.

### Voorbeeldbronnen aanpassen

Pas `data/sources.json` aan. Dit bestand wordt ingelezen wanneer de database nog
leeg is. Stop de app en maak een backup van `data/knowledge.sqlite3` voordat je de
database verwijdert om opnieuw te importeren; daarin staan ook expertverzoeken.

### Checks

```sh
.venv/bin/python -m unittest discover -s tests -v
```
