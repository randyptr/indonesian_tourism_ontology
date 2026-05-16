"""Manually curated data for individuals and properties.

This module centralises all hand-curated ontology data that cannot be reliably
fetched from DBpedia. It replaces the former curate_individuals.py and
curate_properties.py split.

Contents
--------
Individuals (list[dict]):
    TRANSPORTATION       — AirTransport / LandTransport / WaterTransport nodes
    FESTIVALS            — Festival individuals for NTB / NTT (poor DBpedia coverage)
    FOOD                 — TypicalFood / CeremonialFood / StapleFood / Beverage
    TRADITIONAL_DANCES   — TraditionalDance individuals (3 provinces)
    TRADITIONAL_HOUSES   — TraditionalHouse individuals (3 provinces)
    PARKS_MANUAL         — Park individuals missing from DBpedia populate (Bali gaps)
    BEACHES_MANUAL       — Beach individuals not reliably returned by DBpedia (NTB/NTT focus)
    RELIGIOUS_CEREMONIES — ReligiousCeremony individuals (3 provinces)
    TEMPLES              — Temple individuals (3 provinces; Bali supplements DBpedia)
    RESTAURANTS          — Restaurant ⊑ Establishments
    STREET_VENDORS       — StreetVendor ⊑ Establishments
    TRADITIONAL_MARKETS  — TraditionalMarket ⊑ Establishments
    RESORTS              — Resort ⊑ Accommodation
    VILLAS               — Villa ⊑ Accommodation
    GUESTHOUSES          — Guesthouse ⊑ Accommodation
    HOSTELS              — Hostel ⊑ Accommodation

Properties (dict):
    RATINGS             — hasRating (xsd:decimal, scale 1-5) per class → {name: score}
    ENTRY_FEE           — hasEntryFee (xsd:boolean) for TouristAttractions
    PARK_ESTABLISHED_YEAR — establishedYear (xsd:integer) for Parks

Class hierarchy reminder
------------------------
Transportation
    AirTransport   — airports, airlines
    LandTransport  — bus terminals, road transport
    WaterTransport — ferry ports, harbours

TypicalFood (top-level class)
    CeremonialFood — food used in religious rituals
    StapleFood     — everyday staple foods
    Beverage       — traditional drinks

CulturalAttraction (subclass of TouristAttraction)
    TraditionalDance   — traditional regional dances
    TraditionalHouse   — traditional vernacular architecture / adat houses

Establishments (top-level class)
    Restaurant         — dining establishments
    StreetVendor       — warungs, street stalls, night markets
    TraditionalMarket  — local pasar (traditional markets)
    (TraditionalHouse also has Establishments as second parent)

Accommodation (top-level class)
    Hotel      — already populated by DBpedia
    Resort     — luxury/eco resorts
    Villa      — private villa rentals
    Guesthouse — budget guesthouses / homestays
    Hostel     — backpacker hostels
"""

# =============================================================================
# INDIVIDUALS
# =============================================================================

# ── Transportation
# Domain of hasTransportation: City -> Transportation
# Populated here because DBpedia lacks structured airport/port data for this region.

TRANSPORTATION: list[dict] = [

    # Bali
    {"name": "Ngurah_Rai_International_Airport", "type": "AirTransport",   "locatedIn": "Bali"},
    {"name": "Gilimanuk_Ferry_Port",             "type": "WaterTransport", "locatedIn": "Bali"},
    {"name": "Padang_Bai_Ferry_Port",            "type": "WaterTransport", "locatedIn": "Bali"},
    {"name": "Denpasar_Bus_Terminal",            "type": "LandTransport",  "locatedIn": "Bali"},

    # West Nusa Tenggara (NTB)
    {"name": "Lombok_International_Airport",     "type": "AirTransport",   "locatedIn": "West_Nusa_Tenggara"},
    {"name": "Lembar_Ferry_Port",                "type": "WaterTransport", "locatedIn": "West_Nusa_Tenggara"},
    {"name": "Mataram_Bus_Terminal",             "type": "LandTransport",  "locatedIn": "West_Nusa_Tenggara"},
    {"name": "Bima_Airport",                     "type": "AirTransport",   "locatedIn": "West_Nusa_Tenggara"},
    {"name": "Sape_Port",                        "type": "WaterTransport", "locatedIn": "West_Nusa_Tenggara"},

    # East Nusa Tenggara (NTT)
    {"name": "El_Tari_International_Airport",    "type": "AirTransport",   "locatedIn": "East_Nusa_Tenggara"},
    {"name": "Komodo_Airport",                   "type": "AirTransport",   "locatedIn": "East_Nusa_Tenggara"},
    {"name": "Tenau_Port",                       "type": "WaterTransport", "locatedIn": "East_Nusa_Tenggara"},
    {"name": "Kupang_Bus_Terminal",              "type": "LandTransport",  "locatedIn": "East_Nusa_Tenggara"},
    {"name": "Frans_Seda_Airport",               "type": "AirTransport",   "locatedIn": "East_Nusa_Tenggara"},
    {"name": "Frans_Sales_Lega_Airport",         "type": "AirTransport",   "locatedIn": "East_Nusa_Tenggara"},
    {"name": "H_Hasan_Aroeboesman_Airport",      "type": "AirTransport",   "locatedIn": "East_Nusa_Tenggara"},
]


