# Deploying to Streamlit Community Cloud

Free. Two apps can be deployed from the same repo.

---

## 1. Push the repo to GitHub

The repo is already set up so that nothing secret is committed:

| File | Status |
|---|---|
| `.env` | gitignored - your database password lives here |
| `.streamlit/secrets.toml` | gitignored |
| `data/processed/*` | gitignored - rebuilt from Supabase or `generate_data.py` |

Verify before every push:

```bash
git check-ignore -v .env .streamlit/secrets.toml
```

Both must print a `.gitignore` line. If either prints nothing, stop.

## 2. Create the app

1. <https://share.streamlit.io> -> sign in with GitHub
2. **New app** -> pick this repo, branch `main`
3. **Main file path**: `src/dashboard.py`
4. **Advanced settings -> Python version**: 3.12
5. Deploy

Repeat with `src/app.py` as the main file to deploy the entry form as a second
app. Same repo, same secrets, different entry point.

## 3. Add the secrets

App -> **Settings -> Secrets**, paste the five keys (see
`.streamlit/secrets.toml.example`):

```toml
PGHOST = "aws-0-eu-central-1.pooler.supabase.com"
PGPORT = "5432"
PGDATABASE = "postgres"
PGUSER = "postgres.your-project-ref"
PGPASSWORD = "your-database-password"
```

`src/db.py` reads Streamlit secrets first, then falls back to `.env`, so the
same code runs locally and deployed with no changes.

## 4. Point the phone at it

Once the form app is live, open its URL on your phone -> Share -> **Add to
Home Screen**. It then opens like an app, which is the whole point of the
90-second nightly routine.

---

## Why requirements.txt is split

`requirements.txt` holds only what the two apps import at runtime.
`requirements-ml.txt` holds the modelling libraries.

Streamlit Cloud installs `requirements.txt`. Prophet pulls in cmdstanpy and
compiles Stan, which is slow and a common cause of failed deploys - and the
dashboard never imports it. It reads model OUTPUT from `mart.*` tables that
were written by `run_ml.py` running on your machine.

So: train locally, serve from the database.

```bash
pip install -r requirements-ml.txt    # local, for generating and training
```

## Keeping it fresh

Nothing on Streamlit Cloud retrains anything. On your machine:

```bash
python src/build_marts.py && python src/run_ml.py
```

The deployed apps read the updated tables on their next load - no redeploy.

## Free-tier limits worth knowing

- Apps sleep after ~7 days idle and wake on first visit (slow first load).
- Supabase's session pooler caps concurrent connections; the apps use one
  connection each and cache queries for 10 minutes, so this is not a problem
  at one branch's usage.
- Supabase free projects pause after a week of no activity. Opening the
  dashboard counts as activity.
