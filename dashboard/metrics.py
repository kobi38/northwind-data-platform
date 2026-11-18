"""Northwind metrics for the dashboard: the semantic layer, in one place.

Every business rule the dashboard applies lives in this file, and each one is a
direct copy of docs/semantic-layer.md section 4 (universal filters) and section 5
(metric definitions). app.py only draws what these queries return; it never
filters, sums or normalizes anything itself.

If a definition changes, change the semantic layer first, then this file, then
check the numbers still match eval/results.yaml (see verify_dashboard_numbers in
docs/build-journal.md, step 10).
"""

# --- The rules, written once -------------------------------------------------

# Section 4.1: internal demo tenants are not customers.
NOT_INTERNAL = "a.is_internal = false"

# Section 3 / gotcha 1: an annual amount is a year, a monthly amount is a month.
MONTHLY_AMOUNT = """case s.billing_interval
                      when 'annual'  then s.amount / 12
                      when 'monthly' then s.amount
                    end"""

# Section 5: "in month M" means live on the last day of M. Dates decide, not status.
LIVE_AT_MONTH_END = "s.started_on <= m.month_end and (s.ended_on is null or s.ended_on >= m.month_end)"

# Section 4.2: trials are never revenue or paying customers.
PAYING = "s.status <> 'trial'"
TRIAL = "s.status = 'trial'"

# Section 5, cash collected: only paid invoices count; total_amount includes tax.
PAID = "i.payment_status = 'paid'"


# --- Queries -----------------------------------------------------------------

# The months the data covers, taken from the data itself (it ends March 2026).
DATA_MONTHS = """
select date_trunc('month', min(invoice_date))::date as first_month,
       date_trunc('month', max(invoice_date))::date as last_month
from invoices
"""

# One row per month: the month-end snapshot metrics plus that month's cash.
MONTHLY = f"""
with months as (
    select m::date                                    as month_start,
           (m + interval '1 month - 1 day')::date     as month_end
    from generate_series(%(first_month)s::date, %(last_month)s::date, interval '1 month') as m
),
subs as (
    select s.*, {MONTHLY_AMOUNT} as monthly_amount
    from subscriptions s
    join accounts a on a.account_code = s.account_code
    where {NOT_INTERNAL}
),
snapshot as (
    select m.month_end,
           coalesce(round(sum(s.monthly_amount) filter (where {PAYING}), 2), 0) as mrr,
           count(distinct s.account_code) filter (where {PAYING})              as paying_customers,
           count(distinct s.account_code) filter (where {TRIAL})               as trial_accounts
    from months m
    left join subs s on {LIVE_AT_MONTH_END}
    group by m.month_end
),
paid as (
    select i.invoice_date, i.total_amount, i.currency
    from invoices i
    join subscriptions s on s.subscription_code = i.subscription_code
    join accounts a      on a.account_code      = s.account_code
    where {NOT_INTERNAL} and {PAID}
),
cash as (
    select m.month_end,
           coalesce(round(sum(p.total_amount), 2), 0) as cash_collected
    from months m
    left join paid p on p.invoice_date between m.month_start and m.month_end
    group by m.month_end
)
select sn.month_end, sn.mrr, sn.mrr * 12 as arr,
       sn.paying_customers, sn.trial_accounts, c.cash_collected
from snapshot sn
join cash c using (month_end)
order by sn.month_end
"""

# MRR per account at one month end: which customers make up the headline number.
MRR_BY_ACCOUNT = f"""
with m as (select %(month_end)s::date as month_end)
select a.company_name                                   as account,
       string_agg(distinct p.plan_name, ', ')           as plans,
       string_agg(distinct s.billing_interval, ', ')    as billing,
       string_agg(distinct s.status, ', ')              as status_today,
       round(sum({MONTHLY_AMOUNT}), 2)                  as mrr
from m
join subscriptions s on {LIVE_AT_MONTH_END}
join accounts a      on a.account_code = s.account_code
join plans p         on p.plan_code    = s.plan_code
where {NOT_INTERNAL} and {PAYING}
group by a.company_name
order by mrr desc
"""

# Section 4.4: never mix currencies. The dashboard checks instead of assuming.
CURRENCIES = """
select distinct currency from subscriptions
union
select distinct currency from invoices
"""

# Section 7: usage_daily rows that break a data-quality rule. Read-only: the
# dashboard reports these, it never fixes them (see scripts/dq_check.py).
USAGE_DQ = """
select * from (
select u.usage_id, u.account_code, u.usage_date, u.active_seats,
       concat_ws('; ',
         case when u.usage_date   is null then 'date missing' end,
         case when u.active_seats is null then 'seat count missing' end,
         case when u.active_seats < 0     then 'negative seats' end,
         case when a.account_code is null then 'unknown account' end,
         case when count(*) over (partition by u.account_code, u.usage_date) > 1
              and u.usage_date is not null then 'duplicate account-day' end
       ) as problem
from usage_daily u
left join accounts a on a.account_code = u.account_code
) checked
where problem <> ''
order by usage_id
"""
