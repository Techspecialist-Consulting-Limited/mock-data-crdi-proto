#!/usr/bin/env python
"""
clean_script.py - ZDF mock dataset cleaner.

Cleans every CSV in the four database folders (Lending, PFI Partner Portal,
finance, procurement) WITHOUT changing the meaning of the data:

  Stage 1  structural   - BOM, blank rows, whitespace, duplicate rows, headers
  Stage 2  nulls        - sentinel strings ("NA", "None", "-") -> real empty cell
  Stage 3  numerics     - money/rate to 2dp, counts to integers, booleans lowercase
  Stage 4  dates        - one format per column, enforced (never coerced silently)
  Stage 5  names        - collapse doubled legal suffixes, de-duplicate labels,
                          and cascade the result into finance_payments.payee
  Stage 6  validate     - re-run the 129 relationship checks; roll back on failure
  Stage 7  output       - LF line endings, UTF-8 no BOM, JSON change report

Design notes
------------
* Idempotent: running it twice produces byte-identical output.
* Config-driven: the column classes below are the only thing to edit when the
  schema grows. There is no per-file special-casing.
* Value-preserving: amounts are RE-RENDERED, never recomputed. Any rounding that
  would move a value by more than HALF_KOBO is reported instead of written.
* Fabric / Spark portability: the row-level helpers (`clean_cell`,
  `normalise_number`, `collapse_designators`) are pure functions over strings
  with no I/O and no third-party imports, so they can be lifted directly into a
  Spark UDF or a Fabric dataflow step. Only the file walking is local.

Usage
-----
    python clean_script.py                  # clean in place (git is the undo)
    python clean_script.py --out ./clean    # write to a mirror folder instead
    python clean_script.py --no-names       # skip Stage 5
    python clean_script.py --dry-run        # report only, write nothing
"""

import argparse
import csv
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from collections import Counter, defaultdict
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation

csv.field_size_limit(10 ** 7)

FOLDERS = ['Lending', 'PFI Partner Portal', 'finance', 'procurement']
VERIFIER = '_tools_verify_relationships.py'
HALF_KOBO = Decimal('0.005')

# --------------------------------------------------------------------------
# COLUMN CLASSES - the whole configuration of the cleaner
# --------------------------------------------------------------------------
# Money: currency, always exactly 2 decimal places.
MONEY = {
    'amount', 'amount_requested', 'amount_approved', 'amount_due', 'amount_paid',
    'facility_amount', 'drawn', 'available', 'budgeted_amount', 'committed',
    'actual', 'awarded_value', 'bid_amount', 'estimated_value', 'contract_value',
    'variation_amount', 'variation_value', 'approved_limit', 'zdf_exposure',
    'cash_balance', 'committed_funds', 'facility_drawn',
}
# Rates and percentages: 2 decimal places.
RATE = {'rate', 'cost_of_funds', 'utilisation_pct'}
# Whole numbers: never a decimal point.
INTEGER = {'arrears_days', 'days_overdue', 'instalment_number', 'record_count',
           'variations', 'fiscal_period'}
# Booleans: lowercase true/false so Spark/Fabric infers BooleanType.
BOOLEAN = {'first_time_borrower_flag', 'responsive_flag'}

# Strings that mean "no value" and must become a genuinely empty cell.
NULL_SENTINELS = {'na', 'n/a', 'null', 'none', 'nan', 'nil', '-', '--', '?',
                  '#n/a', 'undefined', 'unknown'}

# Corporate designators. A name keeps at most one - the last.
DESIGNATORS = {'Ltd', 'Limited', 'LLC', 'Inc', 'PLC'}

DATE_RE = re.compile(r'\d{4}-\d{2}-\d{2}')
TS_RE = re.compile(r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}')
MONTH_RE = re.compile(r'\d{4}-\d{2}')
DATEISH = re.compile(r'date|period|_at$')


# --------------------------------------------------------------------------
# Row-level helpers (pure - reusable as Spark UDFs)
# --------------------------------------------------------------------------
def clean_cell(value):
    """Stage 1 + 2: trim, collapse internal whitespace, normalise nulls."""
    if value is None:
        return ''
    v = value.replace('﻿', '')
    v = re.sub(r'\s+', ' ', v).strip()
    if v.lower() in NULL_SENTINELS:
        return ''
    return v


def normalise_number(value, kind):
    """Stage 3. Returns (text, moved) where `moved` flags a real value change."""
    if value == '':
        return '', False
    try:
        d = Decimal(value)
    except InvalidOperation:
        return value, False
    if kind == 'integer':
        q = d.quantize(Decimal('1'), rounding=ROUND_HALF_UP)
    else:
        q = d.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    return format(q, 'f'), abs(d - q) > HALF_KOBO


