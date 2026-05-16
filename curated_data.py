"""Manually curated data for individuals and properties.

This module centralises all hand-curated ontology data that cannot be reliably
fetched from DBpedia. It replaces the former curate_individuals.py and
curate_properties.py split.

Contents
--------
Individuals (list[dict]):
    TRANSPORTATION      — AirTransport / LandTransport / WaterTransport nodes
    FESTIVALS           — Festival individuals for NTB / NTT (poor DBpedia coverage)
    FOOD                — TypicalFood / CeremonialFood / StapleFood / Beverage
    TRADITIONAL_DANCES  — TraditionalDance individuals (3 provinces)
    TRADITIONAL_HOUSES  — TraditionalHouse individuals (3 provinces)
    RESTAURANTS         — Restaurant ⊑ Establishments
    STREET_VENDORS      — StreetVendor ⊑ Establishments
    TRADITIONAL_MARKETS — TraditionalMarket ⊑ Establishments
    RESORTS             — Resort ⊑ Accommodation
    VILLAS              — Villa ⊑ Accommodation
    GUESTHOUSES         — Guesthouse ⊑ Accommodation
    HOSTELS             — Hostel ⊑ Accommodation

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

    # East Nusa Tenggara (NTT)
    {"name": "El_Tari_International_Airport",    "type": "AirTransport",   "locatedIn": "East_Nusa_Tenggara"},
    {"name": "Komodo_Airport",                   "type": "AirTransport",   "locatedIn": "East_Nusa_Tenggara"},
    {"name": "Tenau_Port",                       "type": "WaterTransport", "locatedIn": "East_Nusa_Tenggara"},
    {"name": "Kupang_Bus_Terminal",              "type": "LandTransport",  "locatedIn": "East_Nusa_Tenggara"},
]


# ── Festivals
# NTB and NTT festivals are added manually because:
#   - NTB:  DBpedia returns 0 results for Festival in West Nusa Tenggara
#   - NTT:  DBpedia incorrectly categorises a gubernatorial election as a
#           SocietalEvent under Tourist_attractions_in_East_Nusa_Tenggara

FESTIVALS: list[dict] = [

    # West Nusa Tenggara (NTB)
    {"name": "Bau_Nyale_Festival",          "locatedIn": "West_Nusa_Tenggara"},  # Sasak sea worm harvest ceremony
    {"name": "Lombok_Sumbawa_Pearl_Festival","locatedIn": "West_Nusa_Tenggara"},  # annual pearl & culture expo

    # East Nusa Tenggara (NTT)
    {"name": "Komodo_Festival",  "locatedIn": "East_Nusa_Tenggara"},  # annual tourism & culture festival, Labuan Bajo
    {"name": "Sail_Komodo",      "locatedIn": "East_Nusa_Tenggara"},  # international yacht rally & marine festival
    {"name": "Ende_Jazz_Festival","locatedIn": "East_Nusa_Tenggara"},  # annual jazz music festival in Ende
    {"name": "Tenun_Festival_NTT","locatedIn": "East_Nusa_Tenggara"},  # traditional ikat weaving showcase
]


# ── Food 
# Domain of hasFood:        City -> Food
# Domain of originatesFrom: Food -> Province

FOOD: list[dict] = [
    # Bali — TypicalFood (savory dishes)
    {"name": "Babi_Guling",  "type": "TypicalFood",    "locatedIn": "Bali", "originatesFrom": "Bali"},
    {"name": "Bebek_Betutu", "type": "TypicalFood",    "locatedIn": "Bali", "originatesFrom": "Bali"},
    {"name": "Lawar",        "type": "TypicalFood",    "locatedIn": "Bali", "originatesFrom": "Bali"},
    {"name": "Sate_Lilit",   "type": "TypicalFood",    "locatedIn": "Bali", "originatesFrom": "Bali"},
    {"name": "Nasi_Campur",  "type": "StapleFood",     "locatedIn": "Bali", "originatesFrom": "Bali"},

    # Bali — CeremonialFood (used in Hindu religious rituals)
    {"name": "Jaje_Bali",    "type": "CeremonialFood", "locatedIn": "Bali", "originatesFrom": "Bali"},
    {"name": "Tumpeng",      "type": "CeremonialFood", "locatedIn": "Bali", "originatesFrom": "Bali"},

    # Bali — Beverage
    {"name": "Tuak",         "type": "Beverage",       "locatedIn": "Bali", "originatesFrom": "Bali"},

    # West Nusa Tenggara (NTB)
    {"name": "Ayam_Taliwang",    "type": "TypicalFood", "locatedIn": "West_Nusa_Tenggara", "originatesFrom": "West_Nusa_Tenggara"},
    {"name": "Plecing_Kangkung", "type": "TypicalFood", "locatedIn": "West_Nusa_Tenggara", "originatesFrom": "West_Nusa_Tenggara"},
    {"name": "Nasi_Balap_Puyung","type": "StapleFood",  "locatedIn": "West_Nusa_Tenggara", "originatesFrom": "West_Nusa_Tenggara"},
    {"name": "Bebalung",         "type": "TypicalFood", "locatedIn": "West_Nusa_Tenggara", "originatesFrom": "West_Nusa_Tenggara"},

    # East Nusa Tenggara (NTT)
    {"name": "Catemak_Jagung", "type": "StapleFood",  "locatedIn": "East_Nusa_Tenggara", "originatesFrom": "East_Nusa_Tenggara"},
    {"name": "Se_i",           "type": "TypicalFood", "locatedIn": "East_Nusa_Tenggara", "originatesFrom": "East_Nusa_Tenggara"},
    {"name": "Jawada",         "type": "TypicalFood", "locatedIn": "East_Nusa_Tenggara", "originatesFrom": "East_Nusa_Tenggara"},
    {"name": "Kolo",           "type": "StapleFood",  "locatedIn": "East_Nusa_Tenggara", "originatesFrom": "East_Nusa_Tenggara"},
]


# ── Traditional Dances 
# TraditionalDance ⊑ CulturalAttraction ⊑ TouristAttraction
# DBpedia returns no structured dance data for this region; all entries are manual.

TRADITIONAL_DANCES: list[dict] = [

    # Bali
    {"name": "Kecak",        "locatedIn": "Bali"},  # fire & trance dance; performed at Uluwatu/Ubud
    {"name": "Legong",       "locatedIn": "Bali"},  # classical female court dance
    {"name": "Barong_Dance", "locatedIn": "Bali"},  # mythical lion-creature dance (good vs. evil)
    {"name": "Pendet",       "locatedIn": "Bali"},  # flower-offering welcome dance
    {"name": "Baris_Dance",  "locatedIn": "Bali"},  # warrior dance performed by males
    {"name": "Topeng_Dance", "locatedIn": "Bali"},  # sacred mask dance; part of temple ceremonies

    # West Nusa Tenggara (NTB)
    {"name": "Tari_Oncer", "locatedIn": "West_Nusa_Tenggara"},  # Lombok fan dance; performed at weddings
    {"name": "Rudat",      "locatedIn": "West_Nusa_Tenggara"},  # Islamic-influenced Lombok dance
    {"name": "Kayak_Sando","locatedIn": "West_Nusa_Tenggara"},  # Sumbawa horse-riding ceremonial dance

    # East Nusa Tenggara (NTT)
    {"name": "Hegong",  "locatedIn": "East_Nusa_Tenggara"},  # Manggarai ceremonial dance, Flores
    {"name": "Ja_i",    "locatedIn": "East_Nusa_Tenggara"},  # Ngada/Flores communal group dance
    {"name": "Likurai", "locatedIn": "East_Nusa_Tenggara"},  # Timor war & welcome drum dance
]


# ── Traditional Houses 
# TraditionalHouse ⊑ CulturalAttraction ⊑ TouristAttraction
#                  ⊑ Establishments  (can have servesFood edge)
# DBpedia does not reliably classify Indonesian vernacular architecture; all manual.

TRADITIONAL_HOUSES: list[dict] = [

    # Bali
    {"name": "Bale_Banjar", "locatedIn": "Bali"},  # communal village meeting pavilion
    {"name": "Jineng",      "locatedIn": "Bali"},  # traditional Balinese rice granary/barn

    # West Nusa Tenggara (NTB)
    {"name": "Bale_Lumbung",     "locatedIn": "West_Nusa_Tenggara"},  # iconic rice-barn shaped Sasak house, Lombok
    {"name": "Rumah_Adat_Bayan", "locatedIn": "West_Nusa_Tenggara"},  # traditional Bayan Wetu Telu house, N. Lombok
    {"name": "Dalam_Loka",       "locatedIn": "West_Nusa_Tenggara"},  # Sumbawa royal palace; traditional timber architecture

    # East Nusa Tenggara (NTT)
    {"name": "Mbaru_Niang",      "locatedIn": "East_Nusa_Tenggara"},  # iconic cone-shaped Manggarai house, Ruteng/Flores
    {"name": "Sa_o",             "locatedIn": "East_Nusa_Tenggara"},  # traditional communal house of Lio people, Ende
    {"name": "Rumah_Adat_Sumba", "locatedIn": "East_Nusa_Tenggara"},  # high-peaked ancestral Marapu house, Sumba
]


# ── Restaurants ───────
# Restaurant ⊑ Establishments
# DBpedia has no restaurant data for this region; all entries are manual.

RESTAURANTS: list[dict] = [

    # Bali
    {"name": "Locavore",               "locatedIn": "Bali"},  # award-winning farm-to-table, Ubud
    {"name": "Merah_Putih_Restaurant", "locatedIn": "Bali"},  # modern Indonesian fine dining, Seminyak
    {"name": "Mozaic_Restaurant",      "locatedIn": "Bali"},  # French-Indonesian fine dining, Ubud
    {"name": "Sardine_Restaurant",     "locatedIn": "Bali"},  # organic Balinese cuisine, Seminyak
    {"name": "Wahaha_Restaurant",      "locatedIn": "Bali"},  # traditional Balinese, Sanur

    # West Nusa Tenggara (NTB)
    {"name": "Ashtari_Restaurant",     "locatedIn": "West_Nusa_Tenggara"},  # hilltop panoramic views, Kuta Lombok
    {"name": "Bale_Lombok_Restaurant", "locatedIn": "West_Nusa_Tenggara"},  # traditional Sasak cuisine, Mataram
    {"name": "Square_Restaurant",      "locatedIn": "West_Nusa_Tenggara"},  # contemporary cuisine, Senggigi

    # East Nusa Tenggara (NTT)
    {"name": "Kampung_Ujung_Restaurant", "locatedIn": "East_Nusa_Tenggara"},  # local seafood, Labuan Bajo
    {"name": "Tree_Top_Restaurant",      "locatedIn": "East_Nusa_Tenggara"},  # eco restaurant near Ruteng, Flores
]


# ── Street Vendors ────
# StreetVendor ⊑ Establishments
# Includes warungs (small local eateries) and night markets.

STREET_VENDORS: list[dict] = [

    # Bali
    {"name": "Warung_Ibu_Oka",          "locatedIn": "Bali"},  # iconic babi guling warung, Ubud
    {"name": "Warung_Nasi_Ayam_Bu_Mus", "locatedIn": "Bali"},  # famous nasi ayam, Kedewatan/Ubud
    {"name": "Kreneng_Night_Market",    "locatedIn": "Bali"},  # street food night market, Denpasar

    # West Nusa Tenggara (NTB)
    {"name": "Warung_Taliwang_Irama", "locatedIn": "West_Nusa_Tenggara"},  # famous ayam taliwang, Mataram
    {"name": "Pasar_Malam_Sindu",     "locatedIn": "West_Nusa_Tenggara"},  # Mataram night market

    # East Nusa Tenggara (NTT)
    {"name": "Warung_Seafood_Kupang",   "locatedIn": "East_Nusa_Tenggara"},  # local seafood stalls, Kupang
    {"name": "Pasar_Malam_Labuan_Bajo", "locatedIn": "East_Nusa_Tenggara"},  # night market, Labuan Bajo
]


# ── Traditional Markets ───────────────────────────────────────────────────────
# TraditionalMarket ⊑ Establishments
# Local pasar (traditional open-air markets).

TRADITIONAL_MARKETS: list[dict] = [

    # Bali
    {"name": "Pasar_Badung",   "locatedIn": "Bali"},  # central market, Denpasar (largest in Bali)
    {"name": "Pasar_Ubud",     "locatedIn": "Bali"},  # Ubud traditional market
    {"name": "Pasar_Sukawati", "locatedIn": "Bali"},  # art & handicraft market, Gianyar

    # West Nusa Tenggara (NTB)
    {"name": "Pasar_Cakranegara", "locatedIn": "West_Nusa_Tenggara"},  # main market, Mataram
    {"name": "Pasar_Bertais",     "locatedIn": "West_Nusa_Tenggara"},  # largest traditional market, Mataram

    # East Nusa Tenggara (NTT)
    {"name": "Pasar_Inpres_Labuan_Bajo", "locatedIn": "East_Nusa_Tenggara"},  # local market, Labuan Bajo
    {"name": "Pasar_Oebobo",             "locatedIn": "East_Nusa_Tenggara"},  # traditional market, Kupang
]


# ── Resorts ───────────
# Resort ⊑ Accommodation
# City -> hasAccommodation -> Resort

RESORTS: list[dict] = [

    # Bali
    {"name": "Four_Seasons_Resort_Sayan", "locatedIn": "Bali"},  # iconic Ayung river valley resort, Ubud
    {"name": "Alila_Villas_Uluwatu",      "locatedIn": "Bali"},  # cliffside eco resort, Uluwatu
    {"name": "COMO_Shambhala_Estate",     "locatedIn": "Bali"},  # wellness & yoga retreat, Ubud
    {"name": "Amanusa",                   "locatedIn": "Bali"},  # luxury resort, Nusa Dua

    # West Nusa Tenggara (NTB)
    {"name": "Katamaran_Resort_Lombok", "locatedIn": "West_Nusa_Tenggara"},  # beachfront, Senggigi
    {"name": "Qunci_Villas_Hotel",      "locatedIn": "West_Nusa_Tenggara"},  # boutique resort, Senggigi
    {"name": "Jeeva_Klui_Resort",       "locatedIn": "West_Nusa_Tenggara"},  # beachfront, Mangsit/Senggigi

    # East Nusa Tenggara (NTT)
    {"name": "Plataran_Komodo_Resort",  "locatedIn": "East_Nusa_Tenggara"},  # eco resort, Labuan Bajo
    {"name": "Sudamala_Resort_Komodo",  "locatedIn": "East_Nusa_Tenggara"},  # luxury resort, Labuan Bajo
]


# ── Villas ────────────
# Villa ⊑ Accommodation

VILLAS: list[dict] = [

    # Bali
    {"name": "Alila_Villas_Soori", "locatedIn": "Bali"},  # volcanic black-sand coast, Tabanan
    {"name": "Karma_Kandara",      "locatedIn": "Bali"},  # cliffside private villas, Uluwatu
    {"name": "The_Royal_Purnama",  "locatedIn": "Bali"},  # beachfront boutique villas, Gianyar

    # West Nusa Tenggara (NTB)
    {"name": "Selong_Selo_Villas", "locatedIn": "West_Nusa_Tenggara"},  # hillside villas, South Lombok
    {"name": "Jeeva_Beloam",       "locatedIn": "West_Nusa_Tenggara"},  # beach camp villas, Southeast Lombok

    # East Nusa Tenggara (NTT)
    {"name": "Sudamala_Surya_Djiwa", "locatedIn": "East_Nusa_Tenggara"},  # private villas, Labuan Bajo
]


# ── Guesthouses ───────
# Guesthouse ⊑ Accommodation
# Includes homestays and budget boutique lodging.

GUESTHOUSES: list[dict] = [

    # Bali
    {"name": "Pondok_Pitaya",            "locatedIn": "Bali"},  # garden guesthouse, Ubud
    {"name": "Sanur_Sunrise_Guesthouse", "locatedIn": "Bali"},  # beachside guesthouse, Sanur

    # West Nusa Tenggara (NTB)
    {"name": "Kuta_Indah_Guesthouse", "locatedIn": "West_Nusa_Tenggara"},  # budget stay, Kuta Lombok

    # East Nusa Tenggara (NTT)
    {"name": "Gardena_Guesthouse", "locatedIn": "East_Nusa_Tenggara"},  # local guesthouse, Kupang
    {"name": "Wae_Rebo_Homestay",  "locatedIn": "East_Nusa_Tenggara"},  # traditional village homestay, Manggarai
]


# ── Hostels ───────────
# Hostel ⊑ Accommodation

HOSTELS: list[dict] = [

    # Bali
    {"name": "Puri_Garden_Hostel", "locatedIn": "Bali"},  # backpacker hostel, Kuta
    {"name": "Tribal_Hostel",      "locatedIn": "Bali"},  # social hostel, Canggu

    # West Nusa Tenggara (NTB)
    {"name": "Shady_Shack_Hostel", "locatedIn": "West_Nusa_Tenggara"},  # surf hostel, Kuta Lombok

    # East Nusa Tenggara (NTT)
    {"name": "Bajo_Komodo_Hostel", "locatedIn": "East_Nusa_Tenggara"},  # budget hostel, Labuan Bajo
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
        "Gedong_Arca_Museum__Bedulu":3.7,
        "Gedong_Kirtya":             4.5,
        "Bajra_Sandhi_Monument":     4.6,
    },
    "Hotel": {
        "Amankila":                  4.7,
        "Tandjung_Sari":             4.7,
        "Tjampuhan_Hotel":           4.6,
        "InterContinental_Hotel_Bali":4.7,
        "Belmond_Jimbaran_Puri":     4.7,
    },
    "Volcano": {
        "Mount_Agung":               4.5,
        "Mount_Batur":               4.3,
        "Mount_Tambora":             4.8,
    },
    "Park": {
        "Komodo_National_Park":              4.6,
        "Kelimutu_National_Park":            4.6,  # was: Kelimutu
        "Mount_Rinjani_National_Park":       4.5,  # was: Mount_Rinjani (Volcano)
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
    "Gedong_Arca_Museum__Bedulu":     True,
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