# ── Festivals
# NTB and NTT festivals are added manually because:
#   - NTB:  DBpedia returns 0 results for Festival in West Nusa Tenggara
#   - NTT:  DBpedia incorrectly categorises a gubernatorial election as a
#           SocietalEvent under Tourist_attractions_in_East_Nusa_Tenggara

FESTIVALS: list[dict] = [

    # West Nusa Tenggara (NTB)
    {"name": "Bau_Nyale_Festival",          "locatedIn": "West_Nusa_Tenggara"},
    {"name": "Lombok_Sumbawa_Pearl_Festival","locatedIn": "West_Nusa_Tenggara"},
    {"name": "Perang_Topat",                "locatedIn": "West_Nusa_Tenggara"},
    {"name": "Tambora_Festival",            "locatedIn": "West_Nusa_Tenggara"},
    {"name": "Festival_Pesona_Moyo",        "locatedIn": "West_Nusa_Tenggara"},

    # East Nusa Tenggara (NTT)
    {"name": "Komodo_Festival",   "locatedIn": "East_Nusa_Tenggara"},
    {"name": "Sail_Komodo",       "locatedIn": "East_Nusa_Tenggara"},
    {"name": "Ende_Jazz_Festival", "locatedIn": "East_Nusa_Tenggara"},
    {"name": "Tenun_Festival_NTT", "locatedIn": "East_Nusa_Tenggara"},
    {"name": "Pasola_Festival",   "locatedIn": "East_Nusa_Tenggara"},
    {"name": "Reba_Festival",     "locatedIn": "East_Nusa_Tenggara"},
    {"name": "Penti_Festival",    "locatedIn": "East_Nusa_Tenggara"},

    # Bali
    {"name": "Festival_Seni_Bali_Jani", "locatedIn": "Bali"},
    {"name": "Bali_Kite_Festival",      "locatedIn": "Bali"},
]


# ── Traditional Dances
# TraditionalDance ⊑ CulturalAttraction ⊑ TouristAttraction
# DBpedia returns no structured dance data for this region; all entries are manual.

TRADITIONAL_DANCES: list[dict] = [

    # Bali
    {"name": "Kecak",         "locatedIn": "Bali"},
    {"name": "Legong",        "locatedIn": "Bali"},
    {"name": "Barong_Dance",  "locatedIn": "Bali"},
    {"name": "Pendet",        "locatedIn": "Bali"},
    {"name": "Baris_Dance",   "locatedIn": "Bali"},
    {"name": "Topeng_Dance",  "locatedIn": "Bali"},
    {"name": "Tari_Rejang",   "locatedIn": "Bali"},
    {"name": "Tari_Gambuh",   "locatedIn": "Bali"},

    # West Nusa Tenggara (NTB)
    {"name": "Tari_Oncer",         "locatedIn": "West_Nusa_Tenggara"},
    {"name": "Rudat",              "locatedIn": "West_Nusa_Tenggara"},
    {"name": "Kayak_Sando",        "locatedIn": "West_Nusa_Tenggara"},
    {"name": "Tari_Gendang_Beleq", "locatedIn": "West_Nusa_Tenggara"},
    {"name": "Tari_Mpaa_Lenggogo", "locatedIn": "West_Nusa_Tenggara"},

    # East Nusa Tenggara (NTT)
    {"name": "Hegong",        "locatedIn": "East_Nusa_Tenggara"},
    {"name": "Ja_i",          "locatedIn": "East_Nusa_Tenggara"},
    {"name": "Likurai",       "locatedIn": "East_Nusa_Tenggara"},
    {"name": "Tari_Caci",     "locatedIn": "East_Nusa_Tenggara"},
    {"name": "Tari_Lego_Lego","locatedIn": "East_Nusa_Tenggara"},
    {"name": "Tari_Bonet",    "locatedIn": "East_Nusa_Tenggara"},
]


