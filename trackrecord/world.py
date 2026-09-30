"""The fictitious world of the demo: people, clients, documents, topics.

Nothing here is real SD Worx data or payroll advice. Names, clients, rules and
amounts are invented so the prototype can run without confidential data.
"""
from datetime import date

DEMO_USERS = [
    # id, username, display name, role
    ("u-sara", "sara", "Sara Willems", "consultant"),
    ("u-an", "an", "An Peeters", "owner"),
    ("u-kim", "kim", "Kim Janssens", "manager"),
]

# Document owners without a demo login.
OTHER_OWNERS = [
    ("u-jonas", "Jonas Maes"), ("u-lotte", "Lotte Claes"), ("u-pieter", "Pieter Wouters"),
    ("u-eline", "Eline Jacobs"), ("u-sanne", "Sanne de Vries"),
]

OTHER_CONSULTANTS = [
    "Tom Verbeke", "Lisa Goossens", "Bram De Smet", "Nina Mertens", "Wout Hermans",
    "Fien Aerts", "Jens Dubois", "Lien Vermeulen", "Arne Coppens", "Eva Lambrechts",
    "Ruben Declercq", "Hanne Stevens", "Milan Wuyts", "Julie Segers", "Kobe Van Damme",
    "Emma De Wilde", "Senne Michiels", "Lore Martens", "Thibo Verstraete", "Amber Smets",
    "Robbe Pauwels", "Marie Willaert", "Lars De Backer", "Ines Timmermans", "Daan Bosman",
    "Femke Visser", "Joris Bakker", "Noor Dekker", "Stijn Vos",
]

CLIENTS = [
    # id, name, country, joint committee (PC) or NL collective agreement, size
    ("c-noordzand", "Bouwbedrijf Noordzand", "BE", "PC 124", "middel"),
    ("c-kobalt", "Softwarehuis Kobalt", "BE", "PC 200", "middel"),
    ("c-ostara", "Metaalwerken Ostara", "BE", "PC 111", "groot"),
    ("c-lindeboom", "Brasserie Lindeboom", "BE", "PC 302", "klein"),
    ("c-heidebloem", "Zorggroep Heidebloem", "BE", "PC 330", "groot"),
    ("c-vlasbloem", "Textiel Vlasbloem", "BE", "PC 120", "middel"),
    ("c-ringlaan", "Logistiek Ringlaan", "BE", "PC 140", "groot"),
    ("c-zilverberk", "Bouwgroep Zilverberk", "BE", "PC 124", "groot"),
    ("c-klaproos", "Bakkerij Klaproos", "BE", "PC 118", "klein"),
    ("c-duinhoek", "Hotel Duinhoek", "BE", "PC 302", "middel"),
    ("c-pixelwerf", "Pixelwerf Digital", "BE", "PC 200", "klein"),
    ("c-merelhof", "Rusthuis Merelhof", "BE", "PC 330", "middel"),
    ("c-staalkade", "Staalkade Engineering", "BE", "PC 111", "middel"),
    ("c-kempenhout", "Schrijnwerkerij Kempenhout", "BE", "PC 124", "klein"),
    ("c-lichtpunt", "Adviesbureau Lichtpunt", "BE", "PC 200", "middel"),
    ("c-havenzicht", "Havenzicht Transport", "BE", "PC 140", "middel"),
    ("c-graanschuur", "Maalderij Graanschuur", "BE", "PC 118", "middel"),
    ("c-scheldebouw", "Scheldebouw Renovatie", "BE", "PC 124", "middel"),
    ("c-boekvink", "Uitgeverij Boekvink", "BE", "PC 200", "klein"),
    ("c-kustlijn", "Kustlijn Retail", "BE", "PC 311", "groot"),
    ("c-noorderlicht", "Noorderlicht BV", "NL", "NL-cao", "middel"),
    ("c-polderveld", "Polderveld Logistiek BV", "NL", "NL-cao", "groot"),
    ("c-waddenzout", "Waddenzout BV", "NL", "NL-cao", "klein"),
    ("c-tulpenhof", "Tulpenhof Zorg BV", "NL", "NL-cao", "middel"),
]

