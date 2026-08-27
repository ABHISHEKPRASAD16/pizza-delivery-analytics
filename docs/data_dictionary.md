# Data Dictionary - Pizza Delivery Analytics

Grain of the model: **one row per order line** (`fct_order_item`), rolled up to
**one row per order** (`fct_order`) and **one row per day** (`dim_date`, `fct_shift`).

## Fixed value lists used by the generator

### Channels (dim_channel)
| key | channel_name | is_aggregator | commission_rate |
|-----|--------------|---------------|-----------------|
| 1 | Telefon      | false | 0.00 |
| 2 | Website      | false | 0.00 |
| 3 | App          | false | 0.00 |
| 4 | Lieferando   | true  | 0.13 |
| 5 | Abholung     | false | 0.00 |

### Delivery zones (dim_zone) - real Potsdam PLZ
| key | plz | district_name | distance_km | base_drive_min | delivery_fee |
|-----|-----|---------------|-------------|----------------|--------------|
| 1 | 14467 | Innenstadt / Noerdliche Innenstadt | 1.5 | 6 | 1.50 |
| 2 | 14469 | Bornstedt / Nauener Vorstadt | 3.8 | 11 | 2.00 |
| 3 | 14471 | Potsdam West / Brandenburger Vorstadt | 2.6 | 8 | 1.50 |
| 4 | 14473 | Zentrum Ost / Templiner Vorstadt | 2.2 | 7 | 1.50 |
| 5 | 14476 | Golm / Eiche / Grube | 7.5 | 18 | 3.50 |
| 6 | 14478 | Waldstadt / Schlaatz | 4.5 | 13 | 2.00 |
| 7 | 14480 | Am Stern / Drewitz / Kirchsteigfeld | 6.2 | 16 | 2.50 |
| 8 | 14482 | Babelsberg / Klein Glienicke | 5.0 | 14 | 2.50 |

### Dayparts
`Mittag` 11:00-14:00 | `Nachmittag` 14:00-17:00 | `Abend` 17:00-21:00 | `Spaet` 21:00-23:30

### Menu categories (dim_item)
`Pizza` (3 sizes: Klein 24cm / Normal 30cm / Familie 40cm) | `Pasta` | `Salat` | `Snacks` | `Dessert` | `Getraenke`
