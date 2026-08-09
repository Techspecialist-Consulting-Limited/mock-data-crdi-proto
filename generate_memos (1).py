#!/usr/bin/env python3
"""
ZDF memo register generator.
Produces two tables:
  memos.csv                 — the register, all three memo types
  memo_approval_steps.csv   — one row per approval action, approval requests only
"""
import csv, random, os
from datetime import date, timedelta

random.seed(4102)
OUT = "/home/claude/memogen/out"
os.makedirs(OUT, exist_ok=True)

END   = date(2026, 8, 4)      # demonstration date
START = date(2025, 8, 5)      # 12 months

MD_THRESHOLD = 15_000_000     # above this, the MD must sign

DEPTS = [
    "Lending Operations", "Risk & Compliance", "Finance & Treasury",
    "Procurement & Logistics", "IT & Infrastructure", "Human Resources",
    "Growth & Strategy", "Executive Office",
]

HEAD_TITLE = {
    "Lending Operations":      "Head of Lending Operations",
    "Risk & Compliance":       "Head of Risk & Compliance",
    "Finance & Treasury":      "Head of Finance & Treasury",
    "Procurement & Logistics": "Head of Procurement",
    "IT & Infrastructure":     "Head of ICT",
    "Human Resources":         "Head of Human Resources",
    "Growth & Strategy":       "Head of Growth & Strategy",
    "Executive Office":        "Head, Executive Office",
}

STAFF = [
    "Adaeze Okonkwo", "Ibrahim Bello", "Funmi Adeyemi", "Chinedu Eze",
    "Halima Sani", "Tunde Balogun", "Ngozi Chukwu", "Yusuf Danjuma",
    "Blessing Ekanem", "Musa Garba", "Kemi Oladele", "Emeka Nwosu",
    "Aisha Lawal", "Segun Ogunleye", "Grace Ibekwe", "Bashir Aliyu",
    "Comfort Akinwale", "Mark Uche", "Zainab Yakubu", "Peter Adeniyi",
]

HEADS = {
    "Lending Operations":      "Adaeze Okonkwo",
    "Risk & Compliance":       "Bashir Aliyu",
    "Finance & Treasury":      "Kemi Oladele",
    "Procurement & Logistics": "Ibrahim Bello",
    "IT & Infrastructure":     "Emeka Nwosu",
    "Human Resources":         "Grace Ibekwe",
    "Growth & Strategy":       "Funmi Adeyemi",
    "Executive Office":        "Peter Adeniyi",
}

MD_NAME = "Dr. Amina Bello"

# ---------------------------------------------------------------- subjects
# (subject, department, category, typical value or None)
APPROVAL = [
    ("Request for approval: external audit engagement", "Finance & Treasury", "Financial", 47_800_000),
    ("Approval of Q3 partner monitoring field visits", "Lending Operations", "Operational", None),
    ("Variation to facility management contract", "Procurement & Logistics", "Procurement", 12_400_000),
    ("Approval to extend partner onboarding window", "Lending Operations", "Partner", None),
    ("Request for approval: core banking licence renewal", "IT & Infrastructure", "Procurement", 61_200_000),
    ("Approval of revised credit assessment criteria", "Risk & Compliance", "Policy", None),
    ("Request for approval: regional office lease renewal", "Procurement & Logistics", "Administrative", 28_900_000),
    ("Approval of staff promotion schedule", "Human Resources", "HR", None),
    ("Request for approval: data platform subscription", "IT & Infrastructure", "Procurement", 19_600_000),
    ("Approval to write off non-performing exposures", "Risk & Compliance", "Financial", 84_500_000),
    ("Request for approval: partner capacity workshop", "Lending Operations", "Partner", 31_400_000),
    ("Approval of legal retainer renewal", "Executive Office", "Administrative", 9_800_000),
    ("Request for approval: impact evaluation consultancy", "Growth & Strategy", "Procurement", 22_700_000),
    ("Approval of secondment to supervising ministry", "Human Resources", "HR", None),
    ("Request for exception to procurement threshold", "Procurement & Logistics", "Procurement", 15_300_000),
    ("Approval of annual insurance renewal", "Finance & Treasury", "Financial", 18_200_000),
    ("Request for approval: disbursement to new PFI cohort", "Lending Operations", "Financial", 180_000_000),
    ("Approval of study leave application", "Human Resources", "HR", None),
    ("Request for approval: server capacity expansion", "IT & Infrastructure", "Procurement", 34_100_000),
    ("Approval to suspend a partner institution", "Risk & Compliance", "Partner", None),
    ("Request for approval: quarterly board pack printing", "Executive Office", "Administrative", 2_400_000),
    ("Approval of revised per diem rates", "Finance & Treasury", "Policy", None),
    ("Request for approval: market research engagement", "Growth & Strategy", "Procurement", 8_900_000),
    ("Approval of contract award — vehicle maintenance", "Procurement & Logistics", "Procurement", 6_700_000),
    ("Request for approval: regional outreach programme", "Growth & Strategy", "Operational", 42_600_000),
    ("Approval of recruitment for vacant credit officer roles", "Human Resources", "HR", None),
    ("Request for approval: disaster recovery site", "IT & Infrastructure", "Procurement", 96_400_000),
    ("Approval to release retention on completed contract", "Finance & Treasury", "Financial", 11_500_000),
    ("Request for approval: partner performance incentive", "Lending Operations", "Partner", 25_800_000),
    ("Approval of policy exception — single source award", "Procurement & Logistics", "Policy", None),
]

