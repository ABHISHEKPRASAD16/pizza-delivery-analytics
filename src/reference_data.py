"""Fixed reference data for Pizza Delivery Analytics.

Store sits in Waldstadt (PLZ 14478), NOT the city centre, so all delivery
distances are measured outward from Waldstadt.
"""

STORE = {
    "name": "Pizza Delivery Analytics",
    "plz": "14478",
    "lat": 52.3714,
    "lon": 13.0847,
}

# key, plz, district, distance_km, base_drive_min, delivery_fee
ZONES = [
    (1, "14478", "Waldstadt / Schlaatz",                  1.2,  5, 0.00),  # home zone
    (2, "14480", "Am Stern / Drewitz / Kirchsteigfeld",   2.8,  9, 1.50),
    (3, "14473", "Zentrum Ost / Templiner Vorstadt",      3.0, 10, 1.50),
    (4, "14471", "Potsdam West / Brandenburger Vorstadt", 4.0, 13, 2.00),
    (5, "14467", "Innenstadt / Noerdliche Innenstadt",    4.2, 13, 2.00),
    (6, "14482", "Babelsberg / Klein Glienicke",          5.5, 16, 2.50),
    (7, "14469", "Bornstedt / Nauener Vorstadt",          6.5, 18, 3.00),
    (8, "14476", "Golm / Eiche / Grube",                  9.5, 24, 3.50),
]

# Share of delivery orders per zone: close + dense residential dominates.
ZONE_WEIGHTS = [0.26, 0.19, 0.14, 0.11, 0.10, 0.09, 0.07, 0.04]

# key, name, is_aggregator, commission_rate
CHANNELS = [
    (1, "Telefon",    False, 0.00),
    (2, "Website",    False, 0.00),
    (3, "App",        False, 0.00),
    (4, "Lieferando", True,  0.13),
    (5, "Abholung",   False, 0.00),
]

DAYPARTS = [
    ("Mittag",      11, 14),
    ("Nachmittag",  14, 17),
    ("Abend",       17, 21),
    ("Spaet",       21, 24),
]

DRIVERS = [
    (1, "Fahrer A", "Roller"),
    (2, "Fahrer B", "Roller"),
    (3, "Fahrer C", "Auto"),
    (4, "Fahrer D", "Roller"),
    (5, "Fahrer E", "Auto"),
    (6, "Fahrer F", "Fahrrad"),
]


# ---------------------------------------------------------------------
# Menu.  (name, category, size, price_eur, cost_eur, vegetarian)
# ---------------------------------------------------------------------
PIZZA_SIZES = [("Klein 24cm", 1.00), ("Normal 30cm", 1.28), ("Familie 40cm", 2.20)]

PIZZAS = [  # name, klein_price, klein_cost, vegetarian
    ("Pizza Margherita",       6.50, 1.80, True),
    ("Pizza Salami",           7.50, 2.20, False),
    ("Pizza Schinken",         7.50, 2.20, False),
    ("Pizza Funghi",           7.50, 2.00, True),
    ("Pizza Hawaii",           8.00, 2.30, False),
    ("Pizza Tonno",            8.00, 2.50, False),
    ("Pizza Vegetaria",        8.00, 2.20, True),
    ("Pizza Diavolo",          8.00, 2.40, False),
    ("Pizza Quattro Formaggi", 8.50, 2.60, True),
    ("Pizza Doener",           8.50, 2.70, False),
    ("Pizza Spezial",          9.00, 2.90, False),
]