# Sara's portfolio is fixed so the demo story is always the same.
SARA_CLIENTS = ["c-noordzand", "c-kobalt", "c-lindeboom", "c-scheldebouw"]

ARBEIDER_SHARE = {"PC 124": 0.85, "PC 111": 0.65, "PC 120": 0.6, "PC 140": 0.6, "PC 118": 0.6,
                  "PC 302": 0.5, "PC 311": 0.15, "PC 330": 0.2, "PC 200": 0.05}
SIZE_WEIGHT = {"klein": 1, "middel": 2, "groot": 3}

TOPICS = {
    "vakantiegeld": dict(
        label="Vakantiegeld", share=0.14, nl=True,
        queries=["vakantiegeld berekenen", "dubbel vakantiegeld uitbetalen",
                 "wanneer vakantiegeld betalen", "vakantiegeld uitbetaling mei"],
        subjects=["Vakantiegeld berekenen voor een {statute}", "Uitbetaling dubbel vakantiegeld",
                  "Vakantiegeld bij uitdiensttreding"],
        questions=["Wie betaalt het vakantiegeld hier uit?",
                   "Welk loon neem je als basis voor het dubbel vakantiegeld?"]),
    "eindejaarspremie": dict(
        label="Eindejaarspremie", share=0.10, nl=False,
        queries=["eindejaarspremie pro rata", "eindejaarspremie berekenen", "dertiende maand deeltijds"],
        subjects=["Eindejaarspremie voor een {statute} die in de loop van het jaar startte",
                  "Pro rata eindejaarspremie"],
        questions=["Welke paritair comité-regels gelden voor de eindejaarspremie?"]),
    "indexering": dict(
        label="Indexering", share=0.08, nl=False,
        queries=["indexering paritair comité", "loonindexering januari", "index toepassen lonen"],
        subjects=["Indexering niet zichtbaar op loonbrief", "Wanneer indexeren voor dit PC?"],
        questions=["Is de indexering voor dit comité al toegepast?"]),
    "maaltijdcheques": dict(
        label="Maaltijdcheques", share=0.10, nl=False,
        queries=["maaltijdcheques werkgeversaandeel", "bedrag maaltijdcheque", "maaltijdcheques deeltijds"],
        subjects=["Werkgeversaandeel maaltijdcheques controleren", "Aantal maaltijdcheques voor een {statute}"],
        questions=["Welk bedrag geldt nu voor maaltijdcheques?"]),
    "ecocheques": dict(
        label="Ecocheques", share=0.04, nl=False,
        queries=["ecocheques referteperiode", "ecocheques pro rata"],
        subjects=["Ecocheques voor nieuwe werknemer"],
        questions=["Tellen afwezigheden mee voor ecocheques?"]),
    "gewaarborgd_loon": dict(
        label="Ziekte en gewaarborgd loon", share=0.12, nl=True,
        queries=["gewaarborgd loon ziekte", "ziekte herval 14 dagen", "loondoorbetaling ziekte"],
        subjects=["Gewaarborgd loon voor een {statute}", "Herval na ziekte"],
        questions=["Is dit een herval of een nieuwe ziekteperiode?"]),
    "tijdelijke_werkloosheid": dict(
        label="Tijdelijke werkloosheid", share=0.06, nl=False,
        queries=["tijdelijke werkloosheid aangifte", "economische werkloosheid verwerken"],
        subjects=["Tijdelijke werkloosheid registreren"],
        questions=["Welke sectorale aanvulling geldt bij tijdelijke werkloosheid?"]),
    "loonbeslag": dict(
        label="Loonbeslag", share=0.07, nl=False,
        queries=["loonbeslag beslagbaar deel", "loonbeslag berekenen", "loonbeslag kinderen ten laste"],
        subjects=["Nieuw loonbeslag verwerken", "Loonbeslag met kinderen ten laste"],
        questions=["Hoe bereken je het beslagbare deel precies?"]),
    "opzeg": dict(
        label="Opzegtermijn", share=0.07, nl=False,
        queries=["opzegtermijn berekenen", "opzeggingsvergoeding outplacement"],
        subjects=["Opzegtermijn voor een {statute} berekenen", "Opzeggingsvergoeding berekenen"],
        questions=["Geldt er een sectorale afwijking voor de opzegtermijn?"]),
    "woon_werk": dict(
        label="Woon-werkverkeer", share=0.06, nl=False,
        queries=["fietsvergoeding kilometer", "tussenkomst treinabonnement"],
        subjects=["Fietsvergoeding instellen", "Tussenkomst openbaar vervoer"],
        questions=["Welke fietsvergoeding geldt in deze sector?"]),
    "bedrijfswagen": dict(
        label="Bedrijfswagen", share=0.05, nl=False,
        queries=["voordeel alle aard bedrijfswagen", "vaa wagen co2"],
        subjects=["Voordeel alle aard nieuwe bedrijfswagen"],
        questions=["Welke cataloguswaarde gebruik je voor het voordeel alle aard?"]),
    "overuren": dict(
        label="Overuren", share=0.05, nl=True,
        queries=["overuren inhaalrust", "vrijwillige overuren", "overwerk vergoeding"],
        subjects=["Overuren registreren voor een {statute}"],
        questions=["Heeft deze overuur recht op inhaalrust?"]),
    # Planted knowledge gap: people keep searching, but no document exists.
    "flexi_job": dict(
        label="Flexi-jobs", share=0.05, nl=False, gap=True,
        queries=["flexi-job loon berekenen", "flexi-job vakantiegeld", "flexiloon horeca minimum",
                 "flexi-job maximum uren"],
        subjects=["Eerste flexi-jobber verwerken", "Flexiloon en flexivakantiegeld"],
        questions=["Hoe verwerk ik een flexi-job in de loonrun?", "Welk minimum flexiloon geldt er nu?",
                   "Krijgt een flexi-jobber ook flexivakantiegeld?"]),
    "fiscaal": dict(
        label="Fiscale fiches", share=0.01, nl=False,
        queries=["fiscale fiche corrigeren", "281.10 verbeterende fiche"],
        subjects=["Fiscale fiche corrigeren"],
        questions=["Hoe maak je een verbeterende fiche?"]),
}