# ── Traditional Houses
# TraditionalHouse ⊑ CulturalAttraction ⊑ TouristAttraction
#                  ⊑ Establishments  (can have servesFood edge)
# DBpedia does not reliably classify Indonesian vernacular architecture; all manual.

TRADITIONAL_HOUSES: list[dict] = [

    # Bali
    {"name": "Bale_Banjar", "locatedIn": "Bali"},
    {"name": "Jineng",      "locatedIn": "Bali"},
    {"name": "Bale_Daja",   "locatedIn": "Bali"},

    # West Nusa Tenggara (NTB)
    {"name": "Bale_Lumbung",     "locatedIn": "West_Nusa_Tenggara"},
    {"name": "Rumah_Adat_Bayan", "locatedIn": "West_Nusa_Tenggara"},
    {"name": "Dalam_Loka",       "locatedIn": "West_Nusa_Tenggara"},
    {"name": "Bale_Jajar",       "locatedIn": "West_Nusa_Tenggara"},
    {"name": "Bencingah",        "locatedIn": "West_Nusa_Tenggara"},

    # East Nusa Tenggara (NTT)
    {"name": "Mbaru_Niang",           "locatedIn": "East_Nusa_Tenggara"},
    {"name": "Sa_o",                  "locatedIn": "East_Nusa_Tenggara"},
    {"name": "Rumah_Adat_Sumba",      "locatedIn": "East_Nusa_Tenggara"},
    {"name": "Uma_Lulik",             "locatedIn": "East_Nusa_Tenggara"},
    {"name": "Sao_Ata_Mosa_Lakitana", "locatedIn": "East_Nusa_Tenggara"},
]


# ── Parks (Manual supplement)
# Park ⊑ TouristAttraction
# These Bali parks are referenced in RATINGS, ENTRY_FEE, and PARK_ESTABLISHED_YEAR
# but are not returned by DBpedia's populate step for this region.

PARKS_MANUAL: list[dict] = [

    # Bali
    {"name": "Bali_Bird_Park",                "locatedIn": "Bali"},
    {"name": "Sacred_Monkey_Forest_Sanctuary", "locatedIn": "Bali"},
    {"name": "Bali_Botanic_Garden",           "locatedIn": "Bali"},
]


# ── Beaches (Manual supplement)
# Beach ⊑ TouristAttraction
# DBpedia covers Bali beaches well; NTB and NTT coverage is sparse or absent.
# Bali entries here fill gaps not returned by the DBpedia populate step.

BEACHES_MANUAL: list[dict] = [

    # Bali
    {"name": "Balangan_Beach",   "locatedIn": "Bali"},
    {"name": "Amed_Beach",       "locatedIn": "Bali"},
    {"name": "Pemuteran_Beach",  "locatedIn": "Bali"},
    {"name": "Bias_Tugel_Beach", "locatedIn": "Bali"},

    # West Nusa Tenggara (NTB)
    {"name": "Kuta_Lombok",      "locatedIn": "West_Nusa_Tenggara"},
    {"name": "Selong_Belanak",   "locatedIn": "West_Nusa_Tenggara"},
    {"name": "Tanjung_Aan",      "locatedIn": "West_Nusa_Tenggara"},
    {"name": "Senggigi_Beach",   "locatedIn": "West_Nusa_Tenggara"},
    {"name": "Lakey_Beach",      "locatedIn": "West_Nusa_Tenggara"},
    {"name": "Maluk_Beach",      "locatedIn": "West_Nusa_Tenggara"},

    # East Nusa Tenggara (NTT)
    {"name": "Nihiwatu_Beach",  "locatedIn": "East_Nusa_Tenggara"},
    {"name": "Pink_Beach",      "locatedIn": "East_Nusa_Tenggara"},
    {"name": "Koka_Beach",      "locatedIn": "East_Nusa_Tenggara"},
    {"name": "Lasiana_Beach",   "locatedIn": "East_Nusa_Tenggara"},
    {"name": "Kolbano_Beach",   "locatedIn": "East_Nusa_Tenggara"},
]