def normalise_boolean(value):
    if value == '':
        return '', False
    low = value.strip().lower()
    if low in ('true', 't', 'yes', 'y', '1'):
        return 'true', False
    if low in ('false', 'f', 'no', 'n', '0'):
        return 'false', False
    return value, True                      # unrecognised - report, don't guess


def collapse_designators(name):
    """'Okafor Ltd Ltd' -> 'Okafor Ltd';  'Eze Inc Nig. Ltd' -> 'Eze Nig. Ltd'."""
    toks = name.split()
    hits = [i for i, t in enumerate(toks) if t.strip('.,') in DESIGNATORS]
    if len(hits) <= 1:
        return name
    drop = set(hits[:-1])                   # keep only the final designator
    return ' '.join(t for i, t in enumerate(toks) if i not in drop)


# --------------------------------------------------------------------------
# File I/O
# --------------------------------------------------------------------------
def read_csv(path):
    with open(path, newline='', encoding='utf-8-sig') as f:
        rd = csv.reader(f)
        try:
            header = next(rd)
        except StopIteration:
            return [], []
        return header, list(rd)


def write_csv(path, header, rows, attempts=4):
    """Write with retry: on Windows an editor or indexer can hold a brief lock."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    for i in range(attempts):
        try:
            with open(path, 'w', newline='', encoding='utf-8') as f:
                w = csv.writer(f, lineterminator='\n', quoting=csv.QUOTE_MINIMAL)
                w.writerow(header)
                w.writerows(rows)
            return
        except OSError:
            if i == attempts - 1:
                raise
            time.sleep(0.4 * (i + 1))


def discover(root):
    out = []
    for folder in FOLDERS:
        d = os.path.join(root, folder)
        if not os.path.isdir(d):
            continue
        for fn in sorted(os.listdir(d)):
            if fn.lower().endswith('.csv'):
                out.append((folder, fn, os.path.join(d, fn)))
    return out


def norm_header(h):
    h = re.sub(r'\s+', '_', h.replace('﻿', '').strip()).lower()
    return re.sub(r'__+', '_', h)


# --------------------------------------------------------------------------
# Stages 1-4
# --------------------------------------------------------------------------
def clean_table(folder, fn, header, rows, report):
    key = f"{folder}/{fn}"
    r = report['files'].setdefault(key, {})
    ncol = len(header)

    new_header = [norm_header(h) for h in header]
    if new_header != header:
        r['headers_renamed'] = [[a, b] for a, b in zip(header, new_header) if a != b]

    # date/timestamp format is decided per (file, column) from the data itself,
    # because e.g. submitted_date is a timestamp in Lending and a date elsewhere.
    date_kind = {}
    for i, col in enumerate(new_header):
        if not DATEISH.search(col):
            continue
        seen = Counter()
        for row in rows:
            v = row[i].strip() if i < len(row) else ''
            if not v:
                continue
            if TS_RE.fullmatch(v):
                seen['timestamp'] += 1
            elif DATE_RE.fullmatch(v):
                seen['date'] += 1
            elif MONTH_RE.fullmatch(v):
                seen['month'] += 1
            else:
                seen['other'] += 1
        if seen:
            date_kind[i] = seen.most_common(1)[0][0]
            if len(seen) > 1:
                r.setdefault('date_format_mixed', {})[col] = dict(seen)

    stats = defaultdict(Counter)
    out, seen_rows = [], set()
    dropped_blank = dropped_dup = ragged = 0

    for row in rows:
        if len(row) < ncol:
            row = row + [''] * (ncol - len(row))
            ragged += 1
        elif len(row) > ncol:
            row = row[:ncol]
            ragged += 1

        cleaned = []
        for i, raw in enumerate(row):
            col = new_header[i]
            v = clean_cell(raw)
            if v != raw.strip():
                if raw != raw.strip() or re.search(r'\s\s', raw):
                    stats['whitespace'][col] += 1
                elif v == '' and raw.strip():
                    stats['null_sentinel'][col] += 1

            if col in BOOLEAN:
                nv, prob = normalise_boolean(v)
                if prob:
                    stats['unparsed_boolean'][col] += 1
                elif nv != v:
                    stats['boolean'][col] += 1
                v = nv
            elif col in MONEY or col in RATE or col in INTEGER:
                kind = 'integer' if col in INTEGER else 'decimal2'
                nv, moved = normalise_number(v, kind)
                if moved:
                    stats['rounding_exceeded'][col] += 1
                    nv = v                                  # refuse to change it
                elif nv != v:
                    stats['numeric_format'][col] += 1
                v = nv
            elif i in date_kind and v:
                want = date_kind[i]
                good = (TS_RE if want == 'timestamp' else
                        DATE_RE if want == 'date' else MONTH_RE).fullmatch(v)
                if not good:
                    stats['date_unparsed'][col] += 1
            cleaned.append(v)

        if not any(cleaned):
            dropped_blank += 1
            continue
        t = tuple(cleaned)
        if t in seen_rows:
            dropped_dup += 1
            continue
        seen_rows.add(t)
        out.append(cleaned)

    if dropped_blank:
        r['blank_rows_dropped'] = dropped_blank
    if dropped_dup:
        r['duplicate_rows_dropped'] = dropped_dup
    if ragged:
        r['ragged_rows_padded_or_trimmed'] = ragged
    for k, c in stats.items():
        if c:
            r[k] = dict(c)
    r['rows'] = len(out)
    return new_header, out


# --------------------------------------------------------------------------
# Stage 5 - names
# --------------------------------------------------------------------------
def clean_names(tables, report):
    """Collapse doubled designators, de-duplicate labels, cascade into payee."""
    changes = {'designators_collapsed': [], 'duplicates_disambiguated': [],
               'payee_cascaded': 0}

    def fix(folder, fn, id_col, name_col):
        key = f"{folder}/{fn}"
        if key not in tables:
            return {}
        header, rows = tables[key]
        if name_col not in header or id_col not in header:
            return {}
        ic, nc = header.index(id_col), header.index(name_col)

        for row in rows:                                    # 5a: designators
            new = collapse_designators(row[nc])
            if new != row[nc]:
                changes['designators_collapsed'].append(
                    {'table': key, 'id': row[ic], 'from': row[nc], 'to': new})
                row[nc] = new

        taken = {}                                          # 5b: duplicate labels
        for row in sorted(rows, key=lambda x: x[ic]):
            name = row[nc]
            if name in taken:
                new = f"{name} ({row[ic]})"
                changes['duplicates_disambiguated'].append(
                    {'table': key, 'id': row[ic], 'from': name, 'to': new,
                     'shared_with': taken[name]})
                row[nc] = new
            else:
                taken[name] = row[ic]
        return {row[ic]: row[nc] for row in rows}

    vendor_name = fix('procurement', 'procurement_vendors.csv', 'vendor_id', 'vendor_name')
    partner_name = fix('PFI Partner Portal', 'pfi_partners.csv', 'partner_id', 'partner_name')

    # 5c: cascade into finance_payments.payee via the FOREIGN KEYS, never by
    # matching on the old name (two vendors could share one label).
    pk = 'finance/finance_payments.csv'
    need = ['procurement/procurement_invoices.csv', 'Lending/lending_disbursements.csv',
            'Lending/lending_approvals.csv', 'Lending/lending_applications.csv']
    if pk in tables and all(n in tables for n in need):
        def as_dicts(key):
            h, rws = tables[key]
            return [dict(zip(h, r)) for r in rws]

        inv_vendor = {r['invoice_id']: r['vendor_id'] for r in as_dicts(need[0])}
        dsb_apr = {r['disbursement_id']: r['approval_id'] for r in as_dicts(need[1])}
        apr_app = {r['approval_id']: r['application_id'] for r in as_dicts(need[2])}
        app_pfi = {r['application_id']: r['pfi_id'] for r in as_dicts(need[3])}

        header, rows = tables[pk]
        pi = header.index('payee')
        di = header.index('disbursement_id')
        ii = header.index('invoice_id')
        for row in rows:
            want = None
            if row[ii]:
                want = vendor_name.get(inv_vendor.get(row[ii]))
            elif row[di]:
                pfi = app_pfi.get(apr_app.get(dsb_apr.get(row[di])))
                want = partner_name.get(pfi)
            if want and want != row[pi]:
                row[pi] = want
                changes['payee_cascaded'] += 1

    report['names'] = {
        'designators_collapsed': len(changes['designators_collapsed']),
        'duplicates_disambiguated': len(changes['duplicates_disambiguated']),
        'payee_values_cascaded': changes['payee_cascaded'],
        'examples': changes['designators_collapsed'][:8],
        'duplicate_examples': changes['duplicates_disambiguated'],
    }


# --------------------------------------------------------------------------
# Driver
# --------------------------------------------------------------------------
def main():
    here = os.path.dirname(os.path.abspath(__file__))
    ap = argparse.ArgumentParser(description='Clean the ZDF mock dataset.')
    ap.add_argument('--root', default=here, help='dataset root (default: script dir)')
    ap.add_argument('--out', default=None, help='write to this folder instead of in place')
    ap.add_argument('--no-names', action='store_true', help='skip Stage 5 (name cleanup)')
    ap.add_argument('--dry-run', action='store_true', help='report only, write nothing')
    ap.add_argument('--skip-validate', action='store_true', help='skip Stage 6')
    ap.add_argument('--report', default='clean_report.json')
    args = ap.parse_args()

    root = os.path.abspath(args.root)
    dest = os.path.abspath(args.out) if args.out else root
    in_place = dest == root
    files = discover(root)
    if not files:
        print(f"No CSVs found under {root}", file=sys.stderr)
        return 1

    report = {'root': root, 'destination': dest, 'in_place': in_place,
              'dry_run': args.dry_run, 'files': {}}

    print(f"ZDF dataset cleaner  ->  {len(files)} tables under {root}\n")

    # ---- Stages 1-4
    tables = {}
    for folder, fn, path in files:
        header, rows = read_csv(path)
        before = len(rows)
        header, rows = clean_table(folder, fn, header, rows, report)
        tables[f"{folder}/{fn}"] = (header, rows)
        r = report['files'][f"{folder}/{fn}"]
        touched = sum(sum(v.values()) for k, v in r.items() if isinstance(v, dict)
                      and k not in ('date_format_mixed',))
        print(f"  {folder}/{fn:<44s} {before:>7,} rows  {touched:>8,} cells normalised")

    # ---- Stage 5
    if args.no_names:
        report['names'] = 'skipped (--no-names)'
        print("\n  Stage 5 skipped (--no-names)")
    else:
        clean_names(tables, report)
        n = report['names']
        print(f"\n  Stage 5 names: {n['designators_collapsed']} suffixes collapsed, "
              f"{n['duplicates_disambiguated']} duplicate labels disambiguated, "
              f"{n['payee_values_cascaded']} payee values cascaded")

    if args.dry_run:
        print("\n  --dry-run: nothing written")
        with open(os.path.join(root, args.report), 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2)
        return 0

    # ---- back up originals so Stage 6 can roll back
    backup = None
    if in_place:
        backup = tempfile.mkdtemp(prefix='zdf_preclean_')
        for folder, fn, path in files:
            os.makedirs(os.path.join(backup, folder), exist_ok=True)
            shutil.copy2(path, os.path.join(backup, folder, fn))

    # ---- Stage 7 write
    for folder, fn, path in files:
        header, rows = tables[f"{folder}/{fn}"]
        write_csv(os.path.join(dest, folder, fn), header, rows)
    print(f"\n  Written to {dest} (LF line endings, UTF-8 no BOM)")

    # ---- Stage 6 validate, roll back on failure
    verifier = os.path.join(root, VERIFIER)
    if args.skip_validate or not os.path.exists(verifier):
        report['validation'] = 'skipped'
        print("  Stage 6 validation skipped")
    else:
        print("\n  Stage 6: re-running relationship checks ...")
        proc = subprocess.run([sys.executable, verifier, dest],
                              capture_output=True, text=True)
        tail = [l for l in proc.stdout.splitlines() if 'PASS /' in l or l.startswith('FAIL')]
        for l in tail:
            print("   ", l)
        # the verifier exits non-zero when any check fails, so its return code is
        # the authority; a crash (empty output) must also count as a failure.
        passed = proc.returncode == 0 and bool(tail)
        report['validation'] = {'passed': passed, 'returncode': proc.returncode,
                                'summary': tail,
                                'stderr': proc.stderr.strip().splitlines()[-12:]}
        if not passed:
            print("\n  VALIDATION FAILED - rolling back", file=sys.stderr)
            if proc.stderr.strip():
                print("  verifier stderr:", file=sys.stderr)
                for l in proc.stderr.strip().splitlines()[-12:]:
                    print("   ", l, file=sys.stderr)
            if backup:
                for folder, fn, path in files:
                    shutil.copy2(os.path.join(backup, folder, fn), path)
                print("  originals restored", file=sys.stderr)
            with open(os.path.join(root, args.report), 'w', encoding='utf-8') as f:
                json.dump(report, f, indent=2)
            return 1

    with open(os.path.join(root, args.report), 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2)
    print(f"\n  Report: {args.report}")
    if backup:
        shutil.rmtree(backup, ignore_errors=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