DOCUMENTS = [
    # id, title, topic, country, owner, weight within topic, body
    ("TR-VAK-01", "Vakantiegeld: berekening en uitbetaling", "vakantiegeld", "BE", "u-an", 0.7,
     "Het enkel en dubbel vakantiegeld wordt door de werkgever uitbetaald, meestal bij de verwerking "
     "van mei of juni. Bereken het dubbel vakantiegeld op het brutomaandloon van de maand van "
     "uitbetaling en verwerk het als afzonderlijke looncode. Controleer vooraf het aantal "
     "gelijkgestelde dagen in het vakantiedienstjaar."),
    ("TR-VAK-02", "Vakantieattest bij uitdiensttreding", "vakantiegeld", "BE", "u-an", 0.2,
     "Bij uitdiensttreding van een bediende betaalt de werkgever het vertrekvakantiegeld uit en "
     "levert hij een vakantieattest af met de gewerkte en gelijkgestelde dagen."),
    ("TR-VAK-03", "Checklist vakantiegeld in de mei-verwerking", "vakantiegeld", "BE", "u-an", 0.1,
     "Controleer vóór de mei-verwerking: het statuut van elke werknemer, gelijkgestelde dagen, "
     "deeltijdse prestaties en vakantieattesten van een vorige werkgever."),
    ("TR-EJP-01", "Eindejaarspremie: pro-rataberekening", "eindejaarspremie", "BE", "u-an", 0.7,
     "Werknemers die niet het volledige jaar in dienst waren, krijgen een eindejaarspremie pro rata. "
     "Pas de regels van het bevoegde paritair comité toe en houd rekening met gelijkgestelde periodes."),
    ("TR-EJP-02", "Eindejaarspremie per paritair comité", "eindejaarspremie", "BE", "u-an", 0.3,
     "Overzicht van berekeningsbasis, betaaldatum en anciënniteitsvoorwaarde per paritair comité, "
     "met verwijzing naar de sectorale cao."),
    ("TR-IDX-01", "Indexering: kalender per paritair comité", "indexering", "BE", "u-jonas", 0.6,
     "Elk paritair comité heeft een eigen indexeringsmechanisme en -moment. Gebruik de kalender om "
     "per klant te bepalen wanneer en met welk percentage de lonen aangepast worden."),
    ("TR-IDX-02", "Indexering controleren na de loonrun", "indexering", "BE", "u-jonas", 0.4,
     "Vergelijk na de loonrun het gemiddelde brutoloon per paritair comité met de vorige maand. Een "
     "afwijking van meer dan het verwachte percentage wijst op een ontbrekende of dubbele indexering."),
    ("TR-MC-01", "Maaltijdcheques: werkgevers- en werknemersaandeel", "maaltijdcheques", "BE", "u-jonas", 0.8,
     "Het werkgeversaandeel bedraagt maximaal het bedrag uit de parameterlijst van 1 januari; het "
     "werknemersaandeel minimaal het wettelijke minimum. Maaltijdcheques worden toegekend per "
     "effectief gewerkte dag."),
    ("TR-MC-02", "Maaltijdcheques bij deeltijdse prestaties", "maaltijdcheques", "BE", "u-jonas", 0.2,
     "Bij deeltijdse werknemers wordt het aantal maaltijdcheques berekend op de effectief gepresteerde "
     "uren gedeeld door de normale dagelijkse arbeidsduur van een voltijdse werknemer."),
    ("TR-ECO-01", "Ecocheques: referteperiode en bedrag", "ecocheques", "BE", "u-jonas", 1.0,
     "De referteperiode loopt normaal van 1 juni tot en met 31 mei. Het bedrag wordt pro rata "
     "toegekend volgens de prestaties in de referteperiode."),
    ("TR-ZIE-01", "Gewaarborgd loon bij ziekte", "gewaarborgd_loon", "BE", "u-lotte", 0.7,
     "De werkgever betaalt gewaarborgd loon tijdens de eerste weken van arbeidsongeschiktheid. "
     "Controleer het ziektebriefje, de anciënniteit en een eventuele herval binnen 14 dagen."),
    ("TR-ZIE-02", "Herval en nieuwe arbeidsongeschiktheid", "gewaarborgd_loon", "BE", "u-lotte", 0.3,
     "Een nieuwe arbeidsongeschiktheid binnen 14 dagen na het einde van de vorige geldt als herval, "
     "tenzij de werknemer een attest van een andere ziekte voorlegt."),
    ("TR-TW-01", "Tijdelijke werkloosheid: aangifte en verwerking", "tijdelijke_werkloosheid", "BE", "u-lotte", 1.0,
     "Registreer de dagen tijdelijke werkloosheid in de maand zelf en doe de elektronische aangifte "
     "tijdig. Controleer eventuele sectorale aanvullingen."),
    ("TR-BES-01", "Loonbeslag: beslagbaar deel berekenen", "loonbeslag", "BE", "u-pieter", 0.8,
     "Bereken het beslagbare deel op het nettoloon met de grensbedragen van de schijven. Pas de "
     "verhoging per kind ten laste toe na aanvraag door de werknemer."),
    ("TR-BES-02", "Loonbeslag: volgorde van meerdere beslagen", "loonbeslag", "BE", "u-pieter", 0.2,
     "Bij meerdere beslagen geldt de volgorde van betekening, behalve voor onderhoudsgeld dat "
     "voorrang heeft."),
    ("TR-OPZ-01", "Opzegtermijn berekenen", "opzeg", "BE", "u-pieter", 0.7,
     "De opzegtermijn hangt af van de anciënniteit op de startdatum van de opzeg. Gebruik de "
     "wettelijke tabel en controleer of een sectorale regeling afwijkt."),
    ("TR-OPZ-02", "Opzeggingsvergoeding en outplacement", "opzeg", "BE", "u-pieter", 0.3,
     "Bij een opzeggingsvergoeding van minstens 30 weken heeft de werknemer recht op outplacement."),
    ("TR-WW-01", "Fietsvergoeding", "woon_werk", "BE", "u-eline", 0.5,
     "De fietsvergoeding wordt per gereden kilometer toegekend volgens de sectorale of "
     "ondernemingsregeling, binnen het fiscaal vrijgestelde maximum."),
    ("TR-WW-02", "Tussenkomst openbaar vervoer", "woon_werk", "BE", "u-eline", 0.5,
     "De werkgever komt tussen in de kosten van het treinabonnement volgens het nationale akkoord of "
     "een gunstigere sectorregeling."),
    ("TR-BW-01", "Voordeel alle aard bedrijfswagen", "bedrijfswagen", "BE", "u-eline", 1.0,
     "Het voordeel alle aard wordt berekend op basis van de cataloguswaarde, de leeftijd van de wagen "
     "en de CO2-uitstoot, met een wettelijk minimum per jaar."),
    ("TR-OVU-01", "Overuren en inhaalrust", "overuren", "BE", "u-eline", 0.6,
     "Overuren geven recht op inhaalrust en een overloontoeslag. Registreer ze in de maand waarin ze "
     "gepresteerd zijn."),
    ("TR-OVU-02", "Vrijwillige overuren", "overuren", "BE", "u-eline", 0.4,
     "Vrijwillige overuren geven geen recht op inhaalrust maar wel op overloon, binnen het jaarlijkse "
     "maximum en na schriftelijk akkoord."),
    ("TR-FIS-01", "Fiscale fiche corrigeren", "fiscaal", "BE", "u-pieter", 1.0,
     "Een correctie van de fiscale fiche gebeurt via een verbeterende fiche met hetzelfde fichenummer."),
    ("TR-NL-VAK", "Vakantiebijslag (Nederland)", "vakantiegeld", "NL", "u-sanne", 1.0,
     "De vakantiebijslag bedraagt minimaal 8% van het brutoloon en wordt meestal in mei of juni "
     "uitbetaald, tenzij de cao iets anders bepaalt."),
    ("TR-NL-ZIE", "Loondoorbetaling bij ziekte (Nederland)", "gewaarborgd_loon", "NL", "u-sanne", 1.0,
     "De werkgever betaalt bij ziekte het loon door volgens de wet en de cao; leg de afspraken over "
     "aanvullingen vast in het klantdossier."),
    ("TR-NL-OVU", "Overwerk volgens de cao (Nederland)", "overuren", "NL", "u-sanne", 1.0,
     "Overwerk wordt vergoed volgens de toepasselijke cao; zonder cao-regeling gelden de afspraken in "
     "de arbeidsovereenkomst."),
]