DIRECTIVE = [
    ("Revised delegation of authority thresholds", "Finance & Treasury", "Policy"),
    ("Updated staff travel and per diem policy", "Human Resources", "HR"),
    ("Mandatory data protection refresher training", "Risk & Compliance", "Policy"),
    ("Revised partner reporting submission calendar", "Lending Operations", "Partner"),
    ("Updated information security access policy", "IT & Infrastructure", "Policy"),
    ("Revised expense claim procedure", "Finance & Treasury", "Financial"),
    ("New whistleblowing reporting channel", "Executive Office", "Policy"),
    ("Updated procurement documentation standards", "Procurement & Logistics", "Procurement"),
    ("Revised credit file retention requirements", "Risk & Compliance", "Policy"),
    ("Updated leave application procedure", "Human Resources", "HR"),
    ("Mandatory quarterly reconciliation of partner returns", "Lending Operations", "Operational"),
    ("Revised vendor compliance verification steps", "Procurement & Logistics", "Procurement"),
    ("Updated business continuity procedures", "IT & Infrastructure", "Operational"),
    ("Revised delegation for regional office spending", "Finance & Treasury", "Financial"),
]

INFORMATIONAL = [
    ("Notification: revised office operating hours", "Human Resources", "Administrative"),
    ("Update on regional office relocation", "Procurement & Logistics", "Administrative"),
    ("Quarterly portfolio performance briefing", "Lending Operations", "Operational"),
    ("Notification: scheduled system maintenance", "IT & Infrastructure", "Operational"),
    ("Update on supervising ministry engagement", "Executive Office", "Administrative"),
    ("Board meeting outcomes summary", "Executive Office", "Administrative"),
    ("Notification: audit fieldwork commencement", "Risk & Compliance", "Operational"),
    ("Update on partner onboarding pipeline", "Growth & Strategy", "Partner"),
    ("Notification: revised bank mandate signatories", "Finance & Treasury", "Financial"),
    ("Staff wellness programme announcement", "Human Resources", "HR"),
    ("Update on data platform rollout", "IT & Infrastructure", "Operational"),
    ("Notification: public holiday working arrangements", "Human Resources", "Administrative"),
]

ACTION = {
    "Approval Request": "Approval required",
    "Directive": "Compliance required",
    "Informational": "For information",
}

def rdate(a, b):
    return a + timedelta(days=random.randint(0, (b - a).days))

def workday(d):
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d

def vary(base):
    return round(base * random.uniform(0.55, 1.65), -4)

# ---------------------------------------------------------------- build
memos, steps = [], []
mseq = sseq = 0

# 600 memos: 45% approval, 30% directive, 25% informational
plan = (["Approval Request"] * 270) + (["Directive"] * 180) + (["Informational"] * 150)
random.shuffle(plan)

