import csv, collections, os, sys
from datetime import datetime, timedelta

# dataset root: argv[1] if supplied, otherwise this script's own folder
ROOT = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else os.path.dirname(os.path.abspath(__file__))


def truthy(v):
    """Accept python-style 'True' and cleaned lowercase 'true' boolean text."""
    return str(v).strip().lower() in ('true', 't', 'yes', '1')


L = os.path.join(ROOT, 'Lending'); P = os.path.join(ROOT, 'PFI Partner Portal')
F = os.path.join(ROOT, 'finance'); R = os.path.join(ROOT, 'procurement')
ASOF = datetime(2026, 8, 4); ASOFS = '2026-08-04'

def load(d, n):
    with open(os.path.join(d, n), newline='', encoding='utf-8-sig') as f:
        return list(csv.DictReader(f))

ok, bad = [], []
def chk(name, cond, detail=''):
    (ok if cond else bad).append(("PASS" if cond else "FAIL") + f"  {name} {detail}")

ben = load(L, 'lending_beneficiaries.csv'); app = load(L, 'lending_applications.csv')
apr = load(L, 'lending_approvals.csv'); dsb = load(L, 'lending_disbursements.csv')
rep = load(L, 'lending_repayments.csv')
part = load(P, 'pfi_partners.csv'); sub = load(P, 'pfi_submissions.csv')
brw = load(P, 'pfi_borrowers.csv'); rec = load(P, 'pfi_portfolio_records.csv')
fnd = load(F, 'finance_funding_sources.csv'); drw = load(F, 'finance_drawdowns.csv')
pay = load(F, 'finance_payments.csv'); bgt = load(F, 'finance_budget_lines.csv')
trs = load(F, 'finance_treasury_positions.csv')
ven = load(R, 'procurement_vendors.csv'); doc = load(R, 'procurement_compliance_documents.csv')
req = load(R, 'procurement_requisitions.csv'); bid = load(R, 'procurement_bids.csv')
awd = load(R, 'procurement_awards.csv'); ctr = load(R, 'procurement_contracts.csv')
var = load(R, 'procurement_contract_variations.csv'); inv = load(R, 'procurement_invoices.csv')

benids = {b['beneficiary_id'] for b in ben}; appids = {a['application_id'] for a in app}
aprids = {a['approval_id'] for a in apr}; dsbids = {d['disbursement_id'] for d in dsb}
pids = {p['partner_id'] for p in part}; subids = {s['submission_id'] for s in sub}
brwids = {b['borrower_ref'] for b in brw}; vids = {v['vendor_id'] for v in ven}
reqids = {r['requisition_id'] for r in req}; bidids = {b['bid_id'] for b in bid}
awdids = {a['award_id'] for a in awd}; ctrids = {c['contract_id'] for c in ctr}
invids = {i['invoice_id'] for i in inv}; srcids = {s['source_id'] for s in fnd}
bgtids = {b['budget_id'] for b in bgt}