# --- Planted problems (the ground truth the evaluation checks against) --------------------

# Extra failure probability of the planted (first) version, optionally limited to a
# context segment or to a period after an external change.
DEFECTS = {
    "TR-VAK-01": dict(extra=0.55, segment=("statute", "arbeider"), comments=[
        "Klant meldt dubbele betaling: vakantiegeld van arbeiders loopt via de vakantiekas, niet via de werkgever.",
        "Correctie: vakantiegeld arbeider ten onrechte via het loon uitbetaald, het vakantiefonds betaalt uit.",
        "Arbeider kreeg enkel en dubbel vakantiegeld via de werkgever; dat moet via de vakantiekas. Terugvordering nodig.",
        "Vakantiegeld van arbeiders hoorde niet in de mei-run: de uitbetaling gebeurt door de vakantiekas.",
    ]),
    "TR-BES-01": dict(extra=0.35, comments=[
        "Beslagbaar deel fout: grensbedragen van vorig jaar gebruikt.",
        "Verhoging per kind ten laste niet toegepast op het loonbeslag.",
        "Schijven voor loonbeslag verkeerd toegepast, te veel ingehouden.",
        "Beslag berekend op het brutoloon in plaats van het nettoloon.",
    ]),
    "TR-MC-01": dict(extra=0.33, since=date(2026, 7, 1), comments=[
        "Werkgeversaandeel maaltijdcheques niet aangepast aan het nieuwe maximum sinds 1 juli.",
        "Oud bedrag voor maaltijdcheques gebruikt; klant verwacht het verhoogde werkgeversaandeel.",
        "Correctie maaltijdcheques: parameter van januari toegepast, maar sinds juli geldt een nieuw bedrag.",
    ]),
}

