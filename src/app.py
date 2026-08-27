"""Daily close - entry form for Pizza Delivery Analytics.

Run:  streamlit run src/app.py

Design goal: under 90 seconds on a phone at 23:30 after a long shift.
Labels are English, with the German term alongside where the number is read
off a German till receipt, so the form can be matched line by line against
the Z-Bon without needing to read German.

Everything is pre-filled and mistakes are correctable. The only blocked save
is a completely empty one, which would otherwise overwrite a real day.
"""
from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent))
from storage import DailyEntryStore  # noqa: E402

st.set_page_config(page_title="Daily Close",
                   page_icon="🍕", layout="centered")


@st.cache_resource
def get_store() -> DailyEntryStore:
    return DailyEntryStore()


store = get_store()

# ------------------------------------------------------------------ header
st.title("🍕 Daily Close")
st.caption("Pizza Delivery Analytics")

if store.backend == "postgres":
    st.success("Connected to Supabase", icon="✅")
elif not store.durable:
    # Hosted, but no database. Anything typed here would be written to a disk
    # that is wiped on the next restart - the form would claim success every
    # night and lose the lot. Refuse rather than pretend.
    st.error("**Not connected to the database — the form is disabled.**")
    st.markdown(
        "Entries typed here could not be saved anywhere permanent, so the "
        "form is switched off rather than silently losing your numbers.")
    if store.reason:
        st.code(store.reason, language=None)
    st.markdown(
        "**Fix:** app menu (top right) → **Settings → Secrets**, add the five "
        "keys below, save. The app restarts on its own.")
    st.code(
        '\n'.join([
            'PGHOST = "aws-0-<region>.pooler.supabase.com"',
            'PGPORT = "5432"',
            'PGDATABASE = "postgres"',
            'PGUSER = "postgres.<your-project-ref>"',
            'PGPASSWORD = "<your-database-password>"',
        ]),
        language="toml")
    st.stop()
else:
    st.warning("Local test mode - no database connected. Entries are saved to "
               "a local file on this machine only.", icon="⚠️")

history = store.load()

# --------------------------------------------------- reminder: missed days
missing = store.missing_days(back=14)
if missing:
    label = ", ".join(d.strftime("%d.%m.") for d in missing[-5:])
    st.error(f"**Missing days:** {label}  \n"
             f"Please fill these in - gaps distort the forecast.", icon="📅")

# ----------------------------------------------------------------- date
chosen = st.date_input("Date", value=date.today(), format="DD.MM.YYYY")
existing = store.get(chosen)
if existing:
    st.info(f"An entry already exists for {chosen.strftime('%d.%m.%Y')}. "
            f"The fields are pre-filled - saving will overwrite it.", icon="✏️")


def prev(field: str, default=0):
    """Value from the existing entry, else 0/default."""
    if existing and pd.notna(existing.get(field)):
        return existing[field]
    return default


def reference(field: str):
    """Same weekday last week - shown as a sanity anchor on each field."""
    if history.empty:
        return None
    target = chosen - timedelta(days=7)
    hit = history[history.business_date == target]
    return None if hit.empty else hit.iloc[0][field]


def hint(field: str, unit: str = "") -> str:
    ref = reference(field)
    if ref is None:
        return ""
    return f"same day last week: {ref:,.0f}{unit}"


# ----------------------------------------------------------------- form
with st.form("daily_close", clear_on_submit=False):

    st.subheader("From the till receipt (Z-Bon)")
    c1, c2 = st.columns(2)
    total_orders = c1.number_input(
        "Total orders · Bestellungen", min_value=0, step=1,
        value=int(prev("total_orders")), help=hint("total_orders"))
    gross_revenue = c2.number_input(
        "Gross revenue € · Umsatz", min_value=0.0, step=10.0, format="%.2f",
        value=float(prev("gross_revenue")), help=hint("gross_revenue", " EUR"))

    c3, c4, c5 = st.columns(3)
    delivery_orders = c3.number_input(
        "Deliveries · Lieferung", min_value=0, step=1,
        value=int(prev("delivery_orders")))
    pickup_orders = c4.number_input(
        "Pickups · Abholung", min_value=0, step=1,
        value=int(prev("pickup_orders")))
    cancelled = c5.number_input(
        "Cancelled · Storno", min_value=0, step=1, value=int(prev("cancelled")))

    st.subheader("From the shift")
    c6, c7 = st.columns(2)
    staff_hours = c6.number_input(
        "Kitchen hours", min_value=0.0, step=0.5, format="%.1f",
        value=float(prev("staff_hours")), help=hint("staff_hours", " h"))
    driver_hours = c7.number_input(
        "Driver hours", min_value=0.0, step=0.5, format="%.1f",
        value=float(prev("driver_hours")), help=hint("driver_hours", " h"))

    c8, c9 = st.columns(2)
    waste_eur = c8.number_input(
        "Waste €", min_value=0.0, step=1.0, format="%.2f",
        value=float(prev("waste_eur")))
    complaints = c9.number_input(
        "Complaints", min_value=0, step=1, value=int(prev("complaints")))

    st.subheader("Context")
    is_closed = st.checkbox(
        "🚫 Closed today (no trading)",
        value=bool(prev("is_closed", False)),
        help="Only tick this if the shop genuinely did not open.")
    promo_active = st.checkbox("Promotion running?",
                               value=bool(prev("promo_active", False)))
    promo_note = st.text_input("Which promotion?",
                               value=prev("promo_note", "") or "")
    notes = st.text_area("Notes", value=prev("notes", "") or "",
                         placeholder="e.g. driver off sick, oven slow, power cut")
    entered_by = st.text_input("Entered by",
                               value=prev("entered_by", "") or "Abhishek")

    submitted = st.form_submit_button("💾 SAVE", use_container_width=True,
                                      type="primary")

