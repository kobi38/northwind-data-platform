# Northwind Cloud: Semantic Layer

The single source of truth for what the numbers in the Northwind Cloud database
**mean**. The schema tells you what columns exist. This document tells you the
business decisions behind every metric.

If a question can't be answered with the definitions below, say so and
state the assumption you're making. Don't invent a new definition silently.

---

## 1. The business in one paragraph

Northwind Cloud sells a B2B SaaS product on three plans (Starter, Business,
Enterprise), billed **monthly or annually**. Customers are organizations
(`accounts`). Each contract period is a row in `subscriptions`. Customers
negotiate, so the price actually paid is on the subscription, **not** the plan
catalog. New customers can start on a free **trial**. The company also runs
**internal demo tenants** that look like customers but aren't.

Data currently covers **January to March 2026**.

---

## 2. Tables, grain and keys

| Table | Grain (one row = …) | Primary business key | Notes |
|---|---|---|---|
| `accounts` | one customer organization | `account_code` | `is_internal = true` marks demo/test tenants |
| `plans` | one catalog plan | `plan_code` | `list_price_monthly` is the **rack rate**, never revenue |
| `subscriptions` | one **contract term** of one account | `subscription_code` | An account can have **several** rows, in sequence (upgrade) or at the same time (add-on) |
| `invoices` | one billing document | `invoice_code` | `total_amount` **includes tax** |
| `usage_daily` | one account on one day (intended) | (`account_code`, `usage_date`) | Not enforced by a constraint, and **no foreign key** to `accounts` |

### Join keys, always on the `*_code` columns

```
accounts.account_code        = subscriptions.account_code
plans.plan_code              = subscriptions.plan_code
subscriptions.subscription_code = invoices.subscription_code
accounts.account_code        = usage_daily.account_code   -- no FK: may not match
```

The `*_id` columns are surrogate identity keys. Nothing references them, so
never join on them.

To reach the account from an invoice, go **through** `subscriptions`:
`invoices → subscriptions → accounts`. Invoices don't carry an `account_code`.

### Tables that are NOT part of Northwind

`d_ent`, `d_sku`, `f_doc`, `f_doc_ln` are leftovers from an earlier training
exercise in the same Supabase project. They aren't Northwind data. **Never use
them** in any Northwind metric.

---

## 3. Vocabulary

### `subscriptions.status`: the **current** state of the term

| Status | Meaning | Paying? | Counts toward MRR while the term is live? |
|---|---|---|---|
| `trial` | Free evaluation, not yet converted | No | **No** |
| `active` | Live, paid contract | Yes | **Yes** |
| `past_due` | Live contract whose latest payment is failing | Yes (contractually) | **Yes**: the contract is still in force. A collection problem isn't churn. |
| `cancelled` | Term closed, e.g. replaced by an upgrade | n/a | Only for dates **before** its `ended_on` |
| `churned` | Customer left | n/a | Only for dates **before** its `ended_on` |

### `subscriptions.billing_interval`

| Value | `amount` means |
|---|---|
| `monthly` | price for one month |
| `annual` | price for **one full year**. Divide by 12 for monthly figures. |

### `invoices.payment_status`

| Value | Meaning | Is it cash we kept? |
|---|---|---|
| `paid` | Customer paid | **Yes** |
| `open` | Issued, not paid yet | No |
| `refunded` | Was paid, money returned | **No** |
| `void` | Cancelled document, never owed | No |

### Dates
- `started_on`: first day of the term (inclusive).
- `ended_on`: **last day of the term (inclusive)**. `NULL` = still open.
  Evidence: Cobalt's Starter term ends `2026-02-14` and its Business term starts
  `2026-02-15`, with no gap and no overlap.

---

## 4. Universal filters (apply to every customer or revenue metric)

1. **Exclude internal accounts:** `accounts.is_internal = false`. Internal demo
   tenants carry large contracts that would dwarf real revenue.
2. **Exclude trials** from revenue and paying-customer metrics: `status <> 'trial'`.
3. **Use the subscription's `amount`**, never `plans.list_price_monthly`.
4. **Never mix currencies** in one sum. All data is currently USD. If a
   non-USD row appears, report per currency.

---

## 5. Metric definitions

### "In month M" means *as of the last day of M*

Every point-in-time metric (MRR, paying customers, trials) is a **month-end
snapshot**. A subscription is **live at date D** when:

```sql
started_on <= D and (ended_on is null or ended_on >= D)
```

Use the **dates** to decide whether a term was live, not the status. `status`
is the *current* state only. There's no status history. A term that is
`churned` today was a paying contract on every day before its `ended_on`.

Why month-end: when an account upgrades mid-month, the old and new terms both
"overlap" the month. Summing every overlapping term would count that customer
twice. A snapshot counts exactly one.

### MRR: Monthly Recurring Revenue

> The monthly-normalized contracted price of every live, non-trial,
> non-internal subscription at month end.

- Monthly-normalized amount: `amount` if `monthly`, `amount / 12` if `annual`.
- Statuses that count: any non-trial term **live at the snapshot date**. In
  practice for a current or recent month that's `active` and `past_due`.
- Pre-tax: `subscriptions.amount` is already pre-tax.
- Not MRR: invoices, cash, list prices, trials, internal accounts.
- **Account-level MRR** (e.g. "Vertex Logistics' MRR") is the same formula
  filtered to that account's subscriptions. It sums **all** of that account's
  live terms.

```sql
-- MRR as of :month_end (e.g. date '2026-02-28')
select round(sum(case s.billing_interval
                   when 'annual'  then s.amount / 12
                   when 'monthly' then s.amount
                 end), 2) as mrr
from subscriptions s
join accounts a on a.account_code = s.account_code
where a.is_internal = false
  and s.status <> 'trial'
  and s.started_on <= :month_end
  and (s.ended_on is null or s.ended_on >= :month_end);
```

**ARR** = MRR × 12.

#### Worked example: February 2026 (snapshot 2026-02-28)

| Subscription | Account | Why | MRR |
|---|---|---|---|
| SUB-7001 | Vertex Logistics | annual 9600 / 12 | 800.00 |
| SUB-7002 | Brightpath Health | monthly | 180.00 |
| SUB-7003 | Nordwind Analytik | monthly | 170.00 |
| SUB-7005 | Cobalt Studio | Business term started Feb 15 | 199.00 |
| SUB-7006 | Harbor Freight Co | `churned` **now**, but live through Feb 28 | 190.00 |
| ~~SUB-7004~~ | Cobalt Studio | ended Feb 14, replaced by SUB-7005 | - |
| ~~SUB-7007/7008~~ | Lumen, Sable | trials | - |
| ~~SUB-7009~~ | Northwind Demo | internal | - |
| ~~SUB-7010~~ | Brightpath Health | starts Mar 1 | - |
| | | **February MRR** | **1539.00** |

The trap this example shows: filtering on `status in ('active','past_due')`
would drop SUB-7006 and understate February. Use dates for history.

### Paying customers

> The number of **distinct accounts** with at least one subscription that
> contributes to MRR at month end.

Count **accounts, not subscription rows**. One customer can hold several live
contracts (Brightpath Health does). An account whose only live subscription
is `past_due` still counts, because the contract is in force.

```sql
select count(distinct s.account_code) as paying_customers
from subscriptions s
join accounts a on a.account_code = s.account_code
where a.is_internal = false
  and s.status <> 'trial'
  and s.started_on <= :month_end
  and (s.ended_on is null or s.ended_on >= :month_end);
```

### Accounts on trial

> The number of **distinct non-internal accounts** with a `trial` subscription
> live at month end.

```sql
select count(distinct s.account_code) as trial_accounts
from subscriptions s
join accounts a on a.account_code = s.account_code
where a.is_internal = false
  and s.status = 'trial'
  and s.started_on <= :month_end
  and (s.ended_on is null or s.ended_on >= :month_end);
```

Trials are **never** paying customers and never in MRR, even though trial rows
carry an `amount` (that's the price they'll pay *if* they convert).

### Cash collected

> Money actually received and kept: the sum of `total_amount` on **`paid`**
> invoices dated in the period, excluding internal accounts.

- **Includes tax.** Cash collected is what landed in the bank, and
  `total_amount` is what the customer paid (net amount + tax).
- **Only `paid`.** `refunded` money went back, `void` was never owed, and `open`
  hasn't arrived yet.
- **Dated by `invoice_date`.** There's no separate payment-date column, so
  `invoice_date` stands in for the collection date.
- **Different from MRR timing.** An annual contract is billed once, so cash
  arrives as one lump in its invoice month while MRR spreads it at 1/12.