# Probability of visible doubt after reading the planted version (default BASE_DOUBT).
DOUBT = {"TR-EJP-01": 0.62, "TR-BES-01": 0.55, "TR-VAK-01": 0.07}

# What people ask in Teams right after reading an unclear document.
FOLLOW_UPS = {
    "TR-EJP-01": [
        "Hoe bereken je de pro rata bij deeltijdse tewerkstelling?",
        "Telt tijdelijke werkloosheid mee als gelijkgestelde periode voor de eindejaarspremie?",
        "Welke referteperiode gebruik je bij indiensttreding midden in het jaar?",
        "Is de pro rata per maand of per dag?",
    ],
    "TR-BES-01": [
        "Welke grensbedragen gelden er dit jaar voor loonbeslag?",
        "Moet de verhoging per kind ook bij onderhoudsgeld?",
    ],
}

NOISE_COMMENTS = [
    "Klant gaf een verkeerd aantal prestaties door.",
    "Late aanlevering van variabele looncomponenten.",
    "Typfout in het uurrooster, aangepast na controle.",
    "Werknemer uit dienst vóór de verwerking, prestaties gecorrigeerd.",
    "Bankrekening gewijzigd na de verwerking.",
    "Klant vroeg achteraf een andere looncode.",
    "Dubbele registratie van een afwezigheid.",
    "Verkeerde startdatum doorgegeven door de klant.",
]