# --------------------------------------------------------------- validate
if submitted:
    # ---------------------------------------------------------------------
    # The one case where saving is blocked rather than warned about.
    # upsert() overwrites, so an empty form submitted by mistake would
    # silently replace a real trading day with zeros. A genuine closed day
    # has to be stated explicitly.
    # ---------------------------------------------------------------------
    if not is_closed and total_orders == 0 and gross_revenue == 0:
        st.error(
            "**Not saved.** Both orders and revenue are 0.  \n"
            "Was the shop closed? Then tick **Closed today** above. "
            "Otherwise please enter the numbers from the till receipt.",
            icon="🚫")
        st.stop()

    warnings: list[str] = []

    if delivery_orders + pickup_orders != total_orders:
        warnings.append(
            f"Deliveries + pickups = {delivery_orders + pickup_orders}, "
            f"but total orders = {total_orders}.")

    if total_orders > 0 and not is_closed:
        aov = gross_revenue / total_orders
        if not 12 <= aov <= 45:
            warnings.append(f"Average order value {aov:.2f} EUR is outside "
                            f"the usual range (12-45 EUR).")

    if total_orders > 0 and gross_revenue == 0:
        warnings.append("Orders recorded but revenue is 0 EUR.")

    if staff_hours == 0 and total_orders > 0:
        warnings.append("Kitchen hours are 0, but there were orders.")

    for w in warnings:
        st.warning(w, icon="⚠️")

    record = {
        "business_date": chosen,
        "total_orders": int(total_orders),
        "gross_revenue": round(float(gross_revenue), 2),
        "delivery_orders": int(delivery_orders),
        "pickup_orders": int(pickup_orders),
        "cancelled": int(cancelled),
        "waste_eur": round(float(waste_eur), 2),
        "staff_hours": round(float(staff_hours), 1),
        "driver_hours": round(float(driver_hours), 1),
        "promo_active": bool(promo_active),
        "is_closed": bool(is_closed),
        "promo_note": promo_note or None,
        "complaints": int(complaints),
        "notes": notes or None,
        "entered_by": entered_by or None,
    }

    # Warnings never block - an unusual day is still a real day.
    action = store.upsert(record)
    st.success(f"**{chosen.strftime('%d.%m.%Y')} {action}.**", icon="✅")
    st.balloons()

    # ------------------------------------------------- mini summary
    st.subheader("At a glance")
    ref_orders = reference("total_orders")
    ref_rev = reference("gross_revenue")

    def delta(now, before):
        if before in (None, 0) or pd.isna(before):
            return None
        return f"{(now / before - 1) * 100:+.0f} % vs last week"

    m1, m2, m3 = st.columns(3)
    m1.metric("Orders", f"{total_orders:,}", delta(total_orders, ref_orders))
    m2.metric("Revenue", f"{gross_revenue:,.2f} EUR", delta(gross_revenue, ref_rev))
    m3.metric("Avg order",
              f"{gross_revenue / total_orders:.2f} EUR" if total_orders else "-")

    m4, m5, m6 = st.columns(3)
    m4.metric("Delivery share",
              f"{delivery_orders / total_orders * 100:.0f} %" if total_orders else "-")
    m5.metric("Labour / revenue",
              f"{(staff_hours * 15.5 + driver_hours * 15.0) / gross_revenue * 100:.0f} %"
              if gross_revenue else "-")
    m6.metric("Waste", f"{waste_eur:.2f} EUR")

    st.caption("Everything else is automatic: ETL runs tonight, "
               "Power BI refreshes at 06:00.")

# ------------------------------------------------------------- last 7 days
with st.expander("Last 7 entries"):
    if history.empty:
        st.write("No entries yet.")
    else:
        recent = history.tail(7)[
            ["business_date", "total_orders", "gross_revenue", "staff_hours"]
        ].rename(columns={
            "business_date": "Date", "total_orders": "Orders",
            "gross_revenue": "Revenue EUR", "staff_hours": "Kitchen h"})
        st.dataframe(recent.iloc[::-1], hide_index=True, use_container_width=True)