# ── Religious Ceremonies
# ReligiousCeremony ⊑ TouristAttraction
# DBpedia returns near-zero structured results for all 3 provinces; all manual.

RELIGIOUS_CEREMONIES: list[dict] = [

    # Bali
    {"name": "Nyepi",    "locatedIn": "Bali"},
    {"name": "Galungan", "locatedIn": "Bali"},
    {"name": "Kuningan", "locatedIn": "Bali"},
    {"name": "Melasti",  "locatedIn": "Bali"},
    {"name": "Odalan",   "locatedIn": "Bali"},
    {"name": "Ngaben",   "locatedIn": "Bali"},

    # West Nusa Tenggara (NTB)
    {"name": "Lebaran_Topat",      "locatedIn": "West_Nusa_Tenggara"},
    {"name": "Maulid_Adat_Bayan",  "locatedIn": "West_Nusa_Tenggara"},

    # East Nusa Tenggara (NTT)
    {"name": "Semana_Santa_Larantuka", "locatedIn": "East_Nusa_Tenggara"},
    {"name": "Wula_Podhu",             "locatedIn": "East_Nusa_Tenggara"},
    {"name": "Pati_Ka",                "locatedIn": "East_Nusa_Tenggara"},
    {"name": "Etu",                    "locatedIn": "East_Nusa_Tenggara"},
]


# ── Temples
# Temple ⊑ TouristAttraction
# DBpedia covers some Bali temples; NTB/NTT coverage is sparse.
# Bali entries here supplement DBpedia output; duplicates are harmless (rdflib is idempotent).

TEMPLES: list[dict] = [

    # Bali
    {"name": "Tanah_Lot",             "locatedIn": "Bali"},
    {"name": "Uluwatu_Temple",        "locatedIn": "Bali"},
    {"name": "Besakih",               "locatedIn": "Bali"},
    {"name": "Pura_Tirta_Empul",      "locatedIn": "Bali"},
    {"name": "Goa_Gajah",             "locatedIn": "Bali"},
    {"name": "Pura_Ulun_Danu_Bratan", "locatedIn": "Bali"},
    {"name": "Pura_Luhur_Batukaru",   "locatedIn": "Bali"},
    {"name": "Pura_Taman_Ayun",       "locatedIn": "Bali"},
    {"name": "Pura_Goa_Lawah",        "locatedIn": "Bali"},

    # West Nusa Tenggara (NTB)
    {"name": "Pura_Meru",    "locatedIn": "West_Nusa_Tenggara"},
    {"name": "Pura_Lingsar", "locatedIn": "West_Nusa_Tenggara"},

    # East Nusa Tenggara (NTT)
    {"name": "Pura_Segara_Rupek", "locatedIn": "East_Nusa_Tenggara"},
]


# ── Restaurants ───────
# Restaurant ⊑ Establishments
# DBpedia has no restaurant data for this region; all entries are manual.

RESTAURANTS: list[dict] = [

    # Bali
    {"name": "Locavore",                  "locatedIn": "Bali"},
    {"name": "Merah_Putih_Restaurant",    "locatedIn": "Bali"},
    {"name": "Mozaic_Restaurant",         "locatedIn": "Bali"},
    {"name": "Sardine_Restaurant",        "locatedIn": "Bali"},
    {"name": "Wahaha_Restaurant",         "locatedIn": "Bali"},
    {"name": "Naughty_Nuris_Warung",      "locatedIn": "Bali"},
    {"name": "Hujan_Locale",              "locatedIn": "Bali"},
    {"name": "Cuca_Restaurant",           "locatedIn": "Bali"},
    {"name": "Bambu_Restaurant",          "locatedIn": "Bali"},

    # West Nusa Tenggara (NTB)
    {"name": "Ashtari_Restaurant",           "locatedIn": "West_Nusa_Tenggara"},
    {"name": "Bale_Lombok_Restaurant",       "locatedIn": "West_Nusa_Tenggara"},
    {"name": "Square_Restaurant",            "locatedIn": "West_Nusa_Tenggara"},
    {"name": "Tanjung_Restaurant_Senggigi",  "locatedIn": "West_Nusa_Tenggara"},
    {"name": "Bale_Sari_Mataram",            "locatedIn": "West_Nusa_Tenggara"},
    {"name": "Mandalika_Restaurant_Lombok",  "locatedIn": "West_Nusa_Tenggara"},

    # East Nusa Tenggara (NTT)
    {"name": "Kampung_Ujung_Restaurant",     "locatedIn": "East_Nusa_Tenggara"},
    {"name": "Tree_Top_Restaurant",          "locatedIn": "East_Nusa_Tenggara"},
    {"name": "Bajo_Seafood_House",           "locatedIn": "East_Nusa_Tenggara"},
    {"name": "Rumah_Makan_Sederhana_Kupang", "locatedIn": "East_Nusa_Tenggara"},
    {"name": "Sari_Restaurant_Ende",         "locatedIn": "East_Nusa_Tenggara"},
]