for mtype in plan:
    mseq += 1
    sub_d = workday(rdate(START, END))
    mid = f"MEM-{sub_d.year}-{mseq:05d}"

    if mtype == "Approval Request":
        subject, dept, category, base = random.choice(APPROVAL)
        amount = "" if base is None else f"{vary(base):.2f}"
        addressed = "Managing Director"
    elif mtype == "Directive":
        subject, dept, category = random.choice(DIRECTIVE)
        amount = f"{vary(3_500_000):.2f}" if random.random() < 0.05 else ""
        addressed = random.choice(["All Staff", "Heads of Department"])
    else:
        subject, dept, category = random.choice(INFORMATIONAL)
        amount = ""
        addressed = "All Staff"

    raiser = HEADS[dept] if random.random() < 0.35 else random.choice(STAFF)

    def core(txt):
        """Strip the leading ask so the purpose line doesn't stutter."""
        t = txt.split(":")[-1].strip()
        for pre in ("Request for approval", "Approval to", "Approval of",
                    "Approval", "Notification", "Update on"):
            if t.lower().startswith(pre.lower()):
                t = t[len(pre):].strip(" -—:")
                break
        return t[0].lower() + t[1:] if t else txt.lower()

    body = core(subject)
    purpose = {
        "Approval Request": f"To seek executive approval for {body}.",
        "Directive":        f"To notify all affected staff of the revised position on {body}, and the date it takes effect.",
        "Informational":    f"To inform staff regarding {body}.",
    }[mtype]

    deadline = (sub_d + timedelta(days=random.choice([7, 10, 14, 21, 30]))).isoformat() \
        if random.random() < 0.65 else ""

    memo = dict(
        memo_id=mid, memo_type=mtype, subject=subject, addressed_to=addressed,
        raised_by=raiser, originating_department=dept, purpose_statement=purpose,
        category=category, amount_ngn=amount, action_required=ACTION[mtype],
        response_deadline=deadline, submitted_date=sub_d.isoformat(),
    )

    # ---- non-approval types are issued and never enter a chain
    if mtype != "Approval Request":
        memo.update(current_stage="Issued", current_approver_role="",
                    last_action_date=sub_d.isoformat())
        memos.append(memo)
        continue

    # ================= approval chain =================
    head_role = HEAD_TITLE[dept]
    head_name = HEADS[dept]
    age = (END - sub_d).days
    val = float(amount) if amount else 0.0
    needs_md = val >= MD_THRESHOLD or (val == 0 and random.random() < 0.60)

    # ---- step 1: submission
    sseq += 1
    steps.append(dict(step_id=f"STP-{sseq:06d}", memo_id=mid, step_number=1,
                      step_name="Submission", approver_role="Originator",
                      approver_name=raiser, status="Submitted",
                      action_date=sub_d.isoformat(),
                      comments="Documentation attached and submitted for review."))

    # ---- pending at head? only recent memos
    if age <= 11 and random.random() < 0.55:
        sseq += 1
        steps.append(dict(step_id=f"STP-{sseq:06d}", memo_id=mid, step_number=2,
                          step_name="Departmental Recommendation", approver_role=head_role,
                          approver_name=head_name, status="Pending", action_date="",
                          comments=""))
        memo.update(current_stage="Awaiting head", current_approver_role=head_role,
                    last_action_date=sub_d.isoformat())
        memos.append(memo)
        continue

    # ---- step 2: head decision
    head_d = workday(sub_d + timedelta(days=random.randint(1, 8)))
    if head_d > END:
        head_d = END
    head_ok = random.random() < 0.90
    sseq += 1
    steps.append(dict(step_id=f"STP-{sseq:06d}", memo_id=mid, step_number=2,
                      step_name="Departmental Recommendation", approver_role=head_role,
                      approver_name=head_name,
                      status="Recommended" if head_ok else "Returned",
                      action_date=head_d.isoformat(),
                      comments="Reviewed and recommended for executive decision." if head_ok
                               else "Returned to originator — supporting documentation incomplete."))

    if not head_ok:
        memo.update(current_stage="Rejected", current_approver_role="",
                    last_action_date=head_d.isoformat())
        memos.append(memo)
        continue

    if not needs_md:
        memo.update(current_stage="Approved", current_approver_role="",
                    last_action_date=head_d.isoformat())
        memos.append(memo)
        continue

    # ---- step 3: MD decision
    head_age = (END - head_d).days
    still_open = head_age <= 30 and random.random() < 0.62

    if still_open:
        sseq += 1
        steps.append(dict(step_id=f"STP-{sseq:06d}", memo_id=mid, step_number=3,
                          step_name="Executive Decision", approver_role="Managing Director",
                          approver_name=MD_NAME, status="Pending", action_date="",
                          comments=""))
        memo.update(current_stage="Awaiting MD", current_approver_role="Managing Director",
                    last_action_date=head_d.isoformat())
        memos.append(memo)
        continue

    md_d = workday(head_d + timedelta(days=random.randint(1, 15)))
    if md_d > END:
        md_d = END
    md_ok = random.random() < 0.88
    sseq += 1
    steps.append(dict(step_id=f"STP-{sseq:06d}", memo_id=mid, step_number=3,
                      step_name="Executive Decision", approver_role="Managing Director",
                      approver_name=MD_NAME,
                      status="Approved" if md_ok else "Declined",
                      action_date=md_d.isoformat(),
                      comments="Approved for implementation." if md_ok
                               else "Declined — to be re-presented with revised costing."))
    memo.update(current_stage="Approved" if md_ok else "Rejected",
                current_approver_role="", last_action_date=md_d.isoformat())
    memos.append(memo)

