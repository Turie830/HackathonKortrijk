"""The fictitious world of the demo: people, teams, clients, topics and planted problems.

Nothing here is real SD Worx data or payroll advice. The sources themselves live
in data/sources.json (PARALLAX's catalogue); this file only describes who uses
them, how often, and which problems we deliberately hid for the evaluation.
"""
from datetime import date

DEMO_USERS = [
    # id, username, display name, role
    ("u-sara", "sara", "Sara Willems", "consultant"),
    ("u-an", "an", "An Peeters", "owner"),
    ("u-kim", "kim", "Kim Janssens", "manager"),
    ("u-admin", "admin", "Demo-beheer", "admin"),
]
# The admin account only switches between these perspectives; it never acts as itself.
ACT_AS = ["u-sara", "u-an", "u-kim"]

# Source owners in PARALLAX are teams. Only team members may review for that team.
TEAMS = {
    "u-an": ["Beloning & Voordelen", "Payroll Planning"],
    "u-kim": ["Knowledge Operations"],
    "u-jonas": ["Afwezigheden & Arbeidsduur"],
    "u-pieter": ["Sociaal Juridisch"],
    "u-lotte": ["Payroll Quality", "Payroll Operations"],
    "u-sanne": ["Payroll Nederland"],
    "u-acme": ["Demo Acme accountteam"],
}
OTHER_OWNERS = [("u-jonas", "Jonas Maes"), ("u-pieter", "Pieter Wouters"), ("u-lotte", "Lotte Claes"),
                ("u-sanne", "Sanne de Vries"), ("u-acme", "Eline Jacobs")]

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
    ("demo-acme", "Demo Acme", "BE", "PC 200", "middel"),
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
SARA_CLIENTS = ["demo-acme", "c-noordzand", "c-kobalt", "c-lindeboom", "c-scheldebouw"]

ARBEIDER_SHARE = {"PC 124": 0.85, "PC 111": 0.65, "PC 120": 0.6, "PC 140": 0.6, "PC 118": 0.6,
                  "PC 302": 0.5, "PC 311": 0.15, "PC 330": 0.2, "PC 200": 0.05}
SIZE_WEIGHT = {"klein": 1, "middel": 2, "groot": 3}

