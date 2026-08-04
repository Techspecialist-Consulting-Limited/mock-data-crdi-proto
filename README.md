# ZDF Mock Data — Structure & Table Relationships

Mock dataset for the Zero-interest Development Fund (ZDF). **Each folder is a database. Each CSV inside it is a table.**

| Folder (database) | What it represents | Tables |
|---|---|---|
| `Lending/` | The fund's own loan book, end to end | 5 |
| `PFI Partner Portal/` | What partner financial institutions report back | 4 |
| `finance/` | Money in, money out, budget and treasury | 5 |
| `procurement/` | Buying goods and services | 8 |

Every figure is as at the **data as-of date: 2026-08-04**. Data covers **2024-08-01 → 2026-08-04**.

---

## How to read this document

- **PK** = primary key (the unique ID of a row in that table).
- **FK** = foreign key (a column that points at another table's PK).
- "One → many" means one row in the first table can have many matching rows in the second.
- **Derived** means the column is calculated from other tables, not invented. Don't edit it by hand — recalculate it.

---

# 1. `Lending/` — the fund's own loan book

One loan travels through five tables, in this order:

```
lending_beneficiaries   (the person / business)
        │  1 → many
lending_applications    (they apply for a loan)
        │  1 → 1   (only if status = Approved)
lending_approvals       (credit decision)
        │  1 → 1   (only if status = Disbursed)
lending_disbursements   (money leaves the fund)
        │  1 → many
lending_repayments      (the instalment schedule)
```

### Tables and keys

| Table | PK | FK → points to |
|---|---|---|
| `lending_beneficiaries` | `beneficiary_id` | — |
| `lending_applications` | `application_id` | `beneficiary_id` → beneficiaries · `pfi_id` → **`PFI Partner Portal/pfi_partners.partner_id`** |
| `lending_approvals` | `approval_id` | `application_id` → applications |
| `lending_disbursements` | `disbursement_id` | `approval_id` → approvals |
| `lending_repayments` | `repayment_id` | `disbursement_id` → disbursements |

### Rules that hold in the data

- A beneficiary can borrow more than once, but repeat loans are at least 120 days apart. `external_ref` is that person's outward-facing reference — one per beneficiary.
- `first_time_borrower_flag` is **True only on a beneficiary's very first application**. The product *First-Time Borrower Fund* is only ever used on a first loan.
- `state` and `sector` on an application always equal the beneficiary's own `state` and `sector`.
- An approval exists **only** for applications with `status = Approved`. Rejected applications carry a `decision_reason`; *Under Review* applications are recent (last 45 days) and have no reason yet.
- `amount_approved` is never more than `amount_requested` — about 1 in 5 loans is approved for a reduced amount.
- `lending_approvals.status` is `Disbursed` or `Lapsed`. Lapsed approvals have **no** disbursement row.
- A disbursement's `amount` always equals its approval's `amount_approved`.
- Dates always run forward: `submitted_date` < `approval_date` < `disbursement_date`.
- **`lending_repayments`** — every disbursement has a full instalment schedule (6, 9 or 12 monthly instalments depending on product).
  - `status` is one of `Paid`, `Paid Late`, `Partially Paid`, `Overdue`, `Defaulted`, `Scheduled` (future).
  - `days_overdue` is **derived**: for settled instalments it is `paid_date − due_date`; for still-outstanding ones it is `as-of date − due_date`; for future instalments it is 0.

---

# 2. `PFI Partner Portal/` — what partners report back

Partners (banks, microfinance banks, fintechs) file a monthly return listing the loans they issued that month.

```
pfi_partners            (38 partner institutions)
        │  1 → many
pfi_submissions         (one monthly return per partner per period)
        │  1 → many
pfi_portfolio_records   (one row per loan reported in that return)
        │
        └── borrower_ref → pfi_borrowers   (who the end borrower is)
```

### Tables and keys

| Table | PK | FK → points to |
|---|---|---|
| `pfi_partners` | `partner_id` | — |
| `pfi_submissions` | `submission_id` | `partner_id` → partners |
| `pfi_borrowers` | `borrower_ref` | `partner_id` → partners · `beneficiary_id` → **`Lending/lending_beneficiaries`** (blank for the partner's own borrowers) |
| `pfi_portfolio_records` | `record_id` | `submission_id` → submissions · `partner_id` → partners · `borrower_ref` → borrowers · `disbursement_id` → **`Lending/lending_disbursements`** (blank = partner's own money) |

### Rules that hold in the data

- One submission per partner per reporting period — never a duplicate.
- `record_count` on a submission is **derived**: it always equals the real number of `pfi_portfolio_records` rows for it.
- Every record's `disbursed_date` falls **inside** its submission's `reporting_period`. A return can only contain loans issued that month.
- `status` on a submission is **derived** from the dates:
  - `Submitted` — filed on or before `due_date`
  - `Late` — filed after `due_date`
  - `Overdue` — due date passed, still not filed (`submitted_date` blank)
  - `Not Due` — due date is in the future
- A record's `partner_id` always matches its submission's `partner_id`. (The old free-text `partner_ref` column is gone — it used to disagree with the submission.)
- A record's borrower always belongs to the partner reporting it.
- `repayment_status` / `arrears_days` are the **live status as at the as-of date**, not the status back in the reporting month. `Current` = 0 days, `In Arrears` = 1–90 days, `Defaulted` = over 90 days.
- `approved_limit` is the partner's ZDF exposure ceiling; `zdf_exposure` is **derived** (total ZDF money on-lent through them) and never exceeds the limit.

---

# 3. `finance/` — money in, money out

```
finance_funding_sources   (3 facilities the fund borrows from)
        │  1 → many
finance_drawdowns         (each time the fund draws on a facility)
        │
        └──> feeds finance_treasury_positions (daily cash & debt position)

finance_budget_lines      (what each department may spend, per year)
        │  1 → many
finance_payments          (every naira that leaves the fund)
        │
        ├── disbursement_id → Lending/lending_disbursements       (loan payout)
        └── invoice_id      → procurement/procurement_invoices    (supplier payment)
```

### Tables and keys

| Table | PK | FK → points to |
|---|---|---|
| `finance_funding_sources` | `source_id` | — |
| `finance_drawdowns` | `drawdown_id` | `source_id` → funding_sources |
| `finance_budget_lines` | `budget_id` | — |
| `finance_payments` | `payment_id` | `source_id` → funding_sources · `budget_id` → budget_lines · `disbursement_id` → **Lending** · `invoice_id` → **procurement** |
| `finance_treasury_positions` | `position_id` (one row per day) | — (all figures derived) |

### Rules that hold in the data

- **Every payment is attributable.** `payment_type` is either `Loan Disbursement` or `Vendor Payment`, and each payment carries **exactly one** of `disbursement_id` or `invoice_id`. There are no orphan payments any more.
- Every payment also carries a `source_id` (which facility funded it) and a `budget_id` (which budget line absorbs it).
- Every disbursement has exactly one payment, and every invoice has exactly one payment — matching amounts, and never dated before the thing they pay for.
- `funding_sources.drawn` is **derived** = the sum of that source's drawdowns. `available` = `facility_amount − drawn`. Drawn never exceeds the facility.
- **`finance_treasury_positions`** is a daily snapshot, entirely derived:
  - `facility_drawn` = cumulative drawdowns up to that date — so it only ever rises.
  - `cash_balance` = drawdowns + repayments received − payments made. It never goes negative.
  - `committed_funds` = approved-but-not-yet-disbursed loans + awarded-but-not-yet-invoiced contracts, as at that date.
  - `cost_of_funds` = the interest rate across drawn balances, weighted by how much is drawn from each facility.
- **`finance_budget_lines`** — `budget_id` reads `BGT-{year}-{department}-{category}`, e.g. `BGT-2025-LEN-CCA`.
  - `actual` = **derived** sum of posted payments on that line.
  - `committed` = actual + payments awaiting clearance + open procurement commitments.
  - `budgeted_amount ≥ committed ≥ actual` always. `utilisation_pct` = actual ÷ budgeted.
  - Only *Lending Operations* has a `Credit Capital Allocation` line; every department has `OpEx`, `CapEx` and `Professional Fees`.

> **Note on scale:** budgeted (~₦155bn) is far larger than the facilities drawn (~₦37bn) because the fund **revolves** — repayments (~₦94bn received) are lent out again. Budget measures gross annual flow; the facilities measure net external borrowing.

---

# 4. `procurement/` — buying goods and services

```
procurement_requisitions   (a department asks to buy something)
        │  1 → many
procurement_bids           (vendors quote)
        │  the winning bid ↓
procurement_awards         (contract awarded)
        │  1 → 1
procurement_contracts      (the signed contract)
        ├── 1 → many  procurement_contract_variations  (scope / price changes)
        └── 1 → many  procurement_invoices  ──> paid by finance_payments

procurement_vendors        (150 suppliers)
        └── 1 → many  procurement_compliance_documents  (tax, CAC, PENCOM, ITF)
```

### Tables and keys

| Table | PK | FK → points to |
|---|---|---|
| `procurement_vendors` | `vendor_id` | — |
| `procurement_compliance_documents` | `document_id` | `vendor_id` → vendors |
| `procurement_requisitions` | `requisition_id` | `budget_id` → **`finance/finance_budget_lines`** |
| `procurement_bids` | `bid_id` | `requisition_id` → requisitions · `vendor_id` → vendors |
| `procurement_awards` | `award_id` | `requisition_id` → requisitions · `bid_id` → bids · `vendor_id` → vendors |
| `procurement_contracts` | `contract_id` | `award_id` → awards · `vendor_id` → vendors |
| `procurement_contract_variations` | `variation_id` | `contract_id` → contracts |
| `procurement_invoices` | `invoice_id` | `contract_id` → contracts · `requisition_id` → requisitions · `vendor_id` → vendors |

### Rules that hold in the data

- **One shared category list** is used by both vendors and requisitions: *IT Hardware & Infrastructure, Software & Licenses, Office Supplies & Printing, Field Survey & Logistics, Media PR & Professional Services*. A vendor can only bid in its own category.
- Every requisition points at the `budget_id` that will fund it — so procurement spend is under budget control.
- `procurement_awards.bid_id` names **the actual winning bid**. `awarded_value` always equals that bid's amount, and the winner was always marked responsive.
- `award_justification` is **derived from the facts**: `Lowest Responsive Bid` when the winner really was cheapest; `Lowest Bidder Non-Compliant at Award` when the cheapest bidder's certificates had lapsed; otherwise a stated discretionary reason.
- **Compliance gate:** a vendor can only bid, and only be awarded, on dates when all four of its compliance documents were valid. `vendors.status` is **derived** — `Active` if all documents are valid today, `Suspended` if any has expired. `documents.status` is `Valid` / `Expired` against the as-of date.
- Requisition `status` is `Awarded`, `Bidding` or `Cancelled`. Awarded → exactly one award and one contract. Cancelled → no award, and a `cancellation_reason` is always given.
- `contract_value` is **derived** = `awarded_value` + all variation amounts. `variations` is the **count** of variation rows; `variation_value` is their total.
- Invoices never exceed `contract_value`. `Completed` contracts are fully invoiced; `Not Started` contracts have none.

---

# 5. Cross-database connections

These four links tie the databases into one system.

| # | Link | Meaning |
|---|---|---|
| **X1** | `Lending/lending_applications.pfi_id` → `PFI Partner Portal/pfi_partners.partner_id` | Which partner institution originated the loan |
| **X2** | `finance/finance_payments.disbursement_id` → `Lending/lending_disbursements.disbursement_id` | The cash movement behind each loan payout |
| **X3** | `finance/finance_payments.invoice_id` → `procurement/procurement_invoices.invoice_id` | The cash movement behind each supplier bill |
| **X4** | `PFI Partner Portal/pfi_portfolio_records.disbursement_id` → `Lending/lending_disbursements.disbursement_id` | **The reconciliation link** (see below) |
| **X5** | `procurement/procurement_requisitions.budget_id` → `finance/finance_budget_lines.budget_id` | Budget control over procurement |
| **X6** | `PFI Partner Portal/pfi_borrowers.beneficiary_id` → `Lending/lending_beneficiaries.beneficiary_id` | Same person, both sides of the pipe |

## The reconciliation link (X4) — what it lets you prove

Each row in `pfi_portfolio_records` is either ZDF money or the partner's own money, marked by `funding_source`:

- **`ZDF Facility`** — `disbursement_id` is filled in. There is **exactly one such record for every single ZDF disbursement**, with the same amount, the same date, the same partner, and the same underlying borrower. The ₦114.30bn the fund disbursed appears, naira for naira, in what partners reported.
- **`Partner Own Book`** — `disbursement_id` is blank. Loans the partner funded itself; ZDF has no exposure to these.

Because the link exists, `repayment_status` and `arrears_days` on a ZDF-funded record are **derived from `lending_repayments`** — the portal and the loan book can never tell two different stories about the same loan.

## The full money trail, in one line

```
finance_funding_sources → finance_drawdowns → finance_payments
   → lending_disbursements → pfi_portfolio_records (partner on-lends)
   → lending_repayments (money comes back) → finance_treasury_positions
```

---

# 6. Reference figures (as at 2026-08-04)

| Measure | Value |
|---|---|
| Applications received | 38,874 (31,150 approved · 6,380 rejected · 1,344 under review) |
| Loans disbursed | 30,742 · **₦114.30bn** |
| Repayments received | **₦93.70bn** |
| Facilities | ₦55.00bn total · **₦37.00bn drawn** · ₦18.00bn available |
| Total payments out | **₦124.20bn** (30,742 loan payouts + 986 supplier payments) |
| Partner returns filed | 950 submissions from 38 partners over 25 months |
| Loans reported by partners | 238,869 (30,742 ZDF-funded · 208,127 partner own book) |
| Procurement awarded | 590 contracts · **₦12.49bn** |

---

# 7. Data cleaning applied

The whole dataset has been run through [clean_script.py](clean_script.py). It is **idempotent** — running it again produces byte-identical files — and it finishes by re-running all 130 relationship checks, **rolling back automatically if any of them break**. Cleaning is never allowed to damage the relationships in sections 1–5.

## What was cleaned

### 1. Money and rates given a consistent 2 decimal places
**714,159 cells across 23 columns.**

| Before | After |
|---|---|
| `3910000.0` | `3910000.00` |
| `93.7` | `93.70` |
| `30000000000.0` | `30000000000.00` |

**Why:** the same column mixed one and two decimals (`93.7` next to `36611000.00`). A tool reading the column has to guess the scale, and currency totals can drift by a kobo per row. One fixed width makes every amount unambiguous. Counts that are *not* money — `arrears_days`, `days_overdue`, `instalment_number`, `record_count`, `variations`, `fiscal_period` — were forced the other way, to whole numbers with no decimal point at all.

> Values were **re-rendered, not recalculated**. Any amount that rounding would have moved by more than half a kobo is reported instead of changed — nothing was silently altered.

### 2. Booleans written in lowercase
**42,346 cells across 2 columns** (`first_time_borrower_flag`, `responsive_flag`).

| Before | After |
|---|---|
| `True` | `true` |
| `False` | `false` |

**Why:** `True`/`False` is Python's spelling. Fabric, Spark and SQL engines don't recognise it, so they load the column as **text** — and in text, the string `"False"` is non-empty and therefore counts as *true* in a filter. That silently inverts logic like "show me the non-responsive bids". Lowercase `true`/`false` is parsed natively as a real boolean.

### 3. Doubled legal suffixes in company names collapsed
**16 vendor names.**

| Before | After |
|---|---|
| `Okafor Ltd Ltd` | `Okafor Ltd` |
| `Obasanjo LLC Ltd` | `Obasanjo Ltd` |
| `Eze Inc Nig. Ltd` | `Eze Nig. Ltd` |
| `Akinwale Inc Limited` | `Akinwale Limited` |
| `Adetokunbo Inc Nig. Ltd` | `Adetokunbo Nig. Ltd` |

**Why:** no company carries two legal forms at once. A name holding both reads as a data-entry error, and it breaks any name-based matching or search a user tries. The rule keeps only the **last** designator (`Ltd`, `Limited`, `LLC`, `Inc`, `PLC`); locality words like `Nig.` are left alone.

### 4. Names shared by two different entities made unique
**4 labels.**

| Before | After |
|---|---|
| `Okafor Ltd` on `PRC-VND-0088` | `Okafor Ltd (PRC-VND-0088)` |
| `Okafor Ltd` on `PRC-VND-0137` | `Okafor Ltd (PRC-VND-0137)` |
| `Oyekan Group Limited` on `PRC-VND-0123` | `Oyekan Group Limited (PRC-VND-0123)` |
| `Adetokunbo Ltd Bank` on `PFI-22` | `Adetokunbo Ltd Bank (PFI-22)` |

**Why:** these are genuinely different organisations that happened to share a label. Anyone grouping a report by name would silently merge two vendors into one and double their spend. The lowest ID keeps the original name; the others are tagged with their own ID so the label is unique but still readable.

> **Cascade:** `finance_payments.payee` stores these names as text. All **937** affected payment rows were updated too — resolved through the *foreign keys* (payment → invoice → vendor, and payment → disbursement → approval → application → partner), never by matching on the old name, because two vendors sharing a label would be impossible to tell apart that way.

### 5. Line endings and encoding standardised
**All 22 files** converted from Windows `CRLF` to `LF`, written as UTF-8 with no byte-order mark, `QUOTE_MINIMAL` quoting, and a trailing newline.

**Why:** a stray `\r` gets read as part of the last value on every row, so `Active` becomes `Active\r` and stops matching `Active`. A BOM does the same to the first column name in the header. LF + UTF-8 without BOM is what Fabric, Spark and pandas expect.

### 6. Blanks left as genuine blanks
**473,384 empty cells across 8 columns were deliberately left empty**, and sentinel strings (`NA`, `N/A`, `null`, `None`, `-`, `unknown`) are converted to empty if they ever appear.

**Why:** in this dataset blank *means something* — a blank `disbursement_id` on a portfolio record means "the partner funded this itself", and a blank `paid_date` means "this instalment hasn't been paid yet". Filling those with `0` or `"Unknown"` would invent facts. An empty cell reads as a proper NULL; the word `"None"` reads as text and quietly breaks both counts and joins.

## Checks that ran and found nothing

The script still performs these on every run, so they catch problems in any future load:

| Check | Found |
|---|---|
| Exact duplicate rows | 0 |
| Leading/trailing whitespace, doubled internal spaces | 0 |
| Blank rows | 0 |
| Ragged rows (wrong number of columns) | 0 |
| Byte-order marks | 0 |
| Header problems (casing, spaces, duplicates) | 0 |
| Category value drift (`Active` vs `active` vs `ACTIVE`) | 0 |
| Mixed date formats within one column | 0 |

## Re-running it

```bash
python clean_script.py                  # clean in place (git is the undo)
python clean_script.py --dry-run        # report what would change, write nothing
python clean_script.py --out ./clean    # write to a mirror folder instead
python clean_script.py --no-names       # skip the name cleanup (items 3 and 4)
```

Every run writes `clean_report.json` listing what changed, per file and per column. The row-level helpers (`clean_cell`, `normalise_number`, `collapse_designators`) are pure string functions with no imports or I/O, so they can be lifted straight into a Fabric dataflow step or a Spark UDF.

---

# 8. Working with this data

- **Join on IDs, never on names or free text.** Every relationship above is an ID column.
- **Derived columns must be recalculated, not typed.** Anything marked *derived* (`record_count`, `drawn`, `actual`, `contract_value`, `days_overdue`, `zdf_exposure`, the whole treasury table, vendor and submission `status`) will contradict its source table if you edit it directly.
- **Blank is meaningful.** A blank `disbursement_id`, `invoice_id`, `beneficiary_id`, `paid_date` or `submitted_date` means "not applicable / hasn't happened", not missing data.
- **Money** is in Nigerian naira (₦), always 2 decimal places. **Timestamps** are `YYYY-MM-DD HH:MM:SS`; **dates** are `YYYY-MM-DD`; `reporting_period` is `YYYY-MM`.
- **Booleans** are lowercase `true` / `false` — safe to load as a real boolean type.
- **Files** are UTF-8 without BOM, LF line endings.

## Scripts in this folder

| Script | What it does |
|---|---|
[clean_script.py](clean_script.py) | Cleans the dataset (section 7). Idempotent, validates, rolls back on failure. |
[_tools_verify_relationships.py](_tools_verify_relationships.py) | The 130 relationship and business-rule checks. Run it any time: `python _tools_verify_relationships.py` |
[_tools_rebuild_dataset.py](_tools_rebuild_dataset.py) | Regenerates the dataset from scratch. Run it only against the original source CSVs — feeding it its own output re-derives slightly different numbers. |