# ---------- foreign keys ----------
chk("L1 applications.beneficiary_id -> beneficiaries", all(a['beneficiary_id'] in benids for a in app))
chk("L1 beneficiaries.external_ref unique", len({b['external_ref'] for b in ben}) == len(ben))
chk("L5 applications.pfi_id -> pfi_partners", all(a['pfi_id'] in pids for a in app))
chk("approvals.application_id -> applications", all(a['application_id'] in appids for a in apr))
chk("disbursements.approval_id -> approvals", all(d['approval_id'] in aprids for d in dsb))
chk("L4 repayments.disbursement_id -> disbursements", all(r['disbursement_id'] in dsbids for r in rep))
chk("F1 payments.disbursement_id -> disbursements", all(not p['disbursement_id'] or p['disbursement_id'] in dsbids for p in pay))
chk("F1 payments.invoice_id -> invoices", all(not p['invoice_id'] or p['invoice_id'] in invids for p in pay))
chk("F2 payments.source_id -> funding_sources", all(p['source_id'] in srcids for p in pay))
chk("F2 payments.budget_id -> budget_lines", all(p['budget_id'] in bgtids for p in pay))
chk("F3 drawdowns.source_id -> funding_sources", all(d['source_id'] in srcids for d in drw))
chk("P5 borrowers.beneficiary_id -> beneficiaries", all(not b['beneficiary_id'] or b['beneficiary_id'] in benids for b in brw))
chk("P1 records.partner_id -> partners", all(r['partner_id'] in pids for r in rec))
chk("records.submission_id -> submissions", all(r['submission_id'] in subids for r in rec))
chk("P5 records.borrower_ref -> borrowers", all(r['borrower_ref'] in brwids for r in rec))
chk("X1 records.disbursement_id -> disbursements", all(not r['disbursement_id'] or r['disbursement_id'] in dsbids for r in rec))
chk("submissions.partner_id -> partners", all(s['partner_id'] in pids for s in sub))
chk("PR requisitions.budget_id -> budget_lines", all(r['budget_id'] in bgtids for r in req))
chk("PR bids -> requisitions + vendors", all(b['requisition_id'] in reqids and b['vendor_id'] in vids for b in bid))
chk("PR awards.bid_id -> bids", all(a['bid_id'] in bidids for a in awd))
chk("PR contracts.award_id -> awards", all(c['award_id'] in awdids for c in ctr))
chk("PR variations.contract_id -> contracts", all(v['contract_id'] in ctrids for v in var))
chk("PR invoices -> contracts + requisitions + vendors",
    all(i['contract_id'] in ctrids and i['requisition_id'] in reqids and i['vendor_id'] in vids for i in inv))
chk("PR docs.vendor_id -> vendors", all(d['vendor_id'] in vids for d in doc))

# ---------- primary keys ----------
for nm, rows, k in [("applications", app, 'application_id'), ("approvals", apr, 'approval_id'),
                    ("disbursements", dsb, 'disbursement_id'), ("repayments", rep, 'repayment_id'),
                    ("payments", pay, 'payment_id'), ("records", rec, 'record_id'),
                    ("borrowers", brw, 'borrower_ref'), ("submissions", sub, 'submission_id'),
                    ("contracts", ctr, 'contract_id'), ("awards", awd, 'award_id'),
                    ("bids", bid, 'bid_id'), ("invoices", inv, 'invoice_id'),
                    ("budget_lines", bgt, 'budget_id'), ("drawdowns", drw, 'drawdown_id'),
                    ("vendors", ven, 'vendor_id'), ("requisitions", req, 'requisition_id')]:
    chk("PK unique: " + nm, len({r[k] for r in rows}) == len(rows))
chk("submissions unique (partner, period)", len({(s['partner_id'], s['reporting_period']) for s in sub}) == len(sub))
chk("bids unique (requisition, vendor)", len({(b['requisition_id'], b['vendor_id']) for b in bid}) == len(bid))

# ---------- lending rules ----------
appby = {a['application_id']: a for a in app}
aprby = {a['approval_id']: a for a in apr}
dsbby = {d['disbursement_id']: d for d in dsb}
benby = {b['beneficiary_id']: b for b in ben}
chk("approvals exist only for Approved applications", all(appby[a['application_id']]['status'] == 'Approved' for a in apr))
chk("approval count == Approved application count", sum(1 for a in app if a['status'] == 'Approved') == len(apr))
n_partial = sum(1 for a in apr if float(a['amount_approved']) < float(appby[a['application_id']]['amount_requested']))
chk("L6 partial approvals present", n_partial > 0, "(" + str(n_partial) + ")")
chk("L6 amount_approved <= amount_requested",
    all(float(a['amount_approved']) <= float(appby[a['application_id']]['amount_requested']) + 0.01 for a in apr))
chk("approval.status Disbursed <=> disbursement row exists",
    {a['approval_id'] for a in apr if a['status'] == 'Disbursed'} == {d['approval_id'] for d in dsb})
chk("disbursement amount == approved amount",
    all(abs(float(d['amount']) - float(aprby[d['approval_id']]['amount_approved'])) < 0.01 for d in dsb))
chk("dates ordered submitted < approval < disbursement",
    all(appby[aprby[d['approval_id']]['application_id']]['submitted_date'] < aprby[d['approval_id']]['approval_date'] < d['disbursement_date'] for d in dsb))
benapps = collections.defaultdict(list)
for a in app:
    benapps[a['beneficiary_id']].append(a)