# ── Street Vendors ────
# StreetVendor ⊑ Establishments
# Includes warungs (small local eateries) and night markets.

STREET_VENDORS: list[dict] = [
    # Bali
    {"name": "Warung_Ibu_Oka",               "locatedIn": "Bali"},
    {"name": "Warung_Nasi_Ayam_Bu_Mus",      "locatedIn": "Bali"},
    {"name": "Kreneng_Night_Market",         "locatedIn": "Bali"},
    {"name": "Warung_Babi_Guling_Chandra",   "locatedIn": "Bali"},
    {"name": "Sanur_Night_Market",           "locatedIn": "Bali"},

    # West Nusa Tenggara (NTB)
    {"name": "Warung_Taliwang_Irama",   "locatedIn": "West_Nusa_Tenggara"},
    {"name": "Pasar_Malam_Sindu",       "locatedIn": "West_Nusa_Tenggara"},
    {"name": "Warung_Pelecing_Bu_Nini", "locatedIn": "West_Nusa_Tenggara"},
    {"name": "Pasar_Malam_Senggigi",    "locatedIn": "West_Nusa_Tenggara"},

    # East Nusa Tenggara (NTT)
    {"name": "Warung_Seafood_Kupang",   "locatedIn": "East_Nusa_Tenggara"},
    {"name": "Pasar_Malam_Labuan_Bajo", "locatedIn": "East_Nusa_Tenggara"},
    {"name": "Warung_Se_i_Babi_Kupang", "locatedIn": "East_Nusa_Tenggara"},
    {"name": "Pasar_Malam_Ende",        "locatedIn": "East_Nusa_Tenggara"},
]


# ── Traditional Markets ───────────────────────────────────────────────────────
# TraditionalMarket ⊑ Establishments
# Local pasar (traditional open-air markets).

TRADITIONAL_MARKETS: list[dict] = [
    # Bali
    {"name": "Pasar_Badung",   "locatedIn": "Bali"},
    {"name": "Pasar_Ubud",     "locatedIn": "Bali"},
    {"name": "Pasar_Sukawati", "locatedIn": "Bali"},
    {"name": "Pasar_Kumbasari","locatedIn": "Bali"},
    {"name": "Pasar_Sanur",    "locatedIn": "Bali"},

    # West Nusa Tenggara (NTB)
    {"name": "Pasar_Cakranegara", "locatedIn": "West_Nusa_Tenggara"},
    {"name": "Pasar_Bertais",     "locatedIn": "West_Nusa_Tenggara"},
    {"name": "Pasar_Ampenan",     "locatedIn": "West_Nusa_Tenggara"},
    {"name": "Pasar_Praya",       "locatedIn": "West_Nusa_Tenggara"},

    # East Nusa Tenggara (NTT)
    {"name": "Pasar_Inpres_Labuan_Bajo", "locatedIn": "East_Nusa_Tenggara"},
    {"name": "Pasar_Oebobo",             "locatedIn": "East_Nusa_Tenggara"},
    {"name": "Pasar_Kasih_Naikoten",     "locatedIn": "East_Nusa_Tenggara"},
    {"name": "Pasar_Ende",               "locatedIn": "East_Nusa_Tenggara"},
]


# ── Resorts ───────────
# Resort ⊑ Accommodation
# City -> hasAccommodation -> Resort

