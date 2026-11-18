-- ============================================================================
--  Agentic Data Analysis - FINAL PROJECT practice database
--  "Northwind Cloud"  (run this in Supabase SQL Editor)
--
--  Domain: a B2B SaaS subscription business.
-- ----------------------------------------------------------------------------
--  Unlike the obfuscated practice database used in class, this schema is
--  READABLE. Tables and columns say what they mean. That is deliberate: the
--  final project is not a puzzle about decoding column names - it is about
--  building a working platform on top of a database you understand.
--
--  What still needs a semantic layer here is the part no schema can tell you:
--  the BUSINESS DEFINITIONS. The tables say `amount` and `billing_interval`;
--  they do not say that MRR normalizes annual contracts to a month, that
--  trials are excluded, or that internal accounts never appear in a customer
--  number. Those are decisions, and decisions are what you are documenting.
--
--  Five tables:
--     accounts       - customer organizations
--     plans          - the plan catalog
--     subscriptions  - one row per subscription term
--     invoices       - billing documents
--     usage_daily    - daily active-seat counts (for the data-quality check)
-- ============================================================================

-- Clean slate (safe to re-run) ------------------------------------------------
drop table if exists usage_daily   cascade;
drop table if exists invoices      cascade;
drop table if exists subscriptions cascade;
drop table if exists plans         cascade;
drop table if exists accounts      cascade;

-- ----------------------------------------------------------------------------
--  accounts - customer organizations
--    is_internal - true for demo/test tenants. Real reporting excludes these.
-- ----------------------------------------------------------------------------
create table accounts (
  account_id   bigint generated always as identity primary key,
  account_code text unique not null,
  company_name text not null,
  signup_date  date not null,
  region       text not null,
  is_internal  boolean not null default false
);

-- ----------------------------------------------------------------------------
--  plans - the plan catalog
--    list_price_monthly - the rack rate. Customers often negotiate below it,
--                         so the real price lives on the subscription.
-- ----------------------------------------------------------------------------
create table plans (
  plan_id            bigint generated always as identity primary key,
  plan_code          text unique not null,
  plan_name          text not null,
  list_price_monthly numeric(12,2) not null,
  included_seats     integer not null
);

-- ----------------------------------------------------------------------------
--  subscriptions - one row per subscription term
--    status            - 'trial', 'active', 'past_due', 'cancelled', 'churned'
--    billing_interval  - 'monthly' or 'annual'
--    amount            - the contracted price for ONE billing interval, pre-tax.
--                        On an annual term this is a full year.
--    ended_on          - NULL means the term is still open.
-- ----------------------------------------------------------------------------
create table subscriptions (
  subscription_id   bigint generated always as identity primary key,
  subscription_code text unique not null,
  account_code      text not null references accounts(account_code),
  plan_code         text not null references plans(plan_code),
  started_on        date not null,
  ended_on          date,
  status            text not null,
  billing_interval  text not null,
  amount            numeric(12,2) not null,
  currency          text not null default 'USD'
);

-- ----------------------------------------------------------------------------
--  invoices - billing documents
--    total_amount   - amount billed, INCLUDING tax.
--    payment_status - 'open', 'paid', 'refunded', 'void'
-- ----------------------------------------------------------------------------
create table invoices (
  invoice_id        bigint generated always as identity primary key,
  invoice_code      text unique not null,
  subscription_code text not null references subscriptions(subscription_code),
  invoice_date      date not null,
  total_amount      numeric(12,2) not null,
  tax_amount        numeric(12,2) not null,
  payment_status    text not null,
  currency          text not null default 'USD'
);

-- ----------------------------------------------------------------------------
--  usage_daily - daily active seats per account
--    Deliberately contains a few dirty rows. Your scheduled data-quality
--    check is what finds them - do not clean them by hand.
-- ----------------------------------------------------------------------------
create table usage_daily (
  usage_id     bigint generated always as identity primary key,
  account_code text not null,
  usage_date   date,
  active_seats integer
);