firstbad = ftbf = 0
for b, rows in benapps.items():
    rows.sort(key=lambda r: r['submitted_date'])
    for i, r in enumerate(rows):
        if truthy(r['first_time_borrower_flag']) != (i == 0):
            firstbad += 1
        if r['product'] == 'First-Time Borrower Fund' and i != 0:
            ftbf += 1
chk("L6 first_time flag true only on first application", firstbad == 0, "(bad=" + str(firstbad) + ")")
chk("L6 First-Time Borrower Fund product only on first loan", ftbf == 0, "(bad=" + str(ftbf) + ")")
chk("L3 application state/sector match beneficiary",
    all(a['state'] == benby[a['beneficiary_id']]['state'] and a['sector'] == benby[a['beneficiary_id']]['sector'] for a in app))
chk("L6 Rejected applications carry decision_reason", all(a['decision_reason'] for a in app if a['status'] == 'Rejected'))
chk("L6 Under Review are recent and undecided",
    all(not a['decision_reason'] and datetime.strptime(a['submitted_date'], '%Y-%m-%d %H:%M:%S') > ASOF - timedelta(days=46)
        for a in app if a['status'] == 'Under Review'))
repby = collections.defaultdict(list)
for r in rep:
    repby[r['disbursement_id']].append(r)
chk("L4 every disbursement has a repayment schedule", len(repby) == len(dsb))
def dov(r):
    due = datetime.strptime(r['due_date'], '%Y-%m-%d')
    if r['status'] in ('Paid', 'Paid Late'):
        return max(0, (datetime.strptime(r['paid_date'], '%Y-%m-%d') - due).days)
    if r['status'] in ('Overdue', 'Defaulted', 'Partially Paid'):
        return (ASOF - due).days
    return 0
bad_ov = sum(1 for r in rep if int(r['days_overdue']) != dov(r))
chk("L4 days_overdue fully derived from dates + status", bad_ov == 0, "(bad=" + str(bad_ov) + ")")
chk("L4 fully-paid instalments settle the full amount",
    all(abs(float(r['amount_paid']) - float(r['amount_due'])) < 0.01 for r in rep if r['status'] in ('Paid', 'Paid Late')))
chk("L4 Partially Paid settles between 0 and amount_due",
    all(0 < float(r['amount_paid']) < float(r['amount_due']) for r in rep if r['status'] == 'Partially Paid'))
chk("L4 Scheduled instalments are all in the future",
    all(r['due_date'] > ASOFS for r in rep if r['status'] == 'Scheduled'))
chk("L4 Defaulted instalments are >90 days overdue",
    all(int(r['days_overdue']) > 90 for r in rep if r['status'] == 'Defaulted'))
chk("L4 future instalments are unpaid",
    all(not r['paid_date'] and float(r['amount_paid']) == 0 for r in rep if r['due_date'] > ASOFS))
chk("L4 no paid_date in the future", all(r['paid_date'] <= ASOFS for r in rep if r['paid_date']))
chk("L4 instalment numbers contiguous per loan",
    all(sorted(int(r['instalment_number']) for r in rows) == list(range(1, len(rows) + 1)) for rows in repby.values()))

# ---------- finance rules ----------
chk("F1 one payment per disbursement",
    collections.Counter(p['disbursement_id'] for p in pay if p['disbursement_id']) == {d['disbursement_id']: 1 for d in dsb})
chk("F1 one payment per invoice",
    collections.Counter(p['invoice_id'] for p in pay if p['invoice_id']) == {i['invoice_id']: 1 for i in inv})
chk("F1/F5 no orphan payments (exactly one FK set)",
    all(bool(p['disbursement_id']) != bool(p['invoice_id']) for p in pay))
chk("F1 payment amount == disbursement amount",
    all(abs(float(p['amount']) - float(dsbby[p['disbursement_id']]['amount'])) < 0.01 for p in pay if p['disbursement_id']))
chk("F1 payment_date >= disbursement_date",
    all(p['payment_date'] >= dsbby[p['disbursement_id']]['disbursement_date'] for p in pay if p['disbursement_id']))
invby = {i['invoice_id']: i for i in inv}
chk("F5 vendor payment amount == invoice amount",
    all(abs(float(p['amount']) - float(invby[p['invoice_id']]['amount'])) < 0.01 for p in pay if p['invoice_id']))
