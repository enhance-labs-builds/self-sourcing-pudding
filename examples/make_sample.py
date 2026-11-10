#!/usr/bin/env python3
"""Write the sample shortlist from a fictional run, using the same code a real run uses.

Every person, company, post and address in it is invented. Run from the repository folder:
    python3 examples/make_sample.py
"""

from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pudding
import treg as t

QUOTED = '"spreadsheets" "our approvals"'


def post(number, author, headline, text, channel="linkedin"):
    host = "x.example" if channel == "x" else "linkedin.example"
    return {"id": f"P{number:04d}", "channel": channel, "kind": "post", "author": author, "headline": headline, "text": text,
            "url": f"https://{host}/posts/{author.split()[0].lower()}", "published_on": f"2026-11-0{number}",
            "profile": f"https://profiles.example/{author.split()[0].lower()}", "found_by": [QUOTED]}


POSTS = [
    post(1, "Nia Alder", "Head of Procurement at Juniper Vale Software",
         "I run procurement intake at Juniper Vale. Purchase approvals kept getting stuck between Slack and a spreadsheet, "
         "so we piloted one request form with finance and IT last week."),
    post(2, "Priya Rowan", "Procurement Operations Manager at Ashmere Hospitality",
         "Our approvals contract is up for renewal in March and we're evaluating alternatives. "
         "Suppliers still send tax forms to three different inboxes."),
    post(3, "Mara Holt", "Procurement Operations Manager",
         "I own our purchase order process. Three teams were rekeying the same request, so I'm testing whether approved "
         "requests can create the order automatically.", channel="x"),
    post(4, "Tomas Reyes", "Controller at Brindle Freight",
         "We moved every purchase approval into our ERP last quarter. It took four months and I would not do it again."),
    post(5, "Sal Okoro", "Finance Lead at Larkfield Foods",
         "We run all of our approvals through Juniper Approvals now and month-end is two days shorter."),
    post(6, "Wren", "", "Our approvals live in a shared inbox and I am the bottleneck on every one of them.", channel="x"),
]
GRADES = {
    "P0001": {"verdict": "prospect", "fit": "strong", "why": "Owns procurement intake and is changing it now.",
              "quote": "Purchase approvals kept getting stuck between Slack and a spreadsheet, so we piloted one request form "
                       "with finance and IT last week."},
    "P0002": {"verdict": "prospect", "fit": "strong", "why": "Owns vendor onboarding and is choosing a replacement before a renewal.",
              "quote": "Our approvals contract is up for renewal in March and we're evaluating alternatives."},
    "P0003": {"verdict": "prospect", "fit": "look", "why": "Owns purchase orders and is testing automation.",
              "quote": "Three teams were rekeying the same request", "labels": ["employer not named in post", "found on X"]},
    "P0004": {"verdict": "prospect", "fit": "low", "why": "Just finished a four-month move to another system.",
              "quote": "We moved every purchase approval into our ERP last quarter.", "labels": ["just chose a competitor"]},
    "P0005": {"verdict": "customer", "why": "Already a customer.", "quote": "We run all of our approvals through Juniper Approvals now"},
    "P0006": {"verdict": "prospect", "fit": "look", "why": "Describes their own approvals bottleneck.", "labels": ["solo"],
              "quote": "Our approvals live in a shared inbox and I am the bottleneck on every one of them."},
}
JOB = {"id": "J001", "url": "https://jobs.example/hollis-bay-health/procurement-systems-lead", "company": "Hollis Bay Health",
       "title": "Procurement Systems Lead", "published_on": "2026-10-21", "found_by": ["procurement systems purchase approvals"],
       "text": "You will choose and roll out our first purchase-approvals system and own it afterwards."}
JOB_GRADES = {"J001": {"verdict": "mandate", "fit": "look", "labels": ["vendor not chosen"],
                       "quote": "You will choose and roll out our first purchase-approvals system",
                       "owner_titles": ["Head of Procurement"], "why": "The ad assigns choosing an approvals system to this hire."}}