TOPICS = {
    "vakantiegeld": dict(
        label="Vakantiegeld", share=0.14, nl=True,
        queries=["vakantiegeld berekenen", "dubbel vakantiegeld uitbetalen", "wie betaalt het vakantiegeld",
                 "vakantiegeld uitbetaling mei"],
        subjects=["Vakantiegeld berekenen voor een {statute}", "Uitbetaling dubbel vakantiegeld",
                  "Vakantiegeld bij uitdiensttreding"],
        questions=["Wie betaalt het vakantiegeld hier uit?",
                   "Welk loon neem je als basis voor het dubbel vakantiegeld?"]),
    "eindejaarspremie": dict(
        label="Eindejaarspremie", share=0.10, nl=False,
        queries=["eindejaarspremie pro rata", "eindejaarspremie berekenen", "dertiende maand deeltijds"],
        subjects=["Eindejaarspremie voor een {statute} die in de loop van het jaar startte",
                  "Pro rata eindejaarspremie"],
        questions=["Welke regels van het paritair comité gelden voor de eindejaarspremie?"]),
    "indexering": dict(
        label="Indexering", share=0.07, nl=False,
        queries=["indexering paritair comité", "indexering januari", "lonen indexeren"],
        subjects=["Indexering niet zichtbaar op de loonbrief", "Wanneer indexeren voor dit PC?"],
        questions=["Is de indexering voor dit comité al toegepast?"]),
    "maaltijdcheques": dict(
        label="Maaltijdcheques", share=0.10, nl=False,
        queries=["maaltijdcheques werkgeversaandeel", "bedrag maaltijdcheque", "maaltijdcheques deeltijds"],
        subjects=["Werkgeversaandeel maaltijdcheques nakijken", "Aantal maaltijdcheques voor een {statute}"],
        questions=["Welk bedrag geldt nu voor maaltijdcheques?"]),
    "ecocheques": dict(
        label="Ecocheques", share=0.04, nl=False,
        queries=["ecocheques referteperiode", "ecocheques pro rata"],
        subjects=["Ecocheques voor een nieuwe werknemer"],
        questions=["Tellen afwezigheden mee voor ecocheques?"]),
    "ziekte": dict(
        label="Ziekte en gewaarborgd loon", share=0.11, nl=True,
        queries=["gewaarborgd loon ziekte", "ziekte herval 14 dagen", "loondoorbetaling bij ziekte"],
        subjects=["Gewaarborgd loon voor een {statute}", "Herval na ziekte"],
        questions=["Is dit een herval of een nieuwe ziekteperiode?"]),
    "werkloosheid": dict(
        label="Tijdelijke werkloosheid", share=0.05, nl=False,
        queries=["tijdelijke werkloosheid aangifte", "economische werkloosheid verwerken"],
        subjects=["Tijdelijke werkloosheid registreren"],
        questions=["Welke sectorale aanvulling geldt bij tijdelijke werkloosheid?"]),
    "loonbeslag": dict(
        label="Loonbeslag", share=0.07, nl=False,
        queries=["loonbeslag beslagbaar deel", "loonbeslag berekenen", "loonbeslag kinderen ten laste"],
        subjects=["Nieuw loonbeslag verwerken", "Loonbeslag met kinderen ten laste"],
        questions=["Hoe bereken je het beslagbare deel precies?"]),
    "opzeg": dict(
        label="Opzegtermijn", share=0.06, nl=False,
        queries=["opzegtermijn berekenen", "opzeggingsvergoeding outplacement"],
        subjects=["Opzegtermijn voor een {statute} berekenen", "Opzeggingsvergoeding berekenen"],
        questions=["Geldt er een sectorale afwijking voor de opzegtermijn?"]),
    "woon_werk": dict(
        label="Woon-werkverkeer", share=0.05, nl=False,
        queries=["fietsvergoeding kilometer", "tussenkomst treinabonnement"],
        subjects=["Fietsvergoeding instellen", "Tussenkomst openbaar vervoer"],
        questions=["Welke fietsvergoeding geldt in deze sector?"]),
    "bedrijfswagen": dict(
        label="Bedrijfswagen", share=0.04, nl=False,
        queries=["voordeel alle aard bedrijfswagen", "bedrijfswagen co2"],
        subjects=["Voordeel alle aard van een nieuwe bedrijfswagen"],
        questions=["Welke cataloguswaarde gebruik je voor het voordeel alle aard?"]),
    "overuren": dict(
        label="Overuren", share=0.05, nl=True,
        queries=["overuren inhaalrust", "vrijwillige overuren", "overwerk vergoeding"],
        subjects=["Overuren registreren voor een {statute}"],
        questions=["Heeft dit overuur recht op inhaalrust?"]),
    "fiscaal": dict(
        label="Fiscale fiches", share=0.01, nl=False,
        queries=["fiscale fiche herstellen", "verbeterende fiche"],
        subjects=["Fiscale fiche herstellen"],
        questions=["Hoe maak je een verbeterende fiche?"]),
    # PARALLAX's original topics
    "deadline": dict(
        label="Deadline maandverwerking", share=0.05, nl=True,
        queries=["deadline maandelijkse verwerking", "tot wanneer wijzigingen doorgeven"],
        subjects=["Klant vraagt tot wanneer wijzigingen binnen mogen"],
        questions=["Is de deadline nog dinsdag of nu woensdag?"]),
    "looncorrectie": dict(
        label="Looncorrecties", share=0.04, nl=False,
        queries=["looncorrectie controleren", "looncorrectie goedkeuren"],
        subjects=["Looncorrectie na een fout in de verwerking"],
        questions=["Moet een tweede consultant deze correctie nakijken?"]),
    "overdracht": dict(
        label="Klantoverdracht", share=0.03, nl=False,
        queries=["klantdossier overdragen", "overdracht nieuwe consultant"],
        subjects=["Klantdossier overdragen aan een collega"],
        questions=["Wie bevestigt de overdracht?"]),
    "archivering": dict(
        label="Archivering", share=0.01, nl=False,
        queries=["dossier archiveren"],
        subjects=["Afgesloten dossier archiveren"],
        questions=["Wat is de geldige archiveringsprocedure?"]),
    # Planted knowledge gap: people keep searching, but no source exists.
    "flexi": dict(
        label="Flexi-jobs", share=0.05, nl=False, gap=True,
        queries=["flexi-job loon berekenen", "flexi-job vakantiegeld", "flexiloon horeca minimum",
                 "flexi-job maximum uren"],
        subjects=["Eerste flexi-jobber verwerken", "Flexiloon en flexivakantiegeld"],
        questions=["Hoe verwerk ik een flexi-job in de loonrun?", "Welk minimum flexiloon geldt er nu?",
                   "Krijgt een flexi-jobber ook flexivakantiegeld?"]),
}