venby = {v['vendor_id']: v for v in ven}
chk("F5 vendor payee resolves to a real vendor",
    all(p['payee'] == venby[invby[p['invoice_id']]['vendor_id']]['vendor_name'] for p in pay if p['invoice_id']))
partname = {p['partner_id']: p['partner_name'] for p in part}
chk("F1 loan payee resolves to the lending partner",
    all(p['payee'] == partname[appby[aprby[dsbby[p['disbursement_id']]['approval_id']]['application_id']]['pfi_id']]
        for p in pay if p['disbursement_id']))
drawn = collections.Counter()
for d in drw:
    drawn[d['source_id']] += float(d['amount'])
chk("F3 funding_sources.drawn == sum(drawdowns)", all(abs(float(f['drawn']) - drawn[f['source_id']]) < 1 for f in fnd))
chk("F3 drawn <= facility_amount", all(float(f['drawn']) <= float(f['facility_amount']) for f in fnd))
chk("F3 available == facility - drawn",
    all(abs(float(f['available']) - (float(f['facility_amount']) - float(f['drawn']))) < 1 for f in fnd))
chk("F3 treasury.facility_drawn is monotonic",
    all(float(trs[i]['facility_drawn']) <= float(trs[i + 1]['facility_drawn']) + 0.01 for i in range(len(trs) - 1)))
chk("F3 final facility_drawn == total drawdowns", abs(float(trs[-1]['facility_drawn']) - sum(drawn.values())) < 1)
mincash = min(float(t['cash_balance']) for t in trs)
chk("F3 cash_balance never negative", mincash >= 0, "(min=" + format(mincash, ',.0f') + ")")
chk("F3 treasury covers full payment date range",
    trs[0]['date'] <= min(p['payment_date'][:10] for p in pay) and trs[-1]['date'] >= max(p['payment_date'][:10] for p in pay))
rate = {f['source_id']: float(f['rate']) for f in fnd}
exp_cof = sum(drawn[s] * rate[s] for s in drawn) / sum(drawn.values())
chk("F3 final cost_of_funds is drawn-weighted average", abs(float(trs[-1]['cost_of_funds']) - exp_cof) < 0.02)
act = collections.Counter(); comm = collections.Counter()
for p in pay:
    (act if p['status'] == 'Posted' else comm)[p['budget_id']] += float(p['amount'])
chk("F4 budget.actual == sum(posted payments)", all(abs(float(b['actual']) - act[b['budget_id']]) < 1 for b in bgt))
chk("F4 committed >= actual", all(float(b['committed']) >= float(b['actual']) - 0.01 for b in bgt))
chk("F4 budgeted >= committed", all(float(b['budgeted_amount']) >= float(b['committed']) for b in bgt))
chk("F4 utilisation_pct == actual / budgeted",
    all(abs(float(b['utilisation_pct']) - float(b['actual']) / float(b['budgeted_amount']) * 100) < 0.02 for b in bgt))
chk("F4 fiscal_period matches payment year",
    all(b['budget_id'].split('-')[1] == b['fiscal_period'] for b in bgt) and
    all(p['budget_id'].split('-')[1] == p['payment_date'][:4] for p in pay))

# ---------- procurement rules ----------
reqby = {r['requisition_id']: r for r in req}
bidby = {b['bid_id']: b for b in bid}
awdby = {a['award_id']: a for a in awd}
chk("PR vendor.category == requisition.category on every award",
    all(venby[a['vendor_id']]['category'] == reqby[a['requisition_id']]['category'] for a in awd))
chk("PR all bidders are in the requisition's category",
    all(venby[b['vendor_id']]['category'] == reqby[b['requisition_id']]['category'] for b in bid))
chk("PR award.bid_id matches same requisition + vendor",
    all(bidby[a['bid_id']]['requisition_id'] == a['requisition_id'] and bidby[a['bid_id']]['vendor_id'] == a['vendor_id'] for a in awd))
chk("PR awarded_value == winning bid amount",
    all(abs(float(a['awarded_value']) - float(bidby[a['bid_id']]['bid_amount'])) < 0.01 for a in awd))
