"""Northwind Cloud metrics dashboard.

Run from the repo root:   streamlit run dashboard/app.py

Reads the database through the Supabase Session pooler using the [db] section
of .streamlit/secrets.toml (never committed; see .streamlit/secrets.toml.example).
Every business rule lives in metrics.py; this file only draws the results.
"""
import altair as alt
import pandas as pd
import psycopg
import streamlit as st

import metrics

st.set_page_config(page_title="Northwind Cloud metrics", page_icon=":bar_chart:", layout="wide")

ACCENT = "#2a78d6"      # selected month
ACCENT_SOFT = "#86b6ef"  # other months (same hue, lighter step)


# --- Data access -------------------------------------------------------------

def _connection_args() -> dict:
    db = st.secrets["db"]
    return dict(host=db["host"], port=int(db.get("port", 5432)), dbname=db.get("dbname", "postgres"),
                user=db["user"], password=db["password"], sslmode="require", connect_timeout=10)


@st.cache_data(ttl=600, show_spinner="Querying Supabase...")
def query(sql: str, params: dict | None = None) -> pd.DataFrame:
    """Run one SELECT in a READ ONLY transaction and return it as a DataFrame."""
    with psycopg.connect(**_connection_args()) as conn:
        conn.read_only = True  # the server rejects any write in this session
        with conn.cursor() as cur:
            cur.execute(sql, params)
            columns = [c.name for c in cur.description]
            return pd.DataFrame(cur.fetchall(), columns=columns)


def money(x: float) -> str:
    return f"${x:,.2f}"


# --- Load --------------------------------------------------------------------

st.title("Northwind Cloud")
st.caption("Recurring revenue, customers and cash, computed with the rules in docs/semantic-layer.md")

try:
    _connection_args()
except Exception:
    st.error("No database settings found. Create `.streamlit/secrets.toml` with a `[db]` section "
             "(host, port, dbname, user, password); see `.streamlit/secrets.toml.example`.")
    st.stop()

try:
    span = query(metrics.DATA_MONTHS).iloc[0]
    monthly = query(metrics.MONTHLY, {"first_month": span.first_month, "last_month": span.last_month})
    currencies = sorted(query(metrics.CURRENCIES)["currency"].dropna())
except psycopg.Error as e:
    detail = (str(e).strip().splitlines() or [""])[-1]
    password = str(st.secrets["db"].get("password", ""))
    if password:
        detail = detail.replace(password, "***")  # never echo the password
    st.error(f"Could not read the database ({type(e).__name__}): {detail}\n\nCheck the [db] settings and "
             "that the host is the Session pooler, not the direct (IPv6-only) host.")
    st.stop()

for col in ["mrr", "arr", "cash_collected"]:
    monthly[col] = monthly[col].astype(float)
monthly["month"] = pd.to_datetime(monthly["month_end"]).dt.strftime("%b %Y")

# Section 4.4: one currency per sum. Refuse to draw mixed totals.
if currencies != ["USD"]:
    st.error(f"Data contains currencies {currencies}. Totals would mix currencies, so they are not shown.")
    st.stop()

# --- Controls ----------------------------------------------------------------

months = list(monthly["month"])
picked = st.selectbox("Month (snapshot at month end)", months, index=len(months) - 1)
i = months.index(picked)
row = monthly.iloc[i]
prev = monthly.iloc[i - 1] if i > 0 else None
ytd_cash = monthly.iloc[: i + 1]["cash_collected"].sum()

st.caption(f"Data covers {months[0]} to {months[-1]}. Nothing later exists, so there is no 'current month' beyond {months[-1]}.")


# --- KPI row -----------------------------------------------------------------

def delta(field: str, fmt=lambda v: f"{v:+,.0f}"):
    return None if prev is None else fmt(row[field] - prev[field])


k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("MRR", money(row.mrr), delta("mrr", lambda v: f"{v:+,.2f}"),
          help="Monthly-normalized contract value of live, non-trial, non-internal subscriptions on the last day of the month. Annual contracts count at amount / 12.")