-- ============================================================================
--  Seed data
-- ============================================================================

insert into accounts (account_code, company_name, signup_date, region, is_internal) values
  ('ACC-1001', 'Vertex Logistics',  '2025-01-14', 'US', false),
  ('ACC-1002', 'Brightpath Health', '2025-03-22', 'US', false),
  ('ACC-1003', 'Nordwind Analytik', '2025-06-08', 'DE', false),
  ('ACC-1004', 'Cobalt Studio',     '2025-09-30', 'US', false),
  ('ACC-1005', 'Harbor Freight Co', '2025-11-17', 'US', false),
  ('ACC-1006', 'Lumen Robotics',    '2026-01-06', 'US', false),
  ('ACC-1007', 'Sable Media',       '2026-01-20', 'US', false),
  ('ACC-9900', 'Northwind Demo',    '2025-01-02', 'US', true);

insert into plans (plan_code, plan_name, list_price_monthly, included_seats) values
  ('STARTER',    'Starter',     49.00,   5),
  ('BUSINESS',   'Business',   199.00,  25),
  ('ENTERPRISE', 'Enterprise', 899.00, 250);

insert into subscriptions
  (subscription_code, account_code, plan_code, started_on, ended_on, status, billing_interval, amount, currency) values
  -- Annual enterprise contract: amount is a full year (9600 / 12 = 800 per month)
  ('SUB-7001', 'ACC-1001', 'ENTERPRISE', '2026-01-01', null,         'active',    'annual',  9600.00, 'USD'),
  ('SUB-7002', 'ACC-1002', 'BUSINESS',   '2026-01-01', null,         'active',    'monthly',  180.00, 'USD'),
  ('SUB-7003', 'ACC-1003', 'BUSINESS',   '2026-01-01', null,         'active',    'monthly',  170.00, 'USD'),
  -- Cobalt Studio upgraded on Feb 15: the starter term closed, a business term opened
  ('SUB-7004', 'ACC-1004', 'STARTER',    '2026-01-01', '2026-02-14', 'cancelled', 'monthly',   49.00, 'USD'),
  ('SUB-7005', 'ACC-1004', 'BUSINESS',   '2026-02-15', null,         'active',    'monthly',  199.00, 'USD'),
  -- Churned at the end of February
  ('SUB-7006', 'ACC-1005', 'BUSINESS',   '2026-01-01', '2026-02-28', 'churned',   'monthly',  190.00, 'USD'),
  -- Two accounts on trial: they are not paying yet
  ('SUB-7007', 'ACC-1006', 'BUSINESS',   '2026-02-01', null,         'trial',     'monthly',  199.00, 'USD'),
  ('SUB-7008', 'ACC-1007', 'STARTER',    '2026-02-10', null,         'trial',     'monthly',   49.00, 'USD'),
  -- Internal demo tenant
  ('SUB-7009', 'ACC-9900', 'ENTERPRISE', '2026-01-01', null,         'active',    'annual', 24000.00, 'USD'),
  -- Payment is failing, but the contract is still live
  ('SUB-7010', 'ACC-1002', 'STARTER',    '2026-03-01', null,         'past_due',  'monthly',   45.00, 'USD');