EXPECTED = {
    "TR-VAK-01": ("dangerous", "Geplant: fout voor arbeiders (vakantiekas vergeten), mensen twijfelen niet."),
    "TR-EJP-01": ("unclear", "Geplant: te vaag, veel vervolgvragen, maar de uitkomst klopt."),
    "TR-BES-01": ("broken", "Geplant: veel twijfel én veel correcties."),
    "TR-MC-01": ("dangerous", "Geplant: correct tot 1 juli 2026, daarna verouderd."),
    "GAP:flexi_job": ("gap", "Geplant: veel zoekopdrachten over flexi-jobs, geen document."),
}

DEMO_TICKETS = [
    # id, client, topic, statute, subject, opened_at
    ("T-DEMO-01", "c-noordzand", "vakantiegeld", "arbeider",
     "Vakantiegeld voor arbeider die in juni uit dienst ging", "2026-09-29T09:12:00"),
    ("T-DEMO-02", "c-kobalt", "eindejaarspremie", "bediende",
     "Eindejaarspremie voor deeltijdse bediende gestart in april", "2026-09-29T14:40:00"),
    ("T-DEMO-03", "c-scheldebouw", "maaltijdcheques", "arbeider",
     "Werkgeversaandeel maaltijdcheques na de aanpassing van juli", "2026-09-30T08:31:00"),
    ("T-DEMO-04", "c-kobalt", "vakantiegeld", "bediende",
     "Dubbel vakantiegeld voor bediende met loonsverhoging", "2026-09-30T10:05:00"),
]