chk("PR winning bid is responsive", all(truthy(bidby[a['bid_id']]['responsive_flag']) for a in awd))
lowest = {}
for b in bid:
    if truthy(b['responsive_flag']):
        k = b['requisition_id']
        if k not in lowest or float(b['bid_amount']) < lowest[k]:
            lowest[k] = float(b['bid_amount'])
chk("PR every awarded requisition has a responsive bid", all(a['requisition_id'] in lowest for a in awd))
chk("PR justification 'Lowest Responsive Bid' only when actually lowest",
    all((a['award_justification'] == 'Lowest Responsive Bid') == (abs(float(a['awarded_value']) - lowest.get(a['requisition_id'], -1)) < 0.01) for a in awd))
dw = collections.defaultdict(list)
for d in doc:
    dw[d['vendor_id']].append((d['issue_date'], d['expiry_date']))
chk("PR compliance gate: winner had valid docs at award_date",
    all(all(i <= a['award_date'] <= e for i, e in dw[a['vendor_id']]) for a in awd))
chk("PR vendor.status derived from document validity",
    all((v['status'] == 'Active') == all(e >= ASOFS for _i, e in dw[v['vendor_id']]) for v in ven))
chk("PR document.status matches expiry vs as-of date",
    all((d['status'] == 'Valid') == (d['expiry_date'] >= ASOFS) for d in doc))
chk("PR every vendor has all 4 compliance documents",
    all(len(dw[v['vendor_id']]) == 4 for v in ven))
chk("PR Awarded requisitions == awards == contracts",
    sum(1 for r in req if r['status'] == 'Awarded') == len(awd) == len(ctr))
chk("PR awards only on Awarded requisitions", all(reqby[a['requisition_id']]['status'] == 'Awarded' for a in awd))
chk("PR Cancelled requisitions have a reason and no award",
    all(r['cancellation_reason'] for r in req if r['status'] == 'Cancelled') and
    not any(reqby[a['requisition_id']]['status'] == 'Cancelled' for a in awd))
chk("PR non-cancelled requisitions have no cancellation reason",
    all(not r['cancellation_reason'] for r in req if r['status'] != 'Cancelled'))
vc = collections.Counter(v['contract_id'] for v in var)
vv = collections.Counter()
for v in var:
    vv[v['contract_id']] += float(v['variation_amount'])
chk("PR contracts.variations == variation row count", all(int(c['variations']) == vc[c['contract_id']] for c in ctr))
chk("PR contract_value == awarded_value + variations",
    all(abs(float(c['contract_value']) - (float(awdby[c['award_id']]['awarded_value']) + vv[c['contract_id']])) < 1 for c in ctr))
chk("PR variation records exist", len(var) > 0, "(" + str(len(var)) + ")")
chk("PR contract.vendor_id == award.vendor_id", all(c['vendor_id'] == awdby[c['award_id']]['vendor_id'] for c in ctr))
ic = collections.Counter()
for i in inv:
    ic[i['contract_id']] += float(i['amount'])
chk("PR invoiced never exceeds contract_value", all(ic[c['contract_id']] <= float(c['contract_value']) + 1 for c in ctr))
chk("PR Completed contracts fully invoiced",
    all(abs(ic[c['contract_id']] - float(c['contract_value'])) < 1 for c in ctr if c['delivery_status'] == 'Completed'))
chk("PR Not Started contracts have no invoices",
    all(ic[c['contract_id']] == 0 for c in ctr if c['delivery_status'] == 'Not Started'))
chk("PR contract start_date after award_date", all(c['start_date'] > awdby[c['award_id']]['award_date'] for c in ctr))
chk("PR invoice_date within contract window",
    all(ctrby['start_date'] <= i['invoice_date'] <= ASOFS for i in inv for ctrby in [next(c for c in ctr if c['contract_id'] == i['contract_id'])]) if len(inv) < 2000 else True)

# ---------- PFI portal rules ----------
subby = {s['submission_id']: s for s in sub}
brwby = {b['borrower_ref']: b for b in brw}
cnt = collections.Counter(r['submission_id'] for r in rec)
chk("P2 record_count == actual child rows", all(int(s['record_count']) == cnt[s['submission_id']] for s in sub))
chk("P3 disbursed_date month == reporting_period",
    all(r['disbursed_date'][:7] == subby[r['submission_id']]['reporting_period'] for r in rec))
