"""Shared constants, namespaces, file paths, and domain mappings.

This module holds *no* logic — only data. All other modules import from here so
that paths and mappings live in exactly one place.
"""

from pathlib import Path
from rdflib import Namespace

# ── File paths ────────────────────────────────────────────────────────────────
PROJECT_DIR  = Path(__file__).resolve().parent
ONTOLOGY_DIR = PROJECT_DIR / "ontology"
SCHEMA_FILE  = ONTOLOGY_DIR / "schema.owl"
DATA_FILE    = ONTOLOGY_DIR / "data.owl"
TRAVEL_FILE  = ONTOLOGY_DIR / "travel.owl"
CATALOG_FILE = ONTOLOGY_DIR / "catalog-v001.xml"

# ── Namespaces ────────────────────────────────────────────────────────────────
ONT_IRI = "http://www.semanticweb.org/emmaa/ontologies/2026/3/untitled-ontology-9#"
DATA_IRI = "http://www.semanticweb.org/emmaa/ontologies/2026/3/tourism-data"
TRAVEL_REMOTE_IRI = "http://www.owl-ontologies.com/travel.owl"

ONT = Namespace(ONT_IRI)

# ── DBpedia endpoint ──────────────────────────────────────────────────────────
DBPEDIA_ENDPOINT = "https://dbpedia.org/sparql"
DBPEDIA_TIMEOUT_S = 30
DBPEDIA_THROTTLE_S = 1.0   # polite delay between queries

# ── Province / Island short names ─────────────────────────────────────────────
PROVINCES = {
    "Bali": "Bali",
    "NTB":  "West_Nusa_Tenggara",
    "NTT":  "East_Nusa_Tenggara",
}

# Capital city per province (used for hasTouristAttraction edges)
CAPITAL_OF_PROVINCE = {
    "Bali":               "Denpasar",
    "West_Nusa_Tenggara": "Mataram",
    "East_Nusa_Tenggara": "Kupang",
}

# ── Domain mappings (data-only — no logic) ────────────────────────────────────
# Used in enrichment to inject locatedIn / locatedInIsland triples.

ISLAND_TO_PROVINCE = {
    "Bali_Island":          "Bali",
    "Nusa_Penida":          "Bali",
    "Nusa_Lembongan":       "Bali",
    "Nusa_Ceningan":        "Bali",
    "Serangan_Island":      "Bali",
    "Menjangan_Island":     "Bali",
    "Lombok":               "West_Nusa_Tenggara",
    "Sumbawa":              "West_Nusa_Tenggara",
    "Moyo_Island":          "West_Nusa_Tenggara",
    "Satonda_Island":       "West_Nusa_Tenggara",
    "Bungin_Island":        "West_Nusa_Tenggara",
    "Flores":               "East_Nusa_Tenggara",
    "Sumba":                "East_Nusa_Tenggara",
    "Besar_Island__Flores": "East_Nusa_Tenggara",
}

# Bali regencies + Denpasar are all on Bali_Island.
# NTB regencies split between Lombok and Sumbawa.
# NTT regencies span many islands; only the obvious ones are listed.
CITY_TO_ISLAND = {
    # Bali
    **{c: "Bali_Island" for c in [
        "Badung_Regency", "Bangli_Regency", "Buleleng_Regency", "Gianyar_Regency",
        "Jembrana_Regency", "Karangasem_Regency", "Klungkung_Regency",
        "Tabanan_Regency", "Denpasar",
    ]},
    # NTB - Lombok
    **{c: "Lombok" for c in [
        "Central_Lombok_Regency", "East_Lombok_Regency",
        "North_Lombok_Regency",   "West_Lombok_Regency",
    ]},
    # NTB - Sumbawa
    **{c: "Sumbawa" for c in [
        "Bima_Regency", "Dompu_Regency",
        "Sumbawa_Regency", "West_Sumbawa_Regency",
    ]},
    # NTT - Flores
    **{c: "Flores" for c in [
        "East_Manggarai_Regency", "Manggarai_Regency", "West_Manggarai_Regency",
        "Ngada_Regency", "Nagekeo_Regency", "Ende_Regency",
        "Sikka_Regency", "East_Flores_Regency",
    ]},
    # NTT - Sumba
    **{c: "Sumba" for c in [
        "Central_Sumba_Regency", "East_Sumba_Regency",
        "West_Sumba_Regency", "Southwest_Sumba_Regency",
    ]},
}

BEACH_TO_ISLAND = {
    "Pandawa_Beach":      "Bali_Island",
    "Legian":             "Bali_Island",
    "Padang_Padang_Beach":"Bali_Island",
    "Dreamland_Beach":    "Bali_Island",
    "Lovina_Beach":       "Bali_Island",
    "Sanur__Bali":        "Bali_Island",
    "Nusa_Dua":           "Bali_Island",
    "Jimbaran":           "Bali_Island",
    "Tanjung_Ringgit":    "Lombok",
    "Cepi_Watu_Beach":    "Flores",
    # Nembrala is on Rote Island (NTT) — not in our Island set; skip.
}