# How often a source is picked among the sources that apply to a ticket (default 0.5).
USAGE_WEIGHT = {
    "BE-VAKANTIEGELD": 0.7, "BE-VAKANTIEGELD-TEAMS": 0.45, "BE-VAKANTIEATTEST": 0.25,
    "BE-VAKANTIEGELD-CHECKLIST": 0.1, "BE-EINDEJAARSPREMIE": 0.7, "BE-EINDEJAARSPREMIE-PC": 0.3,
    "BE-INDEXERING": 0.6, "BE-INDEXERING-CONTROLE": 0.4, "BE-MAALTIJDCHEQUES": 0.8,
    "BE-MAALTIJDCHEQUES-DEELTIJDS": 0.2, "BE-GEWAARBORGD-LOON": 0.7, "BE-HERVAL": 0.3,
    "BE-LOONBESLAG": 0.8, "BE-LOONBESLAG-VOLGORDE": 0.2, "BE-OPZEGTERMIJN": 0.7,
    "BE-OPZEGGINGSVERGOEDING": 0.3, "BE-OVERUREN": 0.6, "BE-VRIJWILLIGE-OVERUREN": 0.4,
    "BE-DEADLINE-POLICY": 0.8, "BE-DEADLINE-CHAT": 0.2, "ACME-HANDOVER": 0.6, "BE-OWNERLESS": 0.5,
}

# --- Planted problems (the ground truth the evaluation checks against) --------------------

# Extra failure probability of the planted (original) source, optionally limited to a
# context segment or to a period after an external change.
DEFECTS = {
    "BE-VAKANTIEGELD": dict(extra=0.55, segment=("statute", "arbeider"), comments=[
        "Klant meldt dubbele betaling: vakantiegeld van arbeiders loopt via de vakantiekas, niet via de werkgever.",
        "Correctie: vakantiegeld arbeider ten onrechte via het loon uitbetaald, het vakantiefonds betaalt uit.",
        "Arbeider kreeg enkel en dubbel vakantiegeld via de werkgever; dat moet via de vakantiekas. Terugvordering nodig.",
        "Vakantiegeld van arbeiders hoorde niet in de mei-run: de uitbetaling gebeurt door de vakantiekas.",
    ]),
    "BE-LOONBESLAG": dict(extra=0.35, comments=[
        "Beslagbaar deel fout: grensbedragen van vorig jaar gebruikt.",
        "Verhoging per kind ten laste niet toegepast op het loonbeslag.",
        "Schijven voor loonbeslag verkeerd toegepast, te veel ingehouden.",
        "Beslag berekend op het brutoloon in plaats van het nettoloon.",
    ]),
    "BE-MAALTIJDCHEQUES": dict(extra=0.33, since=date(2026, 7, 1), comments=[
        "Werkgeversaandeel maaltijdcheques niet aangepast aan het nieuwe maximum sinds 1 juli.",
        "Oud bedrag voor maaltijdcheques gebruikt; klant verwacht het verhoogde werkgeversaandeel.",
        "Correctie maaltijdcheques: parameter van januari toegepast, maar sinds juli geldt een nieuw bedrag.",
    ]),
}