RESORTS: list[dict] = [
    # Bali
    {"name": "Four_Seasons_Resort_Sayan", "locatedIn": "Bali"},
    {"name": "Alila_Villas_Uluwatu",      "locatedIn": "Bali"},
    {"name": "COMO_Shambhala_Estate",     "locatedIn": "Bali"},
    {"name": "Amanusa",                   "locatedIn": "Bali"},
    {"name": "Bulgari_Resort_Bali",       "locatedIn": "Bali"},
    {"name": "Capella_Ubud",              "locatedIn": "Bali"},
    {"name": "Hanging_Gardens_Resort",    "locatedIn": "Bali"},

    # West Nusa Tenggara (NTB)
    {"name": "Katamaran_Resort_Lombok", "locatedIn": "West_Nusa_Tenggara"},
    {"name": "Qunci_Villas_Hotel",      "locatedIn": "West_Nusa_Tenggara"},
    {"name": "Jeeva_Klui_Resort",       "locatedIn": "West_Nusa_Tenggara"},
    {"name": "Oberoi_Lombok",           "locatedIn": "West_Nusa_Tenggara"},

    # East Nusa Tenggara (NTT)
    {"name": "Plataran_Komodo_Resort", "locatedIn": "East_Nusa_Tenggara"},
    {"name": "Sudamala_Resort_Komodo", "locatedIn": "East_Nusa_Tenggara"},
    {"name": "Ayana_Komodo",           "locatedIn": "East_Nusa_Tenggara"},
    {"name": "Meruorah_Komodo_Resort", "locatedIn": "East_Nusa_Tenggara"},
]


# ── Villas ────────────
# Villa ⊑ Accommodation

VILLAS: list[dict] = [
    # Bali
    {"name": "Alila_Villas_Soori",   "locatedIn": "Bali"},
    {"name": "Karma_Kandara",        "locatedIn": "Bali"},
    {"name": "The_Royal_Purnama",    "locatedIn": "Bali"},
    {"name": "Puri_Wulandari_Villa", "locatedIn": "Bali"},
    {"name": "Shanti_Villa",         "locatedIn": "Bali"},
    {"name": "Villa_Mathis",         "locatedIn": "Bali"},

    # West Nusa Tenggara (NTB)
    {"name": "Selong_Selo_Villas", "locatedIn": "West_Nusa_Tenggara"},
    {"name": "Jeeva_Beloam",       "locatedIn": "West_Nusa_Tenggara"},
    {"name": "The_Lombok_Lodge",   "locatedIn": "West_Nusa_Tenggara"},

    # East Nusa Tenggara (NTT)
    {"name": "Sudamala_Surya_Djiwa", "locatedIn": "East_Nusa_Tenggara"},
    {"name": "Golo_Hilltop_Escape",  "locatedIn": "East_Nusa_Tenggara"},
]


# ── Guesthouses 
# Guesthouse ⊑ Accommodation
# Includes homestays and budget boutique lodging.

GUESTHOUSES: list[dict] = [
    # Bali
    {"name": "Pondok_Pitaya",            "locatedIn": "Bali"},
    {"name": "Sanur_Sunrise_Guesthouse", "locatedIn": "Bali"},
    {"name": "Pondok_Indah_Ubud",        "locatedIn": "Bali"},
    {"name": "Kuta_Beach_Guesthouse",    "locatedIn": "Bali"},

    # West Nusa Tenggara (NTB)
    {"name": "Kuta_Indah_Guesthouse",    "locatedIn": "West_Nusa_Tenggara"},
    {"name": "Senggigi_Beach_Guesthouse","locatedIn": "West_Nusa_Tenggara"},
    {"name": "Medana_Homestay",          "locatedIn": "West_Nusa_Tenggara"},
    {"name": "Gili_Trawangan_Guesthouse","locatedIn": "West_Nusa_Tenggara"},

    # East Nusa Tenggara (NTT)
    {"name": "Gardena_Guesthouse",     "locatedIn": "East_Nusa_Tenggara"},
    {"name": "Wae_Rebo_Homestay",      "locatedIn": "East_Nusa_Tenggara"},
    {"name": "Bajo_Divers_Guesthouse", "locatedIn": "East_Nusa_Tenggara"},
    {"name": "Soe_Guesthouse",         "locatedIn": "East_Nusa_Tenggara"},
]


# ── Hostels
# Hostel ⊑ Accommodation

