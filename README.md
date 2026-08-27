# Pizza Delivery Analytics

End-to-end analytics for a single-branch pizza delivery business in Potsdam,
Germany. Built as a portfolio project: nightly data capture on a phone, a
dimensionally modelled warehouse on Postgres, five ML models, and a Streamlit
dashboard - with Power BI as an optional reporting layer on top.

**The data is synthetic.** Order history is generated, but driven by *real*
Potsdam weather (Open-Meteo) and *real* Brandenburg public holidays, so the
relationships the models find are grounded in genuine exogenous variation
rather than noise. No real business, customer or financial data is used
anywhere in this repository.

Interface language is English. German appears only where it maps to something
physical - a till-receipt line, or a label a German-speaking colleague reads.

## Architecture

```
  app.py  - entry form (phone)     ~85 seconds/day
              |
              v
  Supabase   staging.daily_entry          as typed
              |
              |  build_marts.py
              v
  Supabase   core.*  ->  mart.*           star schema -> reporting layer
              |                            (incl. mart.daily_actuals, which
              |                             merges form entries with history)
              +--------------------+
              |                    |
              v                    v
  dashboard.py              Power BI
  (all the analysis)        (2 pages, for sharing)
```

Two Streamlit apps, one command each:

| App | Who / when | What |
|---|---|---|
| `app.py` | shift lead, nightly, phone | 12 fields off the till receipt |
| `dashboard.py` | you, desktop | 7 tabs: overview, profit, zones, forecast, customers, menu, daily log |

Power BI is optional on top - useful for handing a report to the franchise
owner, not needed to see the numbers.

## Data

Synthetic order history driven by **real** external data:

- **Weather** - Open-Meteo ERA5 archive for the store coordinates
- **Public holidays** - `holidays` package, Germany `subdiv="BB"`
- **School holidays** - hardcoded Brandenburg dates, approximate; see
  `reference_data.SCHOOL_HOLIDAYS_BB`

Range 2025-09-01 to 2026-08-20: 40,633 orders, 155,175 order lines,
2,200 pseudonymous customers, 354 days.

> The order data is synthetic. Relationships the models find are real
> relationships *in this data*, grounded in real weather and holidays, but
> they are not evidence about the real branch.

## Cost model

The P&L assumptions live in `src/reference_data.py`, deliberately visible
rather than buried in code, and are also loaded into
`mart.dim_cost_assumption` so the dashboard can show what profit rests on.

| Line | Share of net revenue |
|---|---|
| Food cost | 29.7 % |
| Packaging | 3.6 % |
| Waste | 0.7 % |
| Labour (incl. employer contributions) | 33.6 % |
| Payment fees | 1.1 % |
| Fixed costs (rent, energy, vehicles, ...) | 10.5 % |
| Franchise licence + ad levy | 7.0 % |
| **Operating profit** | **13.7 %** |

> These are estimates for a branch of this size, **not** figures from the real
> Waldstadt books. Replace them with actuals before any of this informs a real
> decision.

## Layout

```
data/raw/          external pulls (weather, calendar)
data/processed/    generated tables + data/processed/mart/
sql/               01_schema.sql (core), 02_marts.sql (Power BI layer)
src/               pipeline and app
docs/              setup guides and data dictionary
```

## Running it

```bash
pip install -r requirements.txt
```

```bash
python src/fetch_external.py          # real weather + holidays -> dim_date
```

```bash
python src/generate_data.py           # build the synthetic warehouse
```

```bash
python src/validate_data.py           # quality gate - run after any change
```

```bash
python src/build_marts.py --local     # marts via DuckDB, no database needed
```

```bash
streamlit run src/app.py              # nightly entry form
```

```bash
streamlit run src/dashboard.py        # the analytics dashboard
```

Once `.env` is configured (see `docs/supabase_setup.md`):

```bash
python src/check_load_types.py        # pre-flight: dtypes vs schema
```

```bash
python src/load_to_postgres.py        # deploy schema + bulk COPY
```

```bash
python src/build_marts.py             # marts in Postgres
```

```bash
python src/run_ml.py                  # all 5 models -> 7 more mart tables
```

Run order matters: `build_marts.py` rebuilds the base marts, then `run_ml.py`
trains on them. Running ML first leaves its outputs describing stale data.

## Status

- [x] Star schema, 11 core tables
- [x] Real weather + Brandenburg holidays
- [x] Synthetic order generator, validated
- [x] Daily close form with missing-day detection and empty-save guard
- [x] Mart layer, 13 tables, runs on Postgres and DuckDB
- [x] Full cost model through to operating profit
- [x] Power BI guide: connection, relationships, DAX, pages, gateway
- [x] Supabase project + load (199,156 rows, eu-central-1)
- [x] Power BI connected, model cleaned, date table marked
- [x] Streamlit analytics dashboard (7 tabs)
- [x] Form wired into reporting via mart.daily_actuals
- [ ] Power BI: 2 pages for sharing (optional)
- [x] ML layer: forecast, RFM, churn, delivery, anomaly, basket (7 mart tables)
- [ ] Deploy form to Streamlit Cloud

## Known limitations

- **One year of history.** Rain and heat effects are statistically
  identifiable; cold, public-holiday and school-holiday effects are not
  (354 days contains only 12 public holidays). Extending the range in
  `fetch_external.py` fixes this. `validate_data.py` reports it every run.
- **Brandenburg school holiday dates are approximate.** Replace with official
  MBJS dates before client use.
- **Power BI connects with encryption disabled.** Supabase signs its pooler
  certificate with a private CA that Windows does not trust. Fine for
  synthetic data; install the Supabase CA before loading anything real.
  See `docs/powerbi_setup.md`.
