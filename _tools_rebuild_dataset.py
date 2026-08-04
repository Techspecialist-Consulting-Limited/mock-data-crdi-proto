#!/usr/bin/env python
"""Rebuild the ZDF mock dataset with coherent, declared relationships.

Order matters: lending -> procurement -> invoices -> payments -> drawdowns
-> treasury -> budget -> PFI portal. Each stage only depends on earlier ones.
"""
import csv, os, math, random, collections
from datetime import datetime, timedelta, date

ROOT = r"c:\Users\SALE\Documents\TCL\Credi-corp\zdf_mock_data"
LEN = os.path.join(ROOT, "Lending")
PFI = os.path.join(ROOT, "PFI Partner Portal")
FIN = os.path.join(ROOT, "finance")
PRC = os.path.join(ROOT, "procurement")

ASOF = datetime(2026, 8, 4)
RNG = random.Random(20260804)

def load(path):
    with open(path, newline='', encoding='utf-8-sig') as f:
        return list(csv.DictReader(f))

def write(path, cols, rows):
    with open(path, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    print(f"  wrote {os.path.basename(path):45s} {len(rows):>7,} rows  ({len(cols)} cols)")

def ts(dt):  return dt.strftime('%Y-%m-%d %H:%M:%S')
def ds(dt):  return dt.strftime('%Y-%m-%d')
def pdt(s):  return datetime.strptime(s, '%Y-%m-%d %H:%M:%S')
def pd_(s):  return datetime.strptime(s, '%Y-%m-%d')
def money(x): return round(float(x), 2)
def add_months(d, n):
    y, m = divmod((d.year * 12 + d.month - 1) + n, 12)
    return d.replace(year=y, month=m + 1, day=min(d.day, 28))

DEPT_CODE = {'Lending Operations': 'LEN', 'IT & Infrastructure': 'ITI',
             'Procurement & Logistics': 'PRL', 'Executive Admin': 'EXA',
             'Risk & Compliance': 'RSC'}
CAT_CODE = {'Credit Capital Allocation': 'CCA', 'OpEx': 'OPX',
            'CapEx': 'CPX', 'Professional Fees': 'PFE'}

# One shared procurement category vocabulary, used by vendors AND requisitions.
PROC_CATS = ['IT Hardware & Infrastructure', 'Software & Licenses',
             'Office Supplies & Printing', 'Field Survey & Logistics',
             'Media, PR & Professional Services']
REQ_CAT_REMAP = {'Hardware Procurement': 'IT Hardware & Infrastructure',
                 'Software Licenses': 'Software & Licenses',
                 'Office Consumables': 'Office Supplies & Printing',
                 'Field Survey Services': 'Field Survey & Logistics',
                 'Media & PR': 'Media, PR & Professional Services'}
PROC_CAT_TO_BUDGET = {'IT Hardware & Infrastructure': 'CapEx',
                      'Software & Licenses': 'OpEx',
                      'Office Supplies & Printing': 'OpEx',
                      'Field Survey & Logistics': 'OpEx',
                      'Media, PR & Professional Services': 'Professional Fees'}

def budget_id(dept, cat, year):
    return f"BGT-{year}-{DEPT_CODE[dept]}-{CAT_CODE[cat]}"

# ===========================================================================
# 1. PFI PARTNERS  (needed early: lending applications reference partner_id)
# ===========================================================================
print("\n[1] PFI partners")
partners = load(os.path.join(PFI, 'pfi_partners.csv'))
PARTNER_SIZE = {'Commercial Bank': 420, 'Fintech Lender': 230, 'Microfinance Bank': 150}
for i, p in enumerate(partners):
    p['status'] = 'Probation' if i in (6, 18, 29, 33) else 'Active'
partner_by_id = {p['partner_id']: p for p in partners}
partner_ids = [p['partner_id'] for p in partners]

# ===========================================================================
# 2. LENDING: beneficiaries <- applications
# ===========================================================================
print("\n[2] Lending beneficiaries + applications")
bens = load(os.path.join(LEN, 'lending_beneficiaries.csv'))
apps = load(os.path.join(LEN, 'lending_applications.csv'))

# external_ref becomes a stable 1:1 alias of beneficiary_id (was the dangling
# applicant_ref on applications).
refs = RNG.sample(range(100000, 999999), len(bens))
for b, r in zip(bens, refs):
    b['external_ref'] = f"AP-{r}"
ben_cols = ['beneficiary_id', 'external_ref', 'state', 'sector', 'gender',
            'age_band', 'employment_category']
bens = [{k: b[k] for k in ben_cols} for b in bens]
ben_by_id = {b['beneficiary_id']: b for b in bens}

apps.sort(key=lambda a: a['submitted_date'])
ben_order = [b['beneficiary_id'] for b in bens]
RNG.shuffle(ben_order)

# First len(bens) applications each open a new borrower; the rest are repeat
# borrowings, only allowed >=120 days after that borrower's previous loan.
last_app = {}
fresh = list(ben_order)
eligible = collections.deque()          # (ready_dt, beneficiary_id) in ready order
assigned = []
for a in apps:
    d = pdt(a['submitted_date'])
    while eligible and eligible[0][0] <= d:
        fresh.append(eligible.popleft()[1])
    if not fresh:
        fresh.append(eligible.popleft()[1])
    bid = fresh.pop(0)
    first_time = bid not in last_app
    last_app[bid] = d
    eligible.append((d + timedelta(days=120), bid))
    assigned.append((a, bid, first_time))

REJECT_REASONS = ['Insufficient Repayment Capacity', 'Adverse Credit Bureau Record',
                  'Incomplete Documentation', 'Collateral Shortfall',
                  'Sector Exposure Cap Reached', 'Failed KYC Verification']
UR_CUTOFF = ASOF - timedelta(days=45)

app_rows = []
for a, bid, first_time in assigned:
    b = ben_by_id[bid]
    d = pdt(a['submitted_date'])
    if first_time:
        prods, wts = ['First-Time Borrower Fund', 'MSME Credit', 'Agri-Boost'], [60, 22, 18]
    else:
        prods, wts = ['MSME Credit', 'Agri-Boost'], [55, 45]
    if b['sector'] == 'Agriculture':                       # sector bias
        wts = [w * (3 if p == 'Agri-Boost' else 1) for p, w in zip(prods, wts)]
    product = RNG.choices(prods, weights=wts)[0]

    if d > UR_CUTOFF and RNG.random() < 0.70:
        status, reason = 'Under Review', ''
    elif RNG.random() < 0.17:
        status, reason = 'Rejected', RNG.choice(REJECT_REASONS)
    else:
        status, reason = 'Approved', 'Standard Credit Review Met'
    app_rows.append({
        'application_id': a['application_id'], 'beneficiary_id': bid,
        'pfi_id': a['pfi_id'], 'product': product,
        'amount_requested': money(a['amount_requested']),
        'state': b['state'], 'sector': b['sector'],
        'submitted_date': ts(d), 'status': status, 'decision_reason': reason,
        'first_time_borrower_flag': first_time})

app_rows.sort(key=lambda r: r['submitted_date'])
app_by_id = {r['application_id']: r for r in app_rows}

# ===========================================================================
# 3. LENDING: approvals -> disbursements -> repayments
# ===========================================================================
print("\n[3] Lending approvals / disbursements / repayments")
CONDITIONS = ['Standard Credit Review Met', 'Subject to Guarantor Confirmation',
              'Subject to Business Premises Verification',
              'Reduced Exposure Approved', 'Subject to Insurance Cover']
apr_rows, dsb_rows, rep_rows = [], [], []
apr_seq = collections.Counter(); dsb_seq = collections.Counter()

for a in app_rows:
    if a['status'] != 'Approved':
        continue
    sd = pdt(a['submitted_date'])
    ad = sd + timedelta(days=RNG.randint(2, 7), hours=RNG.randint(0, 6))
    if ad > ASOF:
        ad = sd + timedelta(days=2)
    req_amt = a['amount_requested']
    if RNG.random() < 0.22:                                # partial approvals
        amt = money(round(req_amt * RNG.uniform(0.60, 0.95) / 10000) * 10000)
        cond = 'Reduced Exposure Approved'
    else:
        amt, cond = req_amt, RNG.choices(CONDITIONS, weights=[62, 12, 12, 0, 14])[0]
    y = ad.year
    apr_seq[y] += 1
    aid = f"APR-{y}-{apr_seq[y]:06d}"
    lapsed = RNG.random() < 0.013
    apr_rows.append({'approval_id': aid, 'application_id': a['application_id'],
                     'amount_approved': amt, 'approved_by': f"OFFICER_{RNG.randint(1, 60):02d}",
                     'approval_date': ts(ad), 'conditions': cond,
                     'status': 'Lapsed' if lapsed else 'Disbursed'})
    if lapsed:
        continue
    dd = ad + timedelta(days=RNG.randint(1, 6), hours=RNG.randint(0, 8))
    if dd > ASOF:
        dd = ad + timedelta(days=1)
    dy = dd.year
    dsb_seq[dy] += 1
    did = f"DSB-{dy}-{dsb_seq[dy]:06d}"
    dsb_rows.append({'disbursement_id': did, 'approval_id': aid, 'amount': amt,
                     'disbursement_date': ts(dd),
                     'disbursement_reference': f"ZDF-DISB-{dy}-{dsb_seq[dy]:05d}",
                     'status': 'Disbursed'})

apr_by_id = {r['approval_id']: r for r in apr_rows}
TENOR = {'MSME Credit': 12, 'Agri-Boost': 6, 'First-Time Borrower Fund': 9}
RATE = {'MSME Credit': 0.14, 'Agri-Boost': 0.11, 'First-Time Borrower Fund': 0.09}
rep_seq = 0
disb_perf = {}                       # disbursement_id -> (status, arrears_days)

for d in dsb_rows:
    app = app_by_id[apr_by_id[d['approval_id']]['application_id']]
    n = TENOR[app['product']]
    dd = pdt(d['disbursement_date'])
    total = d['amount'] * (1 + RATE[app['product']] * n / 12)
    inst = money(round(total / n, 2))
    behaviour = RNG.choices(['current', 'arrears', 'default'], weights=[80, 16, 4])[0]
    # The breach instalment is chosen from the timeline, so days_overdue is always
    # derived (ASOF - due_date) and the resulting arrears bucket is never invented.
    TODAY = ASOF.date()
    dues = [add_months(dd.date(), i) for i in range(1, n + 1)]
    past = [i for i, u in enumerate(dues, 1) if u <= TODAY]
    breach = None
    if behaviour == 'arrears':
        cand = [i for i in past if (TODAY - dues[i - 1]).days <= 90]
        breach = min(cand) if cand else None
    elif behaviour == 'default':
        cand = [i for i in past if (TODAY - dues[i - 1]).days > 90]
        breach = min(cand) if cand else None
    if breach is None:
        behaviour = 'current'
    worst = worst_open = 0
    for i in range(1, n + 1):
        due = dues[i - 1]
        amount_due = money(total - inst * (n - 1)) if i == n else inst
        paid_amt, paid_dt, overdue, st = 0.0, '', 0, 'Scheduled'
        if due <= TODAY:
            if behaviour == 'current' or i < breach:
                late = RNG.random() < 0.10
                pdate = due + timedelta(days=RNG.randint(1, 12) if late else -RNG.randint(0, 4))
                pdate = min(pdate, TODAY)
                paid_amt, paid_dt = amount_due, ds(pdate)
                overdue = max(0, (pdate - due).days)
                st = 'Paid Late' if overdue > 0 else 'Paid'
            else:
                overdue = (TODAY - due).days
                st = 'Defaulted' if overdue > 90 else 'Overdue'
                worst_open = max(worst_open, overdue)
                if RNG.random() < 0.30:                    # part-payment against arrears
                    paid_amt = money(round(amount_due * RNG.uniform(0.2, 0.7), 2))
                    paid_dt = ds(min(due + timedelta(days=max(1, overdue // 2)), TODAY))
                    st = 'Partially Paid'
            worst = max(worst, overdue)
        rep_seq += 1
        rep_rows.append({'repayment_id': f"REP-{rep_seq:08d}",
                         'disbursement_id': d['disbursement_id'], 'instalment_number': i,
                         'amount_due': amount_due, 'amount_paid': money(paid_amt),
                         'due_date': ds(due), 'paid_date': paid_dt,
                         'days_overdue': overdue, 'status': st})
    # loan-level status = worst STILL-OUTSTANDING instalment; settled late payments
    # are history, not arrears.
    disb_perf[d['disbursement_id']] = (
        'Current' if worst_open == 0 else ('In Arrears' if worst_open <= 90 else 'Defaulted'),
        worst_open)

# ===========================================================================
# 4. PROCUREMENT: vendors, compliance, requisitions, bids, awards, contracts,
#    variations, invoices
# ===========================================================================
print("\n[4] Procurement")
vendors = load(os.path.join(PRC, 'procurement_vendors.csv'))
for i, v in enumerate(vendors):
    v['category'] = PROC_CATS[i % len(PROC_CATS)]

DOC_TYPES = ['CAC Registration', 'Tax Clearance Certificate', 'PENCOM Compliance',
             'ITF Certificate']
# Registration dates are spread so that every category has a deep pool of vendors
# already compliant when the earliest 2024 requisitions go to market.
REG_START = date(2023, 1, 10)
for i, v in enumerate(vendors):
    if i < 120:
        v['registration_date'] = ds(REG_START + timedelta(days=int(i * 535 / 120)))
    else:
        v['registration_date'] = ds(date(2024, 9, 1) + timedelta(days=int((i - 120) * 400 / 30)))

docs, doc_windows = [], collections.defaultdict(list)
dseq = 0
for i, v in enumerate(vendors):
    reg = pd_(v['registration_date'])
    lapse = (i % 8 == 3)                       # ~12.5% of vendors let a cert lapse
    for j, dt_ in enumerate(DOC_TYPES):
        issue = reg + timedelta(days=RNG.randint(3, 25))
        if lapse and j == 1:
            expiry = ASOF - timedelta(days=RNG.randint(20, 150))
        else:
            expiry = ASOF + timedelta(days=RNG.randint(90, 720))
        dseq += 1
        docs.append({'document_id': f"DOC-{dseq:06d}", 'vendor_id': v['vendor_id'],
                     'document_type': dt_, 'issue_date': ds(issue),
                     'expiry_date': ds(expiry),
                     'status': 'Valid' if expiry >= ASOF else 'Expired'})
        doc_windows[v['vendor_id']].append((issue, expiry))

def compliant_on(vid, when):
    return all(i <= when <= e for i, e in doc_windows[vid])

for v in vendors:
    v['status'] = 'Active' if compliant_on(v['vendor_id'], ASOF) else 'Suspended'
vendors_by_cat = collections.defaultdict(list)
for v in vendors:
    vendors_by_cat[v['category']].append(v)
vendor_by_id = {v['vendor_id']: v for v in vendors}

reqs = load(os.path.join(PRC, 'procurement_requisitions.csv'))
CANCEL_REASONS = ['Budget Withdrawn', 'Requirement Superseded',
                  'Insufficient Responsive Bids', 'Re-scoped for Re-tender']
for r in reqs:
    r['category'] = REQ_CAT_REMAP.get(r['category'], r['category'])
    rd = pd_(r['raised_date'])
    r['budget_id'] = budget_id(r['department'], PROC_CAT_TO_BUDGET[r['category']], rd.year)
    r['cancellation_reason'] = RNG.choice(CANCEL_REASONS) if r['status'] == 'Cancelled' else ''
    r['estimated_value'] = money(r['estimated_value'])
reqs.sort(key=lambda r: r['raised_date'])

JUSTIFY = ['Lowest Responsive Bid', 'Best Evaluated Bid - Technical Score',
           'Lowest Bidder Non-Compliant at Award', 'Delivery Timeline Advantage',
           'Prior Satisfactory Performance']
bids, awards, contracts, variations, invoices = [], [], [], [], []
bseq = collections.Counter(); aseq = collections.Counter(); iseq = 0

for r in reqs:
    if r['status'] == 'Cancelled':
        continue
    rd = pd_(r['raised_date'])
    bid_open = rd + timedelta(days=RNG.randint(7, 21))
    pool = [v for v in vendors_by_cat[r['category']] if compliant_on(v['vendor_id'], bid_open)]
    if not pool:
        r['status'] = 'Cancelled'
        r['cancellation_reason'] = 'Insufficient Responsive Bids'
        continue
    chosen = RNG.sample(pool, min(len(pool), RNG.randint(3, 6)))
    est = r['estimated_value']
    mine = []
    for v in chosen:
        amt = money(round(est * RNG.uniform(0.82, 1.12) / 1000) * 1000)
        bseq[rd.year] += 1
        bid = {'bid_id': f"BID-{rd.year}-{bseq[rd.year]:06d}", 'requisition_id': r['requisition_id'],
               'vendor_id': v['vendor_id'], 'bid_amount': amt,
               'submitted_date': ds(bid_open + timedelta(days=RNG.randint(0, 9))),
               'responsive_flag': RNG.random() < 0.82}
        bids.append(bid); mine.append(bid)
    if r['status'] != 'Awarded':
        continue
    ad = bid_open + timedelta(days=RNG.randint(8, 25))
    responsive = sorted([b for b in mine if b['responsive_flag']], key=lambda b: b['bid_amount'])
    eligible_b = [b for b in responsive if compliant_on(b['vendor_id'], ad)]
    if not eligible_b:                       # nobody left compliant at award -> no award
        r['status'] = 'Cancelled'
        r['cancellation_reason'] = 'Insufficient Responsive Bids'
        continue
    if len(eligible_b) > 1 and RNG.random() < 0.30:
        win = RNG.choice(eligible_b[1:])
    else:
        win = eligible_b[0]
    # justification is derived from the facts, not chosen at random
    if win['bid_amount'] == responsive[0]['bid_amount']:
        just = 'Lowest Responsive Bid'
    elif win is eligible_b[0]:
        just = 'Lowest Bidder Non-Compliant at Award'
    else:
        just = RNG.choice(['Best Evaluated Bid - Technical Score',
                           'Delivery Timeline Advantage', 'Prior Satisfactory Performance'])
    aseq[ad.year] += 1
    awd = {'award_id': f"AWD-{ad.year}-{aseq[ad.year]:05d}", 'requisition_id': r['requisition_id'],
           'bid_id': win['bid_id'], 'vendor_id': win['vendor_id'],
           'awarded_value': win['bid_amount'], 'award_date': ds(ad),
           'award_justification': just}
    awards.append(awd)

    start = ad + timedelta(days=RNG.randint(5, 20))
    end = start + timedelta(days=RNG.randint(90, 240))
    cid = f"CTR-{ad.year}-{aseq[ad.year]:05d}"
    var_rows, var_total = [], 0.0
    if RNG.random() < 0.18:
        for k in range(RNG.randint(1, 2)):
            v_amt = money(round(awd['awarded_value'] * RNG.uniform(0.03, 0.15) / 1000) * 1000)
            var_total += v_amt
            var_rows.append({'variation_id': f"VAR-{cid}-{k+1}", 'contract_id': cid,
                             'variation_date': ds(start + timedelta(days=RNG.randint(15, 120))),
                             'variation_amount': v_amt,
                             'reason': RNG.choice(['Scope Increase', 'Price Escalation',
                                                   'Timeline Extension', 'Additional Sites'])})
    variations += var_rows
    cval = money(awd['awarded_value'] + var_total)
    delivery = 'Completed' if end <= ASOF else ('In Progress' if start <= ASOF else 'Not Started')
    contracts.append({'contract_id': cid, 'award_id': awd['award_id'],
                      'vendor_id': awd['vendor_id'], 'contract_value': cval,
                      'start_date': ds(start), 'end_date': ds(end),
                      'delivery_status': delivery, 'variations': len(var_rows),
                      'variation_value': money(var_total)})

    n_inv = RNG.randint(1, 3)
    share = cval if delivery == 'Completed' else (cval * RNG.uniform(0.3, 0.75)
                                                  if delivery == 'In Progress' else 0.0)
    if share <= 0:
        continue
    each = money(share / n_inv)
    for k in range(n_inv):
        idate = start + timedelta(days=int((k + 1) * (end - start).days / (n_inv + 1)))
        if idate > ASOF:
            break
        iseq += 1
        amt = money(share - each * (n_inv - 1)) if k == n_inv - 1 else each
        invoices.append({'invoice_id': f"INV-{idate.year}-{iseq:05d}", 'contract_id': cid,
                         'vendor_id': awd['vendor_id'], 'amount': amt,
                         'invoice_date': ds(idate),
                         'due_date': ds(idate + timedelta(days=30)),
                         'status': 'Paid', 'requisition_id': r['requisition_id']})
req_by_id = {r['requisition_id']: r for r in reqs}

# ===========================================================================
# 5. FINANCE: payments -> drawdowns -> funding sources -> treasury -> budget
# ===========================================================================
print("\n[5] Finance")
pay_events = []
for d in dsb_rows:
    app = app_by_id[apr_by_id[d['approval_id']]['application_id']]
    pd2 = pdt(d['disbursement_date']) + timedelta(days=RNG.randint(0, 2), hours=RNG.randint(0, 10))
    pay_events.append({'when': min(pd2, ASOF), 'type': 'Loan Disbursement',
                       'payee': partner_by_id[app['pfi_id']]['partner_name'],
                       'payee_type': 'PFI Partner', 'amount': d['amount'],
                       'disbursement_id': d['disbursement_id'], 'invoice_id': '',
                       'reference': d['disbursement_reference'],
                       'dept': 'Lending Operations', 'cat': 'Credit Capital Allocation'})
for inv in invoices:
    r = req_by_id[inv['requisition_id']]
    pd2 = pd_(inv['invoice_date']) + timedelta(days=RNG.randint(5, 32), hours=RNG.randint(8, 17))
    pay_events.append({'when': min(pd2, ASOF), 'type': 'Vendor Payment',
                       'payee': vendor_by_id[inv['vendor_id']]['vendor_name'],
                       'payee_type': 'Vendor', 'amount': inv['amount'],
                       'disbursement_id': '', 'invoice_id': inv['invoice_id'],
                       'reference': inv['invoice_id'], 'dept': r['department'],
                       'cat': PROC_CAT_TO_BUDGET[r['category']]})
pay_events.sort(key=lambda e: e['when'])

FUNDERS = [('FND-001', 'Federal Ministry of Finance', 30_000_000_000.0, '10 Years', 5.0, 0.55),
           ('FND-002', 'Central Bank Intervention Facility', 15_000_000_000.0, '7 Years', 6.5, 0.30),
           ('FND-003', 'African Development Bank (AfDB)', 10_000_000_000.0, '15 Years', 4.2, 0.15)]
headroom = {f[0]: f[2] for f in FUNDERS}
rate_of = {f[0]: f[4] for f in FUNDERS}

out_by_month = collections.Counter()
for e in pay_events:
    out_by_month[(e['when'].year, e['when'].month)] += e['amount']
in_by_month = collections.Counter()
for r in rep_rows:
    if r['paid_date']:
        p = pd_(r['paid_date'])
        in_by_month[(p.year, p.month)] += r['amount_paid']

months = []
m = date(2024, 8, 1)
while (m.year, m.month) <= (2026, 8):
    months.append((m.year, m.month))
    m = add_months(m, 1)

BUFFER = 3_000_000_000.0
drawdowns, cash = [], 0.0
drawn_running = collections.Counter()
month_mix = {}                       # (y, mo) -> ([source_id], [weight]) actually drawn
for (y, mo) in months:
    need = out_by_month[(y, mo)] * 1.03 + BUFFER - cash - in_by_month[(y, mo)]
    if need > 0:
        total = math.ceil(need / 100_000_000) * 100_000_000
        # the mix shifts month to month, so cost_of_funds actually moves
        jit = [f[5] * RNG.uniform(0.6, 1.4) for f in FUNDERS]
        jit = [w / sum(jit) for w in jit]
        want = {f[0]: total * w for f, w in zip(FUNDERS, jit)}
        got = {}
        for sid in want:                                   # clamp to headroom
            got[sid] = min(want[sid], headroom[sid])
        short = total - sum(got.values())
        while short > 1:                                   # redistribute shortfall
            spare = [s for s in got if headroom[s] - got[s] > 1]
            if not spare:
                break
            per = short / len(spare)
            for s in spare:
                take = min(per, headroom[s] - got[s])
                got[s] += take
                short -= take
        for n, (sid, _f, _fa, _t, _r, _s) in enumerate(FUNDERS, 1):
            amt = round(got[sid], 2)
            if amt <= 0:
                continue
            headroom[sid] -= amt
            drawn_running[sid] += amt
            cash += amt
            drawdowns.append({'drawdown_id': f"DRW-{y}{mo:02d}-{n}", 'source_id': sid,
                              'drawdown_date': ds(date(y, mo, 1)),
                              'amount': money(amt),
                              'purpose': 'Credit Capital Funding' if n == 1 else 'Operations & Credit Funding',
                              'status': 'Received'})
        month_mix[(y, mo)] = ([s for s in got if got[s] > 0], [got[s] for s in got if got[s] > 0])
    cash += in_by_month[(y, mo)] - out_by_month[(y, mo)]

src_pick = [f[0] for f in FUNDERS]
src_wts = [f[5] for f in FUNDERS]
last_mix = (src_pick, src_wts)
pay_rows = []
pseq = collections.Counter(); vseq = 1000
for e in pay_events:
    y = e['when'].year
    pseq[y] += 1
    vseq += 1
    pending = (ASOF - e['when']).days <= 7 and RNG.random() < 0.25
    pay_rows.append({'payment_id': f"PAY-{y}-{pseq[y]:06d}",
                     'voucher_number': f"PV-{y}-{vseq}", 'payment_type': e['type'],
                     'payee': e['payee'], 'payee_type': e['payee_type'],
                     'amount': e['amount'], 'payment_date': ts(e['when']),
                     'disbursement_id': e['disbursement_id'], 'invoice_id': e['invoice_id'],
                     'source_id': RNG.choices(*month_mix.get((e['when'].year, e['when'].month), last_mix))[0],
                     'budget_id': budget_id(e['dept'], e['cat'], y),
                     'reference': e['reference'],
                     'status': 'Pending Clearance' if pending else 'Posted'})
    e['status'] = pay_rows[-1]['status']

funding_rows = [{'source_id': sid, 'funder': f, 'facility_amount': money(fa),
                 'drawn': money(drawn_running[sid]),
                 'available': money(fa - drawn_running[sid]), 'tenor': t, 'rate': r}
                for sid, f, fa, t, r, _s in FUNDERS]

# --- treasury: daily, all figures derived -----------------------------------
delta_in = collections.Counter()
for d in drawdowns:
    delta_in[pd_(d['drawdown_date']).date()] += d['amount']
delta_rep = collections.Counter()
for r in rep_rows:
    if r['paid_date']:
        delta_rep[pd_(r['paid_date']).date()] += r['amount_paid']
delta_out = collections.Counter()
for e in pay_events:
    if e['status'] == 'Posted':
        delta_out[e['when'].date()] += e['amount']
drawn_delta = collections.defaultdict(lambda: collections.Counter())
for d in drawdowns:
    drawn_delta[pd_(d['drawdown_date']).date()][d['source_id']] += d['amount']

# committed funds: approved-not-disbursed loans + awarded-not-yet-invoiced contracts
commit_delta = collections.Counter()
dsb_by_apr = {d['approval_id']: d for d in dsb_rows}
for a in apr_rows:
    st = pdt(a['approval_date']).date()
    commit_delta[st] += a['amount_approved']
    d = dsb_by_apr.get(a['approval_id'])
    en = pdt(d['disbursement_date']).date() if d else (pdt(a['approval_date']) + timedelta(days=45)).date()
    commit_delta[en] -= a['amount_approved']
inv_paid_by_ctr = collections.Counter()
for inv in invoices:
    inv_paid_by_ctr[inv['contract_id']] += inv['amount']
awd_by_id = {a['award_id']: a for a in awards}
for c in contracts:
    st = pd_(awd_by_id[c['award_id']]['award_date']).date()
    commit_delta[st] += c['contract_value']
    outstanding = c['contract_value'] - inv_paid_by_ctr[c['contract_id']]
    if outstanding <= 1:
        rel = max((pd_(i['invoice_date']).date() for i in invoices
                   if i['contract_id'] == c['contract_id']), default=st)
        commit_delta[rel] -= c['contract_value']

trs_rows = []
cash = 0.0; committed = 0.0; drawn_cum = collections.Counter()
day = date(2024, 8, 1)
while day <= ASOF.date():
    cash += delta_in[day] + delta_rep[day] - delta_out[day]
    committed += commit_delta[day]
    for sid, amt in drawn_delta[day].items():
        drawn_cum[sid] += amt
    tot = sum(drawn_cum.values())
    cof = (sum(drawn_cum[s] * rate_of[s] for s in drawn_cum) / tot) if tot else 0.0
    trs_rows.append({'position_id': f"TRS-{day.strftime('%Y%m%d')}", 'date': ds(day),
                     'cash_balance': money(cash), 'committed_funds': money(max(committed, 0)),
                     'facility_drawn': money(tot), 'cost_of_funds': round(cof, 2)})
    day += timedelta(days=1)

# --- budget lines: committed/actual derived from payments + open commitments --
actual = collections.Counter(); committed_b = collections.Counter()
for p in pay_rows:
    if p['status'] == 'Posted':
        actual[p['budget_id']] += p['amount']
    else:
        committed_b[p['budget_id']] += p['amount']
for c in contracts:                                    # awarded, not yet invoiced
    r = req_by_id[awd_by_id[c['award_id']]['requisition_id']]
    bid_ = budget_id(r['department'], PROC_CAT_TO_BUDGET[r['category']],
                     pd_(awd_by_id[c['award_id']]['award_date']).year)
    open_amt = c['contract_value'] - inv_paid_by_ctr[c['contract_id']]
    if open_amt > 1:
        committed_b[bid_] += open_amt

bgt_rows = []
for year in (2024, 2025, 2026):
    for dept in DEPT_CODE:
        cats = ['Credit Capital Allocation', 'OpEx', 'CapEx', 'Professional Fees'] \
               if dept == 'Lending Operations' else ['OpEx', 'CapEx', 'Professional Fees']
        for cat in cats:
            bid_ = budget_id(dept, cat, year)
            act = money(actual[bid_]); com = money(act + committed_b[bid_])
            base = com if com > 0 else 50_000_000.0
            budgeted = money(math.ceil(base / RNG.uniform(0.72, 0.94) / 100_000) * 100_000)
            bgt_rows.append({'budget_id': bid_, 'department': dept, 'category': cat,
                             'fiscal_period': year, 'budgeted_amount': budgeted,
                             'committed': com, 'actual': act,
                             'utilisation_pct': round(act / budgeted * 100, 2)})

# ===========================================================================
# 6. PFI PORTAL: submissions -> borrowers -> portfolio records
# ===========================================================================
print("\n[6] PFI Partner Portal")
periods = []
m = date(2024, 8, 1)
while (m.year, m.month) <= (2026, 8):
    periods.append(f"{m.year}-{m.month:02d}")
    m = add_months(m, 1)

sub_rows, sub_index = [], {}
for per in periods:
    py, pm = int(per[:4]), int(per[5:])
    due = add_months(date(py, pm, 5), 1)
    for p in partners:
        sid = f"SUB-{py}{pm:02d}-{p['partner_id']}"
        if due > ASOF.date():
            submitted, status = '', 'Not Due'
        elif RNG.random() < 0.012:
            submitted, status = '', 'Overdue'
        else:
            d = due + timedelta(days=RNG.randint(-11, 4))
            d = min(d, ASOF.date())
            submitted = ds(d)
            status = 'Late' if d > due else 'Submitted'
        row = {'submission_id': sid, 'partner_id': p['partner_id'], 'reporting_period': per,
               'submitted_date': submitted, 'due_date': ds(due), 'record_count': 0,
               'status': status}
        sub_rows.append(row); sub_index[(p['partner_id'], per)] = row

# borrower registry
borrowers, brw_seq = [], 0
zdf_brw = {}                                  # (beneficiary_id, partner_id) -> borrower_ref
own_pool = collections.defaultdict(list)
STATES = sorted({b['state'] for b in bens}); SECTORS = sorted({b['sector'] for b in bens})
AGE = ['18-25', '26-35', '36-50', '50+']; EMP = ['Formal Sector', 'Micro-Enterprise', 'Self-Employed']

rec_rows = []
rseq = 0
linked_by_sub = collections.Counter()
for d in dsb_rows:
    app = app_by_id[apr_by_id[d['approval_id']]['application_id']]
    dd = pdt(d['disbursement_date'])
    per = f"{dd.year}-{dd.month:02d}"
    sub = sub_index[(app['pfi_id'], per)]
    key = (app['beneficiary_id'], app['pfi_id'])
    if key not in zdf_brw:
        brw_seq += 1
        ref = f"PFI-BRW-{brw_seq:06d}"
        b = ben_by_id[app['beneficiary_id']]
        borrowers.append({'borrower_ref': ref, 'partner_id': app['pfi_id'],
                          'beneficiary_id': app['beneficiary_id'], 'state': b['state'],
                          'sector': b['sector'], 'gender': b['gender'],
                          'age_band': b['age_band'], 'employment_category': b['employment_category']})
        zdf_brw[key] = ref
    st, ar = disb_perf[d['disbursement_id']]
    rseq += 1
    rec_rows.append({'record_id': f"REC-{rseq:08d}", 'submission_id': sub['submission_id'],
                     'partner_id': app['pfi_id'], 'borrower_ref': zdf_brw[key],
                     'disbursement_id': d['disbursement_id'], 'funding_source': 'ZDF Facility',
                     'amount': d['amount'], 'disbursed_date': ds(dd),
                     'repayment_status': st, 'arrears_days': ar})
    linked_by_sub[sub['submission_id']] += 1

for p in partners:
    target = int(PARTNER_SIZE[p['institution_type']] * len(periods) * 0.72)
    for _ in range(target):
        brw_seq += 1
        ref = f"PFI-BRW-{brw_seq:06d}"
        borrowers.append({'borrower_ref': ref, 'partner_id': p['partner_id'],
                          'beneficiary_id': '', 'state': RNG.choice(STATES),
                          'sector': RNG.choice(SECTORS), 'gender': RNG.choice(['Male', 'Female']),
                          'age_band': RNG.choice(AGE), 'employment_category': RNG.choice(EMP)})
        own_pool[p['partner_id']].append(ref)

for sub in sub_rows:
    if sub['status'] == 'Not Due':
        continue
    p = partner_by_id[sub['partner_id']]
    per = sub['reporting_period']
    py, pm = int(per[:4]), int(per[5:])
    pstart = date(py, pm, 1)
    pend = add_months(pstart, 1) - timedelta(days=1)
    n = int(PARTNER_SIZE[p['institution_type']] * RNG.uniform(0.85, 1.15))
    pool = own_pool[sub['partner_id']]
    for _ in range(n):
        rseq += 1
        dd = pstart + timedelta(days=RNG.randint(0, (pend - pstart).days))
        st = RNG.choices(['Current', 'In Arrears', 'Defaulted'], weights=[75, 20, 5])[0]
        ar = 0 if st == 'Current' else (RNG.randint(1, 90) if st == 'In Arrears'
                                        else RNG.randint(91, 420))
        rec_rows.append({'record_id': f"REC-{rseq:08d}", 'submission_id': sub['submission_id'],
                         'partner_id': sub['partner_id'], 'borrower_ref': RNG.choice(pool),
                         'disbursement_id': '', 'funding_source': 'Partner Own Book',
                         'amount': money(round(RNG.uniform(150000, 5000000) / 10000) * 10000),
                         'disbursed_date': ds(dd), 'repayment_status': st, 'arrears_days': ar})

cnt = collections.Counter(r['submission_id'] for r in rec_rows)
for sub in sub_rows:
    sub['record_count'] = cnt[sub['submission_id']]

exposure = collections.Counter()
for r in rec_rows:
    if r['disbursement_id']:
        exposure[r['partner_id']] += r['amount']
for p in partners:
    ex = exposure[p['partner_id']]
    p['approved_limit'] = money(math.ceil(ex / 0.75 / 100_000_000) * 100_000_000 if ex else 500_000_000)
    p['zdf_exposure'] = money(ex)

# ===========================================================================
# WRITE
# ===========================================================================
print("\n[7] Writing files")
write(os.path.join(LEN, 'lending_beneficiaries.csv'), ben_cols, bens)
write(os.path.join(LEN, 'lending_applications.csv'),
      ['application_id', 'beneficiary_id', 'pfi_id', 'product', 'amount_requested', 'state',
       'sector', 'submitted_date', 'status', 'decision_reason', 'first_time_borrower_flag'], app_rows)
write(os.path.join(LEN, 'lending_approvals.csv'),
      ['approval_id', 'application_id', 'amount_approved', 'approved_by', 'approval_date',
       'conditions', 'status'], apr_rows)
write(os.path.join(LEN, 'lending_disbursements.csv'),
      ['disbursement_id', 'approval_id', 'amount', 'disbursement_date',
       'disbursement_reference', 'status'], dsb_rows)
write(os.path.join(LEN, 'lending_repayments.csv'),
      ['repayment_id', 'disbursement_id', 'instalment_number', 'amount_due', 'amount_paid',
       'due_date', 'paid_date', 'days_overdue', 'status'], rep_rows)

write(os.path.join(PFI, 'pfi_partners.csv'),
      ['partner_id', 'partner_name', 'institution_type', 'region', 'onboarding_date',
       'approved_limit', 'zdf_exposure', 'status'], partners)
write(os.path.join(PFI, 'pfi_submissions.csv'),
      ['submission_id', 'partner_id', 'reporting_period', 'submitted_date', 'due_date',
       'record_count', 'status'], sub_rows)
write(os.path.join(PFI, 'pfi_borrowers.csv'),
      ['borrower_ref', 'partner_id', 'beneficiary_id', 'state', 'sector', 'gender',
       'age_band', 'employment_category'], borrowers)
write(os.path.join(PFI, 'pfi_portfolio_records.csv'),
      ['record_id', 'submission_id', 'partner_id', 'borrower_ref', 'disbursement_id',
       'funding_source', 'amount', 'disbursed_date', 'repayment_status', 'arrears_days'], rec_rows)

write(os.path.join(FIN, 'finance_funding_sources.csv'),
      ['source_id', 'funder', 'facility_amount', 'drawn', 'available', 'tenor', 'rate'], funding_rows)
write(os.path.join(FIN, 'finance_drawdowns.csv'),
      ['drawdown_id', 'source_id', 'drawdown_date', 'amount', 'purpose', 'status'], drawdowns)
write(os.path.join(FIN, 'finance_payments.csv'),
      ['payment_id', 'voucher_number', 'payment_type', 'payee', 'payee_type', 'amount',
       'payment_date', 'disbursement_id', 'invoice_id', 'source_id', 'budget_id',
       'reference', 'status'], pay_rows)
write(os.path.join(FIN, 'finance_budget_lines.csv'),
      ['budget_id', 'department', 'category', 'fiscal_period', 'budgeted_amount',
       'committed', 'actual', 'utilisation_pct'], bgt_rows)
write(os.path.join(FIN, 'finance_treasury_positions.csv'),
      ['position_id', 'date', 'cash_balance', 'committed_funds', 'facility_drawn',
       'cost_of_funds'], trs_rows)

write(os.path.join(PRC, 'procurement_vendors.csv'),
      ['vendor_id', 'vendor_name', 'category', 'registration_date', 'status'], vendors)
write(os.path.join(PRC, 'procurement_compliance_documents.csv'),
      ['document_id', 'vendor_id', 'document_type', 'issue_date', 'expiry_date', 'status'], docs)
write(os.path.join(PRC, 'procurement_requisitions.csv'),
      ['requisition_id', 'department', 'category', 'budget_id', 'estimated_value',
       'raised_date', 'status', 'cancellation_reason'], reqs)
write(os.path.join(PRC, 'procurement_bids.csv'),
      ['bid_id', 'requisition_id', 'vendor_id', 'bid_amount', 'submitted_date',
       'responsive_flag'], bids)
write(os.path.join(PRC, 'procurement_awards.csv'),
      ['award_id', 'requisition_id', 'bid_id', 'vendor_id', 'awarded_value', 'award_date',
       'award_justification'], awards)
write(os.path.join(PRC, 'procurement_contracts.csv'),
      ['contract_id', 'award_id', 'vendor_id', 'contract_value', 'start_date', 'end_date',
       'delivery_status', 'variations', 'variation_value'], contracts)
write(os.path.join(PRC, 'procurement_contract_variations.csv'),
      ['variation_id', 'contract_id', 'variation_date', 'variation_amount', 'reason'], variations)
write(os.path.join(PRC, 'procurement_invoices.csv'),
      ['invoice_id', 'contract_id', 'requisition_id', 'vendor_id', 'amount', 'invoice_date',
       'due_date', 'status'], invoices)

print("\n[8] Totals")
print(f"  disbursed            {sum(d['amount'] for d in dsb_rows)/1e9:>10,.2f} bn")
print(f"  repaid (cash in)     {sum(r['amount_paid'] for r in rep_rows)/1e9:>10,.2f} bn")
print(f"  payments out         {sum(p['amount'] for p in pay_rows)/1e9:>10,.2f} bn")
print(f"  facility drawn       {sum(d['amount'] for d in drawdowns)/1e9:>10,.2f} bn")
print(f"  facility total       {sum(f['facility_amount'] for f in funding_rows)/1e9:>10,.2f} bn")
print(f"  budgeted             {sum(b['budgeted_amount'] for b in bgt_rows)/1e9:>10,.2f} bn")
print(f"  min cash balance     {min(t['cash_balance'] for t in trs_rows)/1e9:>10,.2f} bn")
print(f"  procurement awarded  {sum(a['awarded_value'] for a in awards)/1e9:>10,.2f} bn")
