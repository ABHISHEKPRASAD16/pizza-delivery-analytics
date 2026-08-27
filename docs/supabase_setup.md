# Supabase setup

You do steps 1-4 yourself (they need your own login). Steps 5-6 are commands.

**Never paste the database password into a chat, a commit, or a screenshot.**
It goes in `.env`, which `.gitignore` already excludes.

---

## 1. Create the project

1. Go to <https://supabase.com> and sign up (GitHub login is fastest).
2. **New project**.
3. Name: `pizza-delivery-analytics`
4. **Region: `Central EU (Frankfurt)`** - pick this one deliberately:
   - lowest latency to Potsdam
   - keeps data in the EU, which matters once any of this touches real
     customer records under GDPR. A US region would be a problem you would
     have to explain to the franchise owner later.
5. Generate a strong database password and save it in your password manager.
6. Create, then wait ~2 minutes for provisioning.

## 2. Get the connection details

Project → **Connect** (top bar) → **Session pooler**.

Use the **Session pooler**, not "Direct connection". Supabase direct
connections are IPv6-only on the free tier, and most home and office networks
in Germany are still IPv4 - you would just get a timeout.

The pooler details look like this:

```
Host      aws-0-eu-central-1.pooler.supabase.com
Port      5432
Database  postgres
User      postgres.abcdefghijklmnop      <- note the project ref suffix
```

## 3. Create your .env

```bash
cp .env.example .env
```

Then open `.env` and fill in the four values plus your password:

```
PGHOST=aws-0-eu-central-1.pooler.supabase.com
PGPORT=5432
PGDATABASE=postgres
PGUSER=postgres.abcdefghijklmnop
PGPASSWORD=the-password-you-saved
```

## 4. Confirm .env is ignored by git

```bash
git check-ignore -v .env
```

Should print a line naming `.gitignore`. If it prints nothing, stop and fix
`.gitignore` before continuing.

## 5. Test the connection

```bash
python src/db.py
```

Expected: `Connected OK` and a PostgreSQL version string.

**If it fails:**

| Error | Cause |
|---|---|
| `timeout expired` | Using the direct connection instead of the Session pooler |
| `password authentication failed` | Password wrong, or `PGUSER` missing the `.projectref` suffix |
| `Missing in .env` | `.env` not created, or saved as `.env.txt` by Notepad |

## 6. Deploy the schema and load the data

```bash
python src/load_to_postgres.py
```

This drops and recreates every table, then bulk-loads all ten via `COPY`.
Expect roughly 200k rows in under a minute.

Verify any time without reloading:

```bash
python src/load_to_postgres.py --verify
```

---

## What you end up with

| Schema | Contents | Who reads it |
|---|---|---|
| `staging` | `daily_entry` - raw form input | the Streamlit app writes here |
| `core` | 6 dimensions + 3 facts (star schema) | the Python ETL and ML layer |
| `mart` | built in the next step | **Power BI connects here only** |

Power BI should never point at `staging` or `core` directly. Everything it
touches goes through `mart`, so the model can be reshaped without breaking
the report.
