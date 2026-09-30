# PARALLAX — SD Worx challenge

## Het concept

Een payrollconsultant moet nu antwoorden, maar de bronnen zijn het niet eens. PARALLAX maakt die twijfel
zichtbaar in een kennisdossier: waar komt elk antwoord vandaan, voor welke situatie geldt het, en waar
spreken bronnen elkaar tegen?

Daarnaast toont PARALLAX **wat er gebeurde nadat collega's een bron gebruikten**. Een ticket dat heropend werd,
een correctie in de loonrun of een escalatie telt als misgelopen. Twijfel na het lezen telt ook mee. Zo krijgt elke bron
een **trackrecord** per situatie. De bronhouder beslist met dat bewijs, publiceert een betere versie, en de
volgende collega profiteert daarvan.

**Pitch:** Herkomst vertelt waarom je een bron zou geloven. Het trackrecord vertelt of dat terecht is.

## Aansluiting bij de SD Worx-briefing (pagina 5)

| Onderdeel | Concreet in de demo |
| --- | --- |
| Eén betekenisvol probleem | Een consultant moet kiezen tussen een goedgekeurde procedure en een Teams-notitie die elkaar tegenspreken. |
| Find | Zoeken met land, klant, statuut en datum. Zoekopdrachten zonder bruikbare bron worden gebundeld tot *ontbrekende kennis*. |
| Understand | Bronpassages, bronhouder, geldigheid en verschillen staan bij elkaar. Twijfel na het lezen wordt gemeten. |
| Trust | Twee lagen: herkomst (goedkeuring, geldigheid, tegenspraak) en trackrecord (uitkomsten per situatie). |
| Detect | Tegenstrijdige claims, vervangen versies, ontbrekende eigenaars, en bronnen die gevaarlijk, onduidelijk of kapot zijn. |
| Connect | Het verzoek gaat met vraag, context, passages en bewijs uit de praktijk naar de bronhouder van het onderwerp. |
| Capture | De gemotiveerde beoordeling wordt hergebruikt. Een nieuwe versie kan een Teams-notitie formeel opnemen. |
| Zichtbaar en uitlegbaar | Vaste rekenregels, de woordanalyse van mislukte tickets en de export tonen elk getal met uitleg. |
| Menselijk oordeel | Alleen de bronhouder beslist, nooit over een eigen verzoek. De AI formuleert hoogstens een hypothese. |
| Schaal | Signalen komen uit het gewone werk, zonder extra moeite. Het trackrecord wordt beter naarmate meer collega's werken. |

Dit document beschrijft de aansluiting op de briefing, geen goedkeuring door SD Worx.

## Demo voor een video van maximaal 3 minuten

Log in als `admin` met een leeg wachtwoord. Wissel rechtsboven van perspectief.

- **0:00–0:20.** "Een klant vraagt wie het vakantiegeld van een arbeider betaalt. De goedgekeurde procedure zegt de werkgever. Een Teams-notitie zegt de vakantiekas. Welke geloof je?"
- **0:20–0:55.** Als *Sara* kies je ticket T-DEMO-01 en zoek je het antwoord. Toon het conflict en de trackrecordregels: de procedure liep bij arbeiders 40 van de 57 keer mis, de notitie 12 van de 12 keer goed. "Goedgekeurd is niet hetzelfde als juist."
- **0:55–1:15.** Kies T-DEMO-02 (bediende). Dezelfde procedure werkt daar wel: "jouw situatie valt daar niet onder". Kies dan T-DEMO-03 (maaltijdcheques): *Loopt vaak mis in de praktijk*, sinds juli.
- **1:15–1:35.** Terug naar T-DEMO-01: *Vraag een beoordeling* met de toelichting "Loopt dit via de vakantiekas?".
- **1:35–2:15.** Als *An*: open het verzoek en kies de Teams-notitie met het bewijs erbij. Open daarna het trackrecord van de procedure en toon de woordanalyse: *vakantiekas*, *werkgever*, *arbeiders*. Publiceer versie 2 en neem de notitie mee op.
- **2:15–2:40.** Als *Kim*: open het overzicht met het raster, de prioriteiten en de ontbrekende kennis rond flexi-jobs. Klik *Simuleer volgende maand*: versie 2 bouwt een nieuw trackrecord op.
- **2:40–2:55.** Toon de evaluatiekaart (67/80 herkend, 2 valse alarmen op 620) en de privacyregel "We meten bronnen, geen mensen". Sluit af met de pitch.

## Inzendregels uit de deelnemersgids (pagina's 6–7, 11–12)

Voor de inzending moet het team nog de volgende zaken voltooien:

- Controleer dat de ingediende versie binnen het officiële bouwtijdvak is gemaakt.
- Maak de korte beschrijving en een demovideo van minder dan 3 minuten.
- Voer de verplichte **Aikido AI Code Audit** uit op de in te dienen repository en branch.
  Bewaar de voor- en nascreenshots, herstel de bevindingen en voeg beide screenshots toe.
- Maak de definitieve repository toegankelijk zoals de hackathon voorschrijft en
  voeg de juiste GitHub-link toe. Deel geen echte bedrijfsdata, sleutels of geheimen.
- Controleer README, startinstructies, links en de expliciet vermelde beperkingen.
- Laat één teamlid via Builderbase indienen vóór de officiële deadline.
- Bevries de ingediende versie na de definitieve inzending.

De lokale tests en codecontroles zijn **geen vervanging voor de Aikido-audit**.