# ---------------------------------------------------------------- write
MEMO_COLS = ["memo_id","memo_type","subject","addressed_to","raised_by",
             "originating_department","purpose_statement","category","amount_ngn",
             "action_required","response_deadline","current_stage",
             "current_approver_role","submitted_date","last_action_date"]
STEP_COLS = ["step_id","memo_id","step_number","step_name","approver_role",
             "approver_name","status","action_date","comments"]

def write(name, rows, cols):
    with open(os.path.join(OUT, name), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader(); w.writerows(rows)
    print(f"  {name:28s} {len(rows):>5,} rows")

memos.sort(key=lambda m: m["submitted_date"])
write("memos.csv", memos, MEMO_COLS)
write("memo_approval_steps.csv", steps, STEP_COLS)

# ---------------------------------------------------------------- check
from collections import Counter
print("\n" + "="*60)
print("REGISTER CHECK")
print("="*60)

print("Memo type:")
for t, c in Counter(m["memo_type"] for m in memos).most_common():
    print(f"  {t:<20} {c:>4}  ({c/len(memos)*100:.0f}%)")

print("\nCurrent stage:")
for t, c in Counter(m["current_stage"] for m in memos).most_common():
    print(f"  {t:<20} {c:>4}")

valued = [m for m in memos if m["amount_ngn"]]
print(f"\nCarrying a value        : {len(valued)} of {len(memos)}  ({len(valued)/len(memos)*100:.0f}%)")
print(f"Total value             : NGN {sum(float(m['amount_ngn']) for m in valued)/1e9:.2f}bn")

print("\n" + "="*60)
print("MD METRICS")
print("="*60)
awaiting = [m for m in memos if m["current_stage"] == "Awaiting MD"]
aw_val = [m for m in awaiting if m["amount_ngn"]]
oldest = min((date.fromisoformat(m["last_action_date"]) for m in awaiting), default=END)
print(f"Awaiting my approval    : {len(awaiting)}")
print(f"  of which carry value  : {len(aw_val)}  =  NGN {sum(float(m['amount_ngn']) for m in aw_val)/1e6:,.1f}m")
print(f"  oldest waiting        : {(END-oldest).days} days")

md30 = [s for s in steps if s["approver_role"]=="Managing Director"
        and s["status"]=="Approved" and s["action_date"]
        and (END - date.fromisoformat(s["action_date"])).days <= 30]
print(f"Approved by MD, 30 days : {len(md30)}")

print("\nHEADS' METRIC — approved by me, now with someone else")
by_dept = Counter(m["originating_department"] for m in awaiting)
for d, c in by_dept.most_common():
    print(f"  {d:<26} {c:>3}")

print("\n" + "="*60)
print("CHAIN CHECK")
print("="*60)
appr = [m for m in memos if m["memo_type"]=="Approval Request"]
per = Counter()
for s in steps:
    per[s["memo_id"]] += 1
print(f"Approval requests       : {len(appr)}")
print(f"Steps generated         : {len(steps)}")
print(f"Avg steps per request   : {len(steps)/len(appr):.1f}")
print(f"Memos with 3 steps      : {sum(1 for v in per.values() if v==3)}")
print(f"Memos with 2 steps      : {sum(1 for v in per.values() if v==2)}")
print(f"Non-approval with steps : {sum(1 for m in memos if m['memo_type']!='Approval Request' and m['memo_id'] in per)}")
print("="*60)