OTHER_ITEMS = [  # name, category, price, cost, vegetarian
    ("Spaghetti Bolognese",  "Pasta",      8.50, 2.30, False),
    ("Penne Arrabbiata",     "Pasta",      8.00, 1.90, True),
    ("Lasagne",              "Pasta",      9.50, 2.80, False),
    ("Tortellini Panna",     "Pasta",      9.00, 2.50, True),
    ("Spaghetti Carbonara",  "Pasta",      9.00, 2.60, False),
    ("Gemischter Salat",     "Salat",      5.50, 1.60, True),
    ("Thunfischsalat",       "Salat",      7.50, 2.40, False),
    ("Griechischer Salat",   "Salat",      7.00, 2.20, True),
    ("Caesar Salat",         "Salat",      7.50, 2.30, False),
    ("Chicken Wings 6er",    "Snacks",     6.50, 2.10, False),
    ("Chicken Nuggets 9er",  "Snacks",     6.00, 1.90, False),
    ("Pommes",               "Snacks",     3.50, 0.80, True),
    ("Mozzarella Sticks",    "Snacks",     5.50, 1.70, True),
    ("Knoblauchbrot",        "Snacks",     4.00, 0.90, True),
    ("Tiramisu",             "Dessert",    4.50, 1.30, True),
    ("Muffin Schoko",        "Dessert",    3.00, 0.80, True),
    ("Eis Vanille",          "Dessert",    3.50, 1.00, True),
    ("Cola 0,5l",            "Getraenke",  2.50, 0.75, True),
    ("Fanta 0,5l",           "Getraenke",  2.50, 0.75, True),
    ("Sprite 0,5l",          "Getraenke",  2.50, 0.75, True),
    ("Wasser 0,5l",          "Getraenke",  2.00, 0.45, True),
    ("Bier 0,5l",            "Getraenke",  3.00, 1.00, True),
]

# ---------------------------------------------------------------------
# Brandenburg SCHOOL holidays, school year 2025/26.
# !! APPROXIMATE - ferien-api.de is down; replace with official MBJS dates
# !! before presenting this to a client.  Public holidays ARE exact
# !! (sourced from the `holidays` package, subdiv='BB').
# ---------------------------------------------------------------------
SCHOOL_HOLIDAYS_BB = [
    ("Herbstferien",      "2025-10-20", "2025-11-01"),
    ("Weihnachtsferien",  "2025-12-22", "2026-01-02"),
    ("Winterferien",      "2026-02-02", "2026-02-07"),
    ("Osterferien",       "2026-03-30", "2026-04-10"),
    ("Himmelfahrt-Brueckentag", "2026-05-15", "2026-05-15"),
    ("Sommerferien",      "2026-07-09", "2026-08-22"),
]


# ---------------------------------------------------------------------
# Cost model for a Potsdam franchise branch.
#
# Kept here (not buried in the generator) so the assumptions are visible
# and arguable. These are estimates for a branch of this size, NOT figures
# from any real set of books - replace them with actuals
# before any of this informs a real decision.
# ---------------------------------------------------------------------

# Fully loaded hourly cost: gross wage plus ~21% employer contributions
# (Lohnnebenkosten). Using the loaded figure keeps labour honest - the
# gross wage alone understates payroll by a fifth.
KITCHEN_WAGE = 15.50
DRIVER_WAGE = 15.00

# Monthly fixed costs, EUR.  (item, monthly_eur, note)
FIXED_COSTS_MONTHLY = [
    ("Miete",            3600.00, "Ladenlokal inkl. Kueche, Waldstadt"),
    ("Energie",          2100.00, "Gasoefen, Kuehlung, Strom"),
    ("Fahrzeuge",        1600.00, "3 Roller + 1 Auto: Leasing, Sprit, Wartung"),
    ("Versicherungen",    400.00, "Betriebshaftpflicht, Inhalt, KFZ"),
    ("Marketing lokal",   650.00, "Flyer, lokale Aktionen"),
    ("Verwaltung",        520.00, "Buchhaltung, Kassensystem, Software"),
    ("Reinigung/Wartung", 480.00, "Reinigung, Ofenwartung"),
    ("Sonstiges",         450.00, "Puffer"),
]

# Variable costs as a share of revenue.  (item, rate, base, note)
VARIABLE_COST_RATES = [
    ("Verpackung",          0.035, "gross",   "Pizzakartons, Tueten, Servietten"),
    ("Zahlungsgebuehren",   0.016, "cashless", "Karten- und Online-Zahlungen"),
    ("Franchise-Royalty",   0.050, "net",     "Lizenzgebuehr an den Franchisegeber"),
    ("Marketingumlage",     0.020, "net",     "nationale Werbung, Franchisegeber"),
]

# Share of orders paid by card or online rather than cash.
CASHLESS_SHARE = 0.70