# Probability of visible doubt after reading the planted source (default: normal doubt).
DOUBT = {"BE-EINDEJAARSPREMIE": 0.62, "BE-LOONBESLAG": 0.55, "BE-VAKANTIEGELD": 0.07}

# What people ask colleagues right after reading an unclear source.
FOLLOW_UPS = {
    "BE-EINDEJAARSPREMIE": [
        "Hoe bereken je de pro rata bij deeltijdse tewerkstelling?",
        "Telt tijdelijke werkloosheid mee als gelijkgestelde periode voor de eindejaarspremie?",
        "Welke referteperiode gebruik je bij indiensttreding midden in het jaar?",
        "Is de pro rata per maand of per dag?",
    ],
    "BE-LOONBESLAG": [
        "Welke grensbedragen gelden er dit jaar voor loonbeslag?",
        "Moet de verhoging per kind ook bij onderhoudsgeld?",
    ],
}

NOISE_COMMENTS = [
    "Klant gaf een verkeerd aantal prestaties door.",
    "Late aanlevering van variabele looncomponenten.",
    "Typfout in het uurrooster, aangepast na controle.",
    "Werknemer uit dienst vóór de verwerking, prestaties aangepast.",
    "Bankrekening gewijzigd na de verwerking.",
    "Klant vroeg achteraf een andere looncode.",
    "Dubbele registratie van een afwezigheid.",
    "Verkeerde startdatum doorgegeven door de klant.",
]

EXPECTED = {
    "BE-VAKANTIEGELD": ("dangerous", "Geplant: fout voor arbeiders (vakantiekas vergeten), lezers twijfelen niet."),
    "BE-EINDEJAARSPREMIE": ("unclear", "Geplant: te vaag, veel vervolgvragen, maar de uitkomst klopt."),
    "BE-LOONBESLAG": ("broken", "Geplant: veel twijfel én veel correcties."),
    "BE-MAALTIJDCHEQUES": ("dangerous", "Geplant: correct tot 1 juli 2026, daarna verouderd."),
    "GAP:flexi": ("gap", "Geplant: veel zoekopdrachten over flexi-jobs, geen bron."),
}

DEMO_TICKETS = [
    # id, client, topic, statute, subject, question, opened_at
    ("T-DEMO-01", "c-noordzand", "vakantiegeld", "arbeider",
     "Vakantiegeld voor een arbeider die in juni uit dienst ging",
     "Wie betaalt het vakantiegeld van een arbeider, en wanneer?", "2026-09-29T09:12:00"),
    ("T-DEMO-02", "c-kobalt", "vakantiegeld", "bediende",
     "Dubbel vakantiegeld voor een bediende met loonsverhoging",
     "Hoe bereken ik het dubbel vakantiegeld van een bediende?", "2026-09-29T14:40:00"),
    ("T-DEMO-03", "c-scheldebouw", "maaltijdcheques", "arbeider",
     "Werkgeversaandeel maaltijdcheques na de aanpassing van juli",
     "Welk werkgeversaandeel geldt voor maaltijdcheques?", "2026-09-30T08:31:00"),
    ("T-DEMO-04", "c-kobalt", "deadline", "bediende",
     "Klant vraagt tot wanneer wijzigingen binnen mogen",
     "Wat is de deadline voor de maandelijkse verwerking?", "2026-09-30T09:02:00"),
    ("T-DEMO-05", "demo-acme", "overdracht", "bediende",
     "Klantdossier Demo Acme overdragen aan een nieuwe consultant",
     "Hoe draag ik een klantdossier over aan een nieuwe consultant?", "2026-09-30T10:05:00"),
    ("T-DEMO-06", "c-lindeboom", "loonbeslag", "bediende",
     "Nieuw loonbeslag voor een medewerker in de zaal",
     "Hoe bereken ik het beslagbare deel van een loonbeslag?", "2026-09-30T11:20:00"),
]
