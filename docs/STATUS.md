# Where we got to - 2026-08-27

## Done

**Data layer**
- 11-table star schema in Supabase Postgres (eu-central-1, Frankfurt)
- 199,156 rows loaded; 13 mart tables built by `sql/02_marts.sql`
- Real Potsdam weather (Open-Meteo) + real Brandenburg public holidays
- Full cost model through to operating profit: 13.7% of net revenue
- `validate_data.py` - all 7 plausibility checks pass

**Daily entry**
- Streamlit form (`src/app.py`), English with German till-receipt hints
- Missing-day detection, empty-save guard, post-save summary
- Reads/writes Supabase live

**Power BI**
- Connected via session pooler, all 13 mart tables imported
- Relationships cleaned: deleted 2 ambiguous, activated 2 that Power BI had
  silently deactivated. ALL relationships now Active.
- `dim_date` marked as date table on `full_date`
- Sort-by columns set on `month_name` / `day_name`

## Next session

1. **Save the .pbix** to `dashboard/pizza-analytics.pbix` if not already done
2. Paste the measures from `docs/powerbi_setup.md` section 5
   (note: table names are `'mart kpi_daily'` with a SPACE - already quoted
   correctly in that file)
3. Build page 1 - Overview (see section 6)
4. Then the ML layer: forecasting, basket analysis, RFM, churn,
   delivery-time, anomaly detection. Needs `pip install prophet shap` first
   - the only two packages still missing.

## Gotchas hit, so they are not re-discovered

- **Power BI cert error**: Supabase signs the pooler cert with its own private
  CA. Fixed by unticking "Encrypt connections" in Data source settings.
  Traffic is now UNENCRYPTED - install the Supabase CA before any real data.
- **EMAXCONNSESSION**: session pooler caps at 15 clients. Power BI default of
  8 parallel evaluations exceeded it. Set to 3 in Options > Data Load.
- **pandas 3.x needs SQLAlchemy >= 2.0.36.** With an older SQLAlchemy pandas
  silently stops recognising it and `read_sql` dies with
  "'Engine' object has no attribute 'cursor'". Both pinned in requirements.txt.
- **Power BI's newer dialogs ignore synthetic clicks** on primary buttons
  (Save / Close / Delete toolbar). The row "..." context menus do work.