def person(name, role, company, city, country):
    first, _, last = name.partition(" ")
    return {"name": name, "first_name": first, "last_name": last, "role": role, "company": company, "role_basis": "current role",
            "other_roles": [], "location": city, "country": country,
            "company_url": "https://profiles.example/company/" + company.split()[0].lower()}


def entry(index, verified, channel="linkedin", **more):
    return {"channel": channel, "source_url": POSTS[index]["url"], "hold": None, "profile_url": POSTS[index]["profile"],
            "verified": verified, **more}


PEOPLE = {
    "P0001": entry(0, person("Nia Alder", "Head of Procurement", "Juniper Vale Software", "Leeds, United Kingdom", "GB"),
                   work_email={"status": "verified", "address": "nia.alder@junipervale.example"}, company_domain="junipervale.example"),
    "P0002": entry(1, person("Priya Rowan", "Procurement Operations Manager", "Ashmere Hospitality", "Austin, Texas", "US")),
    "P0003": entry(2, person("Mara Holt", "Procurement Operations Manager", "Oriole Dune Robotics", "Toronto, Canada", "CA"),
                   channel="x", identity_basis="web search: same name and orioledune"),
    "P0004": entry(3, person("Tomas Reyes", "Controller", "Brindle Freight", "Rotterdam, Netherlands", "NL")),
    "P0006": {"channel": "x", "source_url": POSTS[5]["url"], "verified": None, "x_name": "Wren",
              "hold": "No LinkedIn identity: the X profile shows no full name."},
    "J001": {"channel": "jobs", "source_url": JOB["url"], "hold": None, "profile_url": "https://profiles.example/idris",
             "verified": person("Idris Vale", "Head of Procurement", "Hollis Bay Health", "Denver, Colorado", "US"),
             "identity_basis": "named owner title"},
}


def build(folder):
    project = Path(folder)
    write = lambda name, value: t.atomic_json(project / name, value)
    write("project.json", {"url": "https://juniper-approvals.example/", "budget_micro": 1_000_000, "window_days": 45, "created": "2026-11-10"})
    write("plan.json", {
        "product": "Juniper Approvals, a fictional purchase-approvals tool.", "buyer": "Procurement and finance operations leads.",
        "qualifies": "The author describes their own team's purchase approvals.", "exclude_employers": ["Juniper Approvals"],
        "customers": ["Larkfield Foods"], "employer_topic": "procurement", "owner_titles": ["Head of Procurement"],
        "linkedin_queries": [f'"Tool{n}" "we switched"' for n in range(5)], "x_queries": [], "job_queries": JOB["found_by"]})
    write("posts.json", {row["id"]: row for row in POSTS})
    write("grades.json", GRADES)
    write("jobs.json", {"J001": JOB})
    write("job-grades.json", JOB_GRADES)
    write("people.json", PEOPLE)
    write("review.json", {POSTS[0]["profile"]: {"vote": "yes", "note": "Exactly who we sell to."}})
    (project / "ledger").mkdir()
    # Fourteen lookups: two searches, a job search, an owner search, six role checks and four email calls.
    write("ledger/treg-run.json", {"plan": {}, "org": "example", "id": "sample",
                                   "calls": {str(n): {"status": "settled", "cost_micro": 3000} for n in range(14)}})
    pudding.shortlist(project)
    note = ("# Sample shortlist\n\nEvery person, company, post and address here is fictional. "
            "`examples/make_sample.py` writes this file with the same code a real run uses.\n")
    page = (project / "shortlist.md").read_text(encoding="utf-8").replace("# Shortlist\n", note, 1)
    return page, (project / "shortlist.csv").read_text(encoding="utf-8")


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as folder:
        page, sheet = build(folder)
    here = Path(__file__).resolve().parent
    (here / "shortlist.md").write_text(page, encoding="utf-8")
    (here / "shortlist.csv").write_text(sheet, encoding="utf-8")
    print("Wrote examples/shortlist.md and examples/shortlist.csv.")
