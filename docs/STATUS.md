# Status

The system is complete and running unattended.

## The loop

```
  phone form  ->  Supabase staging  ->  GitHub Actions, 01:00 UTC nightly
                                            |
                                    marts rebuilt + models retrained
                                            |
                                    Streamlit dashboard, correct by morning
```

Nobody opens a terminal. Verified end to end: a form entry reached
mart.daily_actuals via a scheduled run with no local involvement.

## What exists

| Piece | State |
|---|---|
| Supabase warehouse | 199k rows, staging -> core (11 tables) -> mart (20 tables) |
| Entry form | deployed, refuses to run without durable storage |
| Dashboard | deployed, 7 tabs |
| ML layer | 5 models, ~18s, writes 7 mart tables |
| Nightly refresh | GitHub Actions, tested green in 1m41s |
| Repo | public, anonymised, no secrets |

## Open items

**Do this one:**
- Rotate the Supabase database password. It was pasted into a chat during
  setup. Update it in four places afterwards: `.env`, both Streamlit apps'
  secrets, and the `PGPASSWORD` GitHub Actions secret.

**Optional polish:**
- Power BI: two pages (Overview, Profit waterfall). Guide in
  `docs/powerbi_setup.md`. The Streamlit dashboard already covers this - Power
  BI is only worth finishing to hand a report to someone who expects it.
- One year of history means public-holiday and cold-weather effects are not
  statistically identifiable. `validate_data.py` reports this every run.
  Extending `fetch_external.py` to 2024 fixes it.
- Brandenburg school-holiday dates are estimates, not official MBJS dates.
- Power BI connects with encryption disabled (Supabase uses a private CA).
  Fine for synthetic data; install the Supabase CA before anything real.
- A test row for 2026-08-21 sits in the data. Overwrite it via the form.

## If real data ever replaces the synthetic history

The cost assumptions in `src/reference_data.py` are industry estimates, not
anyone's real books. Replace them before the profit figures inform a decision.