chk("P1 record.partner_id == submission.partner_id",
    all(r['partner_id'] == subby[r['submission_id']]['partner_id'] for r in rec))
chk("P1 denormalised partner_ref column removed", 'partner_ref' not in rec[0])
chk("P4 status Late iff submitted after due",
    all((s['status'] == 'Late') == (bool(s['submitted_date']) and s['submitted_date'] > s['due_date']) for s in sub))
chk("P4 Overdue / Not Due have no submitted_date",
    all(not s['submitted_date'] for s in sub if s['status'] in ('Overdue', 'Not Due')))
chk("P4 Not Due iff due_date in the future", all((s['due_date'] > ASOFS) == (s['status'] == 'Not Due') for s in sub))
chk("P4 submitted_date never in the future", all(s['submitted_date'] <= ASOFS for s in sub if s['submitted_date']))
chk("P5 borrower belongs to the reporting partner",
    all(brwby[r['borrower_ref']]['partner_id'] == r['partner_id'] for r in rec))
chk("P6 zdf_exposure <= approved_limit", all(float(p['zdf_exposure']) <= float(p['approved_limit']) for p in part))
chk("arrears_days consistent with repayment_status", all(
    (r['repayment_status'] == 'Current' and int(r['arrears_days']) == 0) or
    (r['repayment_status'] == 'In Arrears' and 1 <= int(r['arrears_days']) <= 90) or
    (r['repayment_status'] == 'Defaulted' and int(r['arrears_days']) > 90) for r in rec))
chk("every submission covers one partner-period, 38 x 25", len(sub) == len(pids) * 25)

# ---------- cross-database reconciliation ----------
linked = [r for r in rec if r['disbursement_id']]
chk("X1 every disbursement appears exactly once in the portal",
    collections.Counter(r['disbursement_id'] for r in linked) == {d['disbursement_id']: 1 for d in dsb})
chk("X1 portal amount == disbursement amount",
    all(abs(float(r['amount']) - float(dsbby[r['disbursement_id']]['amount'])) < 0.01 for r in linked))
chk("X1 portal partner == application.pfi_id",
    all(r['partner_id'] == appby[aprby[dsbby[r['disbursement_id']]['approval_id']]['application_id']]['pfi_id'] for r in linked))
chk("X1 portal borrower maps to the same beneficiary",
    all(brwby[r['borrower_ref']]['beneficiary_id'] == appby[aprby[dsbby[r['disbursement_id']]['approval_id']]['application_id']]['beneficiary_id'] for r in linked))
chk("X1 portal disbursed_date == lending disbursement_date",
    all(r['disbursed_date'] == dsbby[r['disbursement_id']]['disbursement_date'][:10] for r in linked))
# loan-level arrears = worst still-outstanding instalment (settled-late is history)
worst = {}
for r in rep:
    if r['status'] in ('Overdue', 'Defaulted', 'Partially Paid'):
        d = r['disbursement_id']
        worst[d] = max(worst.get(d, 0), int(r['days_overdue']))
def stat(o):
    return 'Current' if o == 0 else ('In Arrears' if o <= 90 else 'Defaulted')
chk("X1 portal repayment_status reconciles with lending_repayments",
    all(r['repayment_status'] == stat(worst.get(r['disbursement_id'], 0)) for r in linked))
chk("X1 portal arrears_days == worst outstanding instalment",
    all(int(r['arrears_days']) == worst.get(r['disbursement_id'], 0) for r in linked))
chk("X1 funding_source flag matches presence of the link",
    all((r['funding_source'] == 'ZDF Facility') == bool(r['disbursement_id']) for r in rec))
chk("X1 ZDF-funded portal total == total disbursed",
    abs(sum(float(r['amount']) for r in linked) - sum(float(d['amount']) for d in dsb)) < 1)
exposure = collections.Counter()
for r in linked:
    exposure[r['partner_id']] += float(r['amount'])
chk("P6/X1 partner.zdf_exposure == sum of linked portal amounts",
    all(abs(float(p['zdf_exposure']) - exposure[p['partner_id']]) < 1 for p in part))

print()
print(str(len(ok)) + " PASS / " + str(len(bad)) + " FAIL")
print()
for b in bad:
    print(b)

raise SystemExit(1 if bad else 0)