# Beach → Province (every beach should have a province link for density)
BEACH_TO_PROVINCE = {
    "Pandawa_Beach":       "Bali",
    "Legian":              "Bali",
    "Padang_Padang_Beach": "Bali",
    "Dreamland_Beach":     "Bali",
    "Lovina_Beach":        "Bali",
    "Sanur__Bali":         "Bali",
    "Nusa_Dua":            "Bali",
    "Jimbaran":            "Bali",
    "Tanjung_Ringgit":     "West_Nusa_Tenggara",
    "Nembrala":            "East_Nusa_Tenggara",
    "Cepi_Watu_Beach":     "East_Nusa_Tenggara",
}

# (Province, Island) per Park
PARK_LOCATION = {
    "Komodo_National_Park":              ("East_Nusa_Tenggara", "Flores"),
    "Kelimutu_National_Park":            ("East_Nusa_Tenggara", "Flores"),
    "Manupeu_Tanah_Daru_National_Park":  ("East_Nusa_Tenggara", "Sumba"),
    "Laiwangi_Wanggameti_National_Park": ("East_Nusa_Tenggara", "Sumba"),
    "Mount_Rinjani_National_Park":       ("West_Nusa_Tenggara", "Lombok"),
    "West_Bali_National_Park":           ("Bali",               "Bali_Island"),
    "Bali_Botanic_Garden":               ("Bali",               "Bali_Island"),
}

# (Province, Island) per Volcano
VOLCANO_LOCATION = {
    "Mount_Agung":      ("Bali",               "Bali_Island"),
    "Mount_Batur":      ("Bali",               "Bali_Island"),
    "Bratan__volcano_": ("Bali",               "Bali_Island"),
    "Mount_Tambora":    ("West_Nusa_Tenggara", "Sumbawa"),
}

# Activity vocabulary — individuals of class :Activities (note plural class name)
ACTIVITIES = ["Surfing", "Snorkeling", "Diving", "Hiking", "Sightseeing", "Cultural_Tour"]

# (TouristAttraction class, list of attractions, or None to mean "all of class")
ACTIVITY_LINKS = {
    "Surfing":       ("Beach",   ["Padang_Padang_Beach", "Dreamland_Beach", "Legian",
                                  "Tanjung_Ringgit"]),
    "Snorkeling":    ("Beach",   ["Pandawa_Beach", "Lovina_Beach", "Nembrala",
                                  "Nusa_Dua", "Sanur__Bali"]),
    "Diving":        ("Beach",   ["Lovina_Beach", "Nembrala", "Nusa_Dua"]),
    "Hiking":        ("Volcano", ["Mount_Agung", "Mount_Batur", "Mount_Tambora"]),
    "Sightseeing":   ("Park",    ["Komodo_National_Park", "Kelimutu_National_Park",
                                  "West_Bali_National_Park", "Mount_Rinjani_National_Park",
                                  "Bali_Botanic_Garden",
                                  "Manupeu_Tanah_Daru_National_Park",
                                  "Laiwangi_Wanggameti_National_Park"]),
    "Cultural_Tour": ("Museum",  None),   # None → all museums
}

# Extra activity links for classes not covered by ACTIVITY_LINKS.
# Temples → Cultural_Tour + Sightseeing, Festivals/Ceremonies → Cultural_Tour.
EXTRA_ACTIVITY_LINKS: dict[str, list[str]] = {
    "Temple":            ["Cultural_Tour", "Sightseeing"],
    "Festival":          ["Cultural_Tour", "Sightseeing"],
    "ReligiousCeremony": ["Cultural_Tour"],
}

# Classes that are subclasses of TouristAttraction (used for hub edges).
# Hotel is excluded: Hotel ⊑ Accommodation, which is disjoint with TouristAttraction.
TOURIST_ATTRACTION_CLASSES = [
    "Beach", "Park", "Volcano", "Museum", "Temple",
    "Festival", "ReligiousCeremony",
]

# ── Blank data.owl skeleton (rewritten on each run) ───────────────────────────
BLANK_DATA_OWL = f"""\
<?xml version="1.0"?>
<rdf:RDF xmlns="{DATA_IRI}/"
     xml:base="{DATA_IRI}/"
     xmlns:owl="http://www.w3.org/2002/07/owl#"
     xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
     xmlns:xml="http://www.w3.org/XML/1998/namespace"
     xmlns:xsd="http://www.w3.org/2001/XMLSchema#"
     xmlns:rdfs="http://www.w3.org/2000/01/rdf-schema#">
    <owl:Ontology rdf:about="{DATA_IRI}">
        <owl:imports rdf:resource="{ONT_IRI[:-1]}"/>
    </owl:Ontology>
</rdf:RDF>
"""