k2.metric("ARR", money(row.arr), help="MRR x 12.")
k3.metric("Paying customers", int(row.paying_customers), delta("paying_customers"),
          help="Distinct non-internal accounts with at least one live non-trial subscription at month end. past_due still counts.")
k4.metric("Accounts on trial", int(row.trial_accounts), delta("trial_accounts"), delta_color="off",
          help="Distinct non-internal accounts with a live trial at month end. Never part of MRR.")
k5.metric("Cash collected", money(row.cash_collected),
          help="Tax-inclusive total of PAID invoices dated in the month, non-internal. Refunded, void and open invoices are excluded.")
st.caption(f"Cash collected, {months[0]} to {picked}: **{money(ytd_cash)}**")


# --- Charts ------------------------------------------------------------------

def month_bars(field: str, title: str) -> alt.Chart:
    base = monthly.assign(selected=monthly["month"] == picked, label=monthly[field].map(money))
    return (
        alt.Chart(base, title=title)
        .mark_bar(cornerRadiusTopLeft=4, cornerRadiusTopRight=4, size=48)
        .encode(
            x=alt.X("month:N", sort=months, title=None, axis=alt.Axis(labelAngle=0)),
            y=alt.Y(f"{field}:Q", title=None, axis=alt.Axis(format="$,.0f", grid=True, gridOpacity=0.3)),
            color=alt.condition("datum.selected", alt.value(ACCENT), alt.value(ACCENT_SOFT)),
            tooltip=[alt.Tooltip("month:N", title="Month"), alt.Tooltip("label:N", title=title)],
        )
        .properties(height=280)
    )


c1, c2 = st.columns(2)
c1.altair_chart(month_bars("mrr", "MRR at month end"), width="stretch")
c2.altair_chart(month_bars("cash_collected", "Cash collected in month"), width="stretch")
st.caption("MRR and cash differ on purpose: an annual contract is billed once (one lump of cash) "
           "but counts toward MRR at 1/12 every month.")


# --- Breakdown ---------------------------------------------------------------

st.subheader(f"Who makes up MRR on {pd.Timestamp(row.month_end):%d %b %Y}")
by_account = query(metrics.MRR_BY_ACCOUNT, {"month_end": row.month_end})
by_account["mrr"] = by_account["mrr"].astype(float)
st.dataframe(
    by_account,
    hide_index=True,
    width="stretch",
    column_config={
        "mrr": st.column_config.NumberColumn("MRR", format="$%.2f"),
        "status_today": st.column_config.TextColumn("Status today", help="Current status. History is decided by dates, not status."),
    },
)
st.caption(f"Total: {money(by_account['mrr'].sum())} (matches the MRR tile)")

with st.expander("Monthly table"):
    st.dataframe(monthly.drop(columns=["month"]), hide_index=True, width="stretch")


# --- Data quality --------------------------------------------------------------

st.subheader("Data quality: usage_daily")
dq = query(metrics.USAGE_DQ)
if dq.empty:
    st.success("All usage_daily rows pass the section 7 rules.")
else:
    st.warning(f"{len(dq)} usage_daily rows break a data-quality rule. They are reported, not fixed; "
               "usage metrics are not shown until they are resolved at the source.")
    st.dataframe(dq, hide_index=True, width="stretch")


# --- How it's computed -------------------------------------------------------

with st.expander("How these numbers are computed"):
    st.markdown(
        "- **Month-end snapshot:** a subscription counts in month M if it was live on M's last day "
        "(`started_on <= day` and `ended_on` empty or `>= day`). Dates decide, not today's status.\n"
        "- **Annual contracts** count at `amount / 12`.\n"
        "- **Trials** are excluded from MRR and paying customers.\n"
        "- **Internal demo accounts** (`is_internal = true`) are excluded everywhere.\n"
        "- **Cash** is the tax-inclusive `total_amount` of `paid` invoices only.\n\n"
        "Source of truth: `docs/semantic-layer.md`. All SQL lives in `dashboard/metrics.py`."
    )
    st.code(metrics.MONTHLY.strip(), language="sql")