```sql
-- cash collected between :start and :end inclusive (Q1 = 2026-01-01..2026-03-31)
select round(sum(i.total_amount), 2) as cash_collected
from invoices i
join subscriptions s on s.subscription_code = i.subscription_code
join accounts a      on a.account_code      = s.account_code
where a.is_internal = false
  and i.payment_status = 'paid'
  and i.invoice_date between :start and :end;
```

### Billed revenue, net of tax (for completeness)

`sum(total_amount - tax_amount)` on `paid` invoices with the same filters.
Use it **only** when someone explicitly asks for revenue excluding tax. "Cash"
and "collected" always mean the tax-inclusive figure above.

---

## 6. Gotchas

1. **Annual `amount` is a year, not a month.** Summing `amount` directly
   inflates MRR by 12× for annual contracts.
2. **Internal accounts are huge.** The demo tenant has the biggest contract in
   the database. Forgetting `is_internal = false` silently breaks every number.
3. **`status` has no history.** Use `started_on` / `ended_on` for any past date.
4. **Count customers by account.** `count(*)` on subscriptions over-counts
   accounts with several contracts.
5. **Upgrades create a new row.** The old term is `cancelled` with `ended_on` the
   day before the new term starts. Mid-month, both overlap the month, which is
   why metrics use a month-end snapshot.
6. **`past_due` is still a customer.** Payment failing ≠ contract ended.
7. **`total_amount` includes tax.** `tax_amount` is the tax part. `total_amount
   - tax_amount` equals the subscription `amount` for a normal invoice.
8. **`void` invoices can be adjustments.** Their amounts don't match any
   contract price. Never include them.
9. **Refunded ≠ paid.** A refund means the cash came back. Exclude it entirely
   rather than netting.
10. **`list_price_monthly` is not revenue.** Real prices are negotiated below it.
11. **`usage_daily` isn't validated.** It may contain negative seats, missing
    dates or seat counts, and account codes that don't exist in `accounts`.
    Filter or flag these before using it in any metric (see §7).
12. **Four tables in the database aren't Northwind** (`d_ent`, `d_sku`,
    `f_doc`, `f_doc_ln`). Ignore them.
13. **Data ends in March 2026.** For "current" or "this month" questions about
    later dates, say that the data stops at March 2026 rather than presenting
    a stale snapshot as today's number.

---

## 7. Data-quality rules for `usage_daily`

A row is **valid** only if all of these hold:

| Rule | Check |
|---|---|
| Date present | `usage_date is not null` |
| Seat count present | `active_seats is not null` |
| Seat count non-negative | `active_seats >= 0` |
| Known account | `account_code` exists in `accounts` |
| One row per account per day | no duplicate (`account_code`, `usage_date`) |

The scheduled data-quality check (`scripts/`) applies exactly these rules and
fails if any row breaks one. Invalid rows are **reported, never fixed by hand**.

---

## 8. Glossary

| Term | Definition |
|---|---|
| **Account / customer** | An organization in `accounts`. "Customer" alone means a non-internal account. |
| **Paying customer** | A non-internal account with ≥1 live non-trial subscription at the snapshot date (§5). |
| **Trial account** | A non-internal account with a live `trial` subscription. |
| **Internal account** | `is_internal = true`: demo or test tenant. Excluded everywhere. |
| **Live (term)** | `started_on <= D` and `ended_on` is null or `>= D`. |
| **MRR** | Monthly Recurring Revenue: monthly-normalized contract value of live, non-trial, non-internal subscriptions at month end. Synonyms: "monthly recurring revenue", "recurring revenue run-rate (monthly)". |
| **ARR** | MRR × 12. |
| **Cash collected** | Tax-inclusive `total_amount` of `paid` invoices in the period, non-internal. |
| **Churn** | A term that ended with status `churned`: the customer left. |
| **Upgrade** | An old term `cancelled` and a new term started for the same account. Not churn. |
| **Rack / list price** | `plans.list_price_monthly`. Reference only. |
| **Snapshot date** | The day a point-in-time metric is measured: the last day of the month asked about. |

---

## 9. How to answer a business question

1. Map the question to a metric in §5. If none fits, say so.
2. Apply every universal filter in §4.
3. Use the canonical SQL, changing only the parameters.
4. Answer with the number, then a short breakdown and the definition you used.
5. If the question is genuinely ambiguous, give the defined answer and name the
   alternative. Don't silently pick a different definition.