insert into invoices
  (invoice_code, subscription_code, invoice_date, total_amount, tax_amount, payment_status, currency) values
  ('INV-3001', 'SUB-7001', '2026-01-01', 11232.00, 1632.00, 'paid',     'USD'),
  ('INV-3002', 'SUB-7002', '2026-01-01',   210.60,   30.60, 'paid',     'USD'),
  ('INV-3003', 'SUB-7002', '2026-02-01',   210.60,   30.60, 'paid',     'USD'),
  ('INV-3004', 'SUB-7002', '2026-03-01',   210.60,   30.60, 'paid',     'USD'),
  ('INV-3005', 'SUB-7003', '2026-01-01',   198.90,   28.90, 'paid',     'USD'),
  ('INV-3006', 'SUB-7003', '2026-02-01',   198.90,   28.90, 'paid',     'USD'),
  ('INV-3007', 'SUB-7003', '2026-03-01',   198.90,   28.90, 'paid',     'USD'),
  ('INV-3008', 'SUB-7004', '2026-01-01',    57.33,    8.33, 'paid',     'USD'),
  ('INV-3009', 'SUB-7004', '2026-02-01',    57.33,    8.33, 'refunded', 'USD'),
  ('INV-3010', 'SUB-7005', '2026-02-15',   232.83,   33.83, 'paid',     'USD'),
  ('INV-3011', 'SUB-7005', '2026-03-15',   232.83,   33.83, 'paid',     'USD'),
  ('INV-3012', 'SUB-7006', '2026-01-01',   222.30,   32.30, 'paid',     'USD'),
  ('INV-3013', 'SUB-7006', '2026-02-01',   222.30,   32.30, 'paid',     'USD'),
  ('INV-3014', 'SUB-7009', '2026-01-01', 28080.00, 4080.00, 'paid',     'USD'),
  ('INV-3015', 'SUB-7010', '2026-03-01',    52.65,    7.65, 'open',     'USD'),
  ('INV-3016', 'SUB-7001', '2026-03-20',   500.00,   72.65, 'void',     'USD');

-- Usage data - clean rows first ----------------------------------------------
insert into usage_daily (account_code, usage_date, active_seats) values
  ('ACC-1001', '2026-03-01', 210), ('ACC-1001', '2026-03-02', 214),
  ('ACC-1001', '2026-03-03', 208), ('ACC-1002', '2026-03-01',  22),
  ('ACC-1002', '2026-03-02',  24), ('ACC-1002', '2026-03-03',  21),
  ('ACC-1003', '2026-03-01',  18), ('ACC-1003', '2026-03-02',  19),
  ('ACC-1004', '2026-03-01',  12), ('ACC-1004', '2026-03-02',  14),
  ('ACC-1006', '2026-03-01',   6), ('ACC-1006', '2026-03-02',   7);

-- ...and the dirty rows your data-quality check is supposed to catch.
-- Four distinct problems, one row each. Leave them alone - the whole point is
-- that an unattended check finds them and fails the build.
insert into usage_daily (account_code, usage_date, active_seats) values
  ('ACC-1002', '2026-03-04',  -5),    -- negative seat count
  ('ACC-1003', null,           17),   -- missing date
  ('ACC-1004', '2026-03-05', null),   -- missing seat count
  ('ACC-9999', '2026-03-05',   40);   -- account_code not in accounts

-- ============================================================================
--  Instructor reference - the numbers a correct semantic layer produces
--  (these are the gold values in eval/golden.yaml)
--
--  MRR, March 2026 = sum of monthly-normalized amount over subscriptions that
--  are live that month, status in (active, past_due), excluding internal
--  accounts and trials:
--      SUB-7001  9600/12 = 800.00   (annual, normalized)
--      SUB-7002            180.00
--      SUB-7003            170.00
--      SUB-7005            199.00   (SUB-7004 closed Feb 14)
--      SUB-7010             45.00   (past_due is still a live contract)
--                       ---------
--                         1394.00
--
--  Paying customers, March 2026 = 4 distinct ACCOUNTS (Vertex, Brightpath,
--  Nordwind, Cobalt) across 5 live subscription rows - Brightpath holds two.
--  Accounts on trial, March 2026 = 2 (Lumen Robotics, Sable Media).
--  Cash collected Q1 2026 = 13428.09 - paid invoices only, excluding the
--  internal tenant and the refunded/open/void ones.
--  Data-quality issues in usage_daily = 4 (one each: negative seats, missing
--  date, missing seat count, unknown account_code).
-- ============================================================================