HOSTELS: list[dict] = [

    # Bali
    {"name": "Puri_Garden_Hostel",     "locatedIn": "Bali"},
    {"name": "Tribal_Hostel",          "locatedIn": "Bali"},
    {"name": "Canggu_Social_Hostel",   "locatedIn": "Bali"},
    {"name": "Kuta_Backpackers_Hostel","locatedIn": "Bali"},

    # West Nusa Tenggara (NTB)
    {"name": "Shady_Shack_Hostel",      "locatedIn": "West_Nusa_Tenggara"},
    {"name": "Kuta_Lombok_Surf_Hostel", "locatedIn": "West_Nusa_Tenggara"},

    # East Nusa Tenggara (NTT)
    {"name": "Bajo_Komodo_Hostel",      "locatedIn": "East_Nusa_Tenggara"},
    {"name": "Flores_Backpacker_Hostel","locatedIn": "East_Nusa_Tenggara"},
    {"name": "Kupang_Youth_Hostel",     "locatedIn": "East_Nusa_Tenggara"},
]


# =============================================================================
# PROPERTIES
# =============================================================================

# hasRating (xsd:decimal, scale 1-5)
RATINGS = {
    "Museum": {
        "Bali_Museum":               4.3,
        "Neka_Art_Museum":           4.5,
        "Puri_Lukisan_Museum":       4.4,
        "Blanco_Renaissance_Museum": 4.3,
        "Museum_Rudana":             4.6,
        "Museum_Pasifika":           4.1,
        "Le_Mayeur_Museum":          4.1,
        "Semarajaya_Museum":         4.6,
        "Gedong_Arca_Museum_Bedulu": 3.7,
        "Gedong_Kirtya":             4.5,
        "Bajra_Sandhi_Monument":     4.6,
    },
    "Hotel": {
        "Amankila":                          4.7,
        "Tandjung_Sari":                     4.7,
        "Tjampuhan_Hotel":                   4.6,
        "InterContinental_Hotel_Bali":       4.7,
        "Belmond_Jimbaran_Puri":             4.7,
    },
    "Volcano": {
        "Mount_Agung":                       4.5,
        "Mount_Batur":                       4.3,
        "Mount_Tambora":                     4.8,
    },
    "Park": {
        "Komodo_National_Park":              4.6,
        "Kelimutu_National_Park":            4.6,
        "Mount_Rinjani_National_Park":       4.5,
        "West_Bali_National_Park":           4.3,
        "Manupeu_Tanah_Daru_National_Park":  4.7,
        "Laiwangi_Wanggameti_National_Park": 4.9,
    },
    "Beach": {
        "Pandawa_Beach":       4.1,
        "Legian":              4.5,
        "Padang_Padang_Beach": 3.8,
        "Dreamland_Beach":     3.8,
        "Lovina_Beach":        3.5,
        "Tanjung_Ringgit":     4.5,
        "Nembrala":            4.6,
        "Cepi_Watu_Beach":     4.1,
    },
}

# hasEntryFee (xsd:boolean) - True = charges an entry fee
# Domain: TouristAttraction
ENTRY_FEE = {
    "Bali_Museum":                    True,
    "Neka_Art_Museum":                True,
    "Puri_Lukisan_Museum":            True,
    "Blanco_Renaissance_Museum":      True,
    "Museum_Rudana":                  True,
    "Museum_Pasifika":                True,
    "Le_Mayeur_Museum":               True,
    "Semarajaya_Museum":              True,
    "Gedong_Arca_Museum_Bedulu":      True,
    "Gedong_Kirtya":                  False,
    "Bajra_Sandhi_Monument":          False,
    "Komodo_National_Park":           True,
    "Kelimutu_National_Park":         True,
    "Mount_Rinjani_National_Park":    True,
    "West_Bali_National_Park":        True,
    "Bali_Bird_Park":                 True,
    "Sacred_Monkey_Forest_Sanctuary": True,
    "Bali_Botanic_Garden":            True,
}

# establishedYear (xsd:integer) for Parks
PARK_ESTABLISHED_YEAR = {
    "Komodo_National_Park":              1980,
    "Kelimutu_National_Park":            1992,
    "Mount_Rinjani_National_Park":       1997,
    "West_Bali_National_Park":           1941,
    "Manupeu_Tanah_Daru_National_Park":  1998,
    "Laiwangi_Wanggameti_National_Park": 1998,
    "Bali_Bird_Park":                    1995,
    "Bali_Botanic_Garden":               1959,
}
