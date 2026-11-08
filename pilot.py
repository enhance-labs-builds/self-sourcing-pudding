"""Keep the approved brief, candidate previews, and feedback together."""

import hashlib
import json
import re
from argparse import Namespace
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from treg_adapter import atomic_json, billing, linkedin_profile, run_live
from url_seed import discover_seed


FIRSTHAND = re.compile(r"\b(?:we (?:use|built|run|tested|tried|migrated)|our (?:team|production|customers))\b", re.I)


def setup_commands(commands):
    pilot = commands.add_parser("pilot", help="go from a company URL to a saved candidate review")
    steps = pilot.add_subparsers(dest="step", required=True)
    start = steps.add_parser("start", help="read a company URL and create an editable draft")
    start.add_argument("url")
    start.add_argument("--website", help="company website when starting from a LinkedIn or X profile")
    start.add_argument("--starter", type=Path, help="use a researched TOML brief as the draft")
    start.add_argument("--target", type=int, default=100, help="maximum candidates for a full batch")
    approve = steps.add_parser("approve", help="approve this exact version of the brief")
    approve.add_argument("--yes", action="store_true", help="record an explicit approval without a prompt")
    run = steps.add_parser("run", help="collect up to 20 candidates, or run a larger batch")
    run.add_argument("--run", required=True, help="a name for this run")
    run.add_argument("--budget-usd", default="0.10")
    run.add_argument("--searches", type=int, choices=range(1, 21), metavar="1–20")
    run.add_argument("--profiles", type=int, choices=range(0, 501), metavar="0–500")
    run.add_argument("--pages", type=int, choices=range(1, 6), metavar="1–5", default=1,
                     help="LinkedIn pages per query")
    run.add_argument("--results-per-search", type=int, choices=range(1, 51), metavar="1–50",
                     help="results to examine per page on both channels")
    run.add_argument("--batch", action="store_true", help="use the approved full batch target")
    run.add_argument("--resume", action="store_true")
    run.add_argument("--corpus", type=Path, help="preview previously collected records offline")
    run.add_argument("--identities", type=Path, help="reviewed links between social authors and LinkedIn profiles")
    review = steps.add_parser("review", help="record yay or nay and remember the reason")
    review.add_argument("--run", required=True)
    review.add_argument("--votes", type=Path, help="record decisions from a JSON file")
    email = steps.add_parser("enrich", help="look up work email after a confirmed LinkedIn non-reply")
    email.add_argument("--run", required=True)
    email.add_argument("--events", type=Path, required=True)
    email.add_argument("--budget-usd", required=True)
    email.add_argument("--dry-run", action="store_true")
    email.add_argument("--resume", action="store_true")
    steps.add_parser("status", help="show the approval and saved feedback")
    for step in (start, approve, run, review, email, steps.choices["status"]):
        step.add_argument("--project", type=Path, required=True)
    return steps


def draft(seed, target):
    description = seed["description"]
    host = urlsplit(seed["website"]).hostname
    data = {
        "schema_version": 1,
        "product": f"{description} {seed['website']}",
        "problem": f"Describe the workflow someone would use {seed['title']} for.",
        "target_roles": ["Choose who owns this workflow"],
        "signals": [host],
        "alternatives": list(seed.get("comparisons", {})),
        "exclusions": ["Vendor announcements without firsthand evidence"],
        "qualifies": "The person describes doing, operating, or evaluating the workflow for their team.",
        "more_like": "A practitioner describes their team's work and a concrete constraint.",
        "less_like": "Someone repeats a product announcement without describing their own work.",
    }
    text = f"{seed['title']} {description}".lower()
    if "agent" in text and ("sandbox" in text or re.search(r"\bvms?\b", text)):
        data["problem"] = "Teams running AI agents need isolated execution with the tooling and persistence their workloads require."
        data["target_roles"] = ["Platform Engineer", "Infrastructure Engineer", "Engineering Lead", "CTO", "Founder"]
        data["signals"] = ["agent sandbox", "sandbox infrastructure", "persistent sandbox", "AI agents"]
    lines = ["# Roles, problem and search terms are hypotheses. Edit them before approval.",
             *[f"{key} = {json.dumps(value, ensure_ascii=False)}" for key, value in data.items()]]
    if data["signals"] != [host]:
        lines.extend(("", "[[searches]]", 'lane = "problem"', f'phrase = "{data["signals"][0]}"'))
        for competitor in data["alternatives"][:3]:
            lines.extend(("", "[[searches]]", 'lane = "alternative"', f'phrase = "{competitor}"',
                          'workflow = ["sandbox", "coding agent", "code execution"]',
                          f'seed_url = "{seed["comparisons"][competitor]}"'))
    lines.extend(("", "[limits]", "source_age_days = 45", "role_age_days = 30",
                  "shortlist_size = 20", f"batch_target = {target}"))
    return "\n".join(lines) + "\n"


def start_project(args, rig):
    if not 1 <= args.target <= 500:
        raise ValueError("Set a full batch target between 1 and 500.")
    seed = discover_seed(args.url, args.website)
    if args.starter:
        starter = rig.read_brief(args.starter)
        body = args.starter.read_text(encoding="utf-8")
        if "batch_target" not in starter["limits"]:
            # The editable limit belongs under [limits] even when more tables follow it.
            body = re.sub(r"(?m)^\[limits\]\s*$", f"[limits]\nbatch_target = {args.target}", body, count=1)
        body = re.sub(r"(?m)^shortlist_size\s*=.*$", "shortlist_size = 20", body, count=1)
    else:
        body = draft(seed, args.target)
    args.project.mkdir(mode=0o700, parents=True)
    (args.project / ".gitignore").write_text("*\n", encoding="utf-8")
    (args.project / "runs").mkdir()
    (args.project / "brief.toml").write_text(body, encoding="utf-8")
    atomic_json(args.project / "state.json", {"seed": seed, "approval": None, "feedback": {}})
    print(f"Company: {seed['title']}\nWebsite: {seed['website']}\n{seed['description']}")
    for channel in ("linkedin", "x"):
        print(f"{channel}: {seed['linked_profiles'].get(channel, 'no company link found on the site')}")
    rig.show_plan(rig.read_brief(args.project / "brief.toml"))
    print(f"Review or edit {args.project / 'brief.toml'}, then run pilot approve.")


@contextmanager
def locked_project(project, rig):
    import fcntl

    with (project / ".lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield rig.read_json(project / "state.json")


def brief_version(brief):
    encoded = json.dumps(brief, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def approve(args, state, rig):
    brief = rig.read_brief(args.project / "brief.toml")
    if "Choose who owns this workflow" in brief["target_roles"] or brief["problem"].startswith("Describe the workflow someone would use "):
        raise ValueError("Fill in the workflow and target roles in brief.toml before approving.")
    rig.show_plan({**brief, "limits": {**brief["limits"], "shortlist_size": 20}})
    print(f"Review preview: up to 20 people. Full batch target: {brief['limits']['batch_target']}.")
    if not args.yes and input("Approve this version? [y/N] ").strip().lower() not in {"y", "yes"}:
        print("Edit brief.toml and approve when it is ready.")
        return
    state["approval"] = {"version": brief_version(brief), "approved_at": utc_now()}
    atomic_json(args.project / "state.json", state)
    print("Approved. Use pilot run to start a capped preview.")


def run_path(project, name):
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", name):
        raise ValueError("Use a short run name with letters, digits, hyphens or underscores.")
    return project / "runs" / name


def feedback_key(row):
    source = row["sources"][0]
    profile = (row["person"] or {}).get("profile_url") or source.get("profile_hint")
    if profile:
        return "profile:" + (linkedin_profile(profile) or profile.rstrip("/").casefold())
    if source["channel"] == "x":
        return "x:" + source["author"].casefold()
    return "source:" + source["url"]


def select_preview(queue, feedback, limit, rig):
    known = []
    held = []
    seen = 0
    for row in queue["candidates"]:
        history = feedback.get(feedback_key(row))
        sources = {source["url"] for source in row["sources"]}
        person = row["person"] or {}
        durable = history and (history["reason_code"] == "duplicate"
                               or history["reason_code"] == "wrong_role" and person.get("role") == history.get("role")
                               or history["reason_code"] == "wrong_account" and person.get("company") == history.get("company"))
        if history and (durable
                        or sources.issubset(history["seen_sources"])):
            seen += 1
            continue
        if history:
            row = {**row, "previous_feedback": history["vote"]}
        if person and not linkedin_profile(person["profile_url"]):
            row = {**row, "hold": "The author has no verified LinkedIn profile."}
        (held if rig.candidate_hold(row) else known).append(row)
    # Keep the person with attributable, current evidence ahead of a name needing research.
    known.sort(key=lambda row: (
        bool(row["role_matches"]),
        any(FIRSTHAND.search(source["text"]) for source in row["sources"] if not source["hold"]),
        max(source["published_on"] for source in row["sources"] if not source["hold"]),
    ), reverse=True)
    return known[:limit], held, seen


def channel_status(ledger, adapter):
    coverage = {}
    for channel, endpoint in (("linkedin", adapter.LINKEDIN), ("x", adapter.X)):
        calls = [call for call in ledger["calls"].values() if call["endpoint"] == endpoint]
        ok = sum("result" in call for call in calls)
        planned = len(ledger["plan"]["terms"])
        if channel == "linkedin":
            planned *= ledger["plan"].get("linkedin_pages", 1)
        coverage[channel] = {"succeeded": ok, "attempted": len(calls), "planned": planned,
                             "status": "complete" if planned and ok == planned else "partial" if ok else "unavailable"}
    return coverage


def run_preview(args, state, rig):
    import treg_adapter

    brief = rig.read_brief(args.project / "brief.toml")
    version = brief_version(brief)
    if not state["approval"] or state["approval"]["version"] != version:
        raise ValueError("Approve the current brief before running a preview.")
    out = run_path(args.project, args.run)
    limit = brief["limits"]["batch_target"] if args.batch else 20
    if out.exists() and (not args.resume or (out / "preview.json").exists() or args.corpus):
        raise ValueError("Choose a fresh run name. Resume is for interrupted live runs.")
    run_brief = {**brief, "limits": {**brief["limits"], "shortlist_size": limit}}
    if args.corpus:
        corpus = rig.read_json(args.corpus)
        stats = {"mode": "replay", "spend_usd": 0, "snapshot": corpus["as_of"]}
    else:
        count = args.searches or min(len(brief.get("searches", [])) or 2, 20)
        options = Namespace(searches=count, budget_usd=args.budget_usd,
                            profiles=args.profiles if args.profiles is not None else limit,
                            out=out, resume=args.resume, dry_run=False, pages=args.pages,
                            results_per_search=args.results_per_search or (30 if args.batch else 12))
        corpus = run_live(run_brief, options, rig.match_terms, rig.discovery_terms(run_brief))
        ledger = rig.read_json(out / "treg-run.json")
        stats = {"mode": "live", "spend_usd": billing(ledger) / 1_000_000,
                 "channels": channel_status(ledger, treg_adapter)}
    if args.identities:
        attach_identities(corpus, rig.read_json(args.identities), rig)
    queue = rig.build_queue(run_brief, corpus)
    cards, held, seen = select_preview(queue, state["feedback"], limit, rig)
    queue = {**queue, "candidates": cards, "brief_version": version}
    if args.corpus:
        rig.new_run(out, queue)
    else:
        atomic_json(out / "queue.json", queue)
    atomic_json(out / "holds.json", {"candidates": held})
    stats.update({"run": args.run, "brief_version": version, "max_candidates": limit,
                  "candidates": len(cards), "held": len(held), "already_reviewed": seen,
                  "observations": len(corpus["observations"])})
    atomic_json(out / "preview.json", stats)
    print(f"Preview: {len(cards)}/{limit} candidates with a current LinkedIn role and source, {len(held)} held. "
          f"Open {out / 'queue.json'} or run pilot review.")


def attach_identities(corpus, identities, rig):
    people = {p["profile_url"].rstrip("/").casefold(): p for p in corpus["people"]}
    sources = {row["url"]: row for row in corpus["observations"]}
    for identity in identities:
        source = sources.get(identity["source_url"])
        if not source or source["author"] != identity["author"]:
            raise ValueError("An identity link must name an exact source URL and author in this run.")
        url = linkedin_profile(identity["profile_url"])
        if not url:
            raise ValueError("A reviewed identity needs a canonical LinkedIn profile.")
        if source.get("profile_hint") and linkedin_profile(source["profile_hint"]) != url:
            raise ValueError("The supplied LinkedIn profile conflicts with the author's profile on the source.")
        person = people.get(url)
        if not person:
            person = {field: identity[field] for field in ("name", "company", "role", "role_checked_on")}
            person.update(id="linkedin:" + url.rsplit("/", 1)[-1], profile_url=url)
            people[url] = person
        if source.get("person_id") and source["person_id"] != person["id"]:
            raise ValueError("The source already belongs to a different verified identity.")
        source["person_id"] = person["id"]
        for field in ("binding_source", "role_source"):
            source[field] = rig.checked_url(identity[field], field)
    corpus["people"] = list(people.values())


def interactive_votes(queue):
    votes = {}
    for row in queue["candidates"]:
        person = row["person"]
        print(f"\n{person['name']} · {person['role']} · {person['company']}\n{person['profile_url']}" if person
              else f"\n{row['sources'][0]['author']}")
        sources = [source for source in row["sources"] if not source["hold"]]
        for i, source in enumerate(sources, 1):
            excerpt = re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", "", source["text"][:650])
            print(f"  {i}. {source['channel']} · {source.get('published_on') or 'date unknown'} · {source['url']}\n"
                  f"     {excerpt}")
        action = input("[y] yay, [n] nay, Enter to skip, [q] save and quit: ").strip().lower()
        if action == "q":
            break
        if action == "n":
            print("Reasons: wrong_role, wrong_account, weak_evidence, duplicate, other")
            code = input("Reason code [weak_evidence]: ").strip() or "weak_evidence"
            votes[row["id"]] = {"vote": "nay", "reason_code": code}
        if action == "y":
            i = input("Which source proves the fit? [1] ").strip() or "1"
            while not i.isascii() or not i.isdecimal() or not 1 <= int(i) <= len(sources):
                i = input(f"Choose a source from 1 to {len(sources)}: ").strip()
            source = sources[int(i) - 1]
            spans = [span.strip() for span in re.split(r"\n+|(?<=[.!?])\s+", source["text"]) if span.strip()]
            suggested = next((span for span in spans if FIRSTHAND.search(span)), spans[0])[:240].rstrip()
            visible = re.sub(r"[\x00-\x1f\x7f]", "", suggested)
            print(f"Suggested evidence: {visible}")
            excerpt = input("Enter to use that evidence, or paste a different exact excerpt: ").strip() or suggested
            while not excerpt or excerpt not in source["text"]:
                excerpt = input("Paste an exact excerpt from that source: ").strip()
            reason = input("Why is this a fit? [Reviewed as a fit] ").strip() or "Reviewed as a fit for this brief."
            kind = input("[p] firsthand problem, [w] explicit work [w]: ").strip()
            votes[row["id"]] = {"vote": "yay", "source_id": source["id"], "excerpt": excerpt,
                                "evidence_kind": "firsthand_problem" if kind == "p" else "explicit_work", "reason": reason}
    return votes


def review(args, state, rig):
    out = run_path(args.project, args.run)
    queue = rig.read_json(out / "queue.json")
    if not (out / "preview.json").exists():
        raise ValueError("Finish the preview before reviewing it.")
    if not state["approval"] or queue["brief_version"] != state["approval"]["version"]:
        raise ValueError("This preview belongs to a different approved brief. Run a new preview.")
    rows = {row["id"]: row for row in queue["candidates"]}
    votes = rig.read_json(args.votes) if args.votes else interactive_votes(queue)
    decisions = {}
    updates = {}
    for key, vote in votes.items():
        if key not in rows or vote.get("vote") not in {"yay", "nay"}:
            raise ValueError("Each vote needs a candidate in this preview and a yay or nay decision.")
        row = rows[key]
        code = vote.get("reason_code", "other" if vote["vote"] == "yay" else "weak_evidence")
        if code not in {"wrong_role", "wrong_account", "weak_evidence", "duplicate", "other"}:
            raise ValueError("Unknown feedback reason code.")
        label = feedback_key(row)
        previous = updates.get(label, state["feedback"].get(label, {}))
        sources = sorted(set(previous.get("seen_sources", [])) | {item["url"] for item in row["sources"]})
        decision = {"decision": "qualify" if vote["vote"] == "yay" else "pass",
                    "reason": vote.get("reason") or code.replace("_", " ")}
        if vote["vote"] == "yay":
            decision.update({field: vote[field] for field in ("source_id", "excerpt", "evidence_kind")})
            code = "other"
        updates[label] = {"vote": vote["vote"], "reason_code": code, "reason": decision["reason"],
                          "seen_sources": sources, "run": args.run, "brief_version": queue["brief_version"],
                          "role": row["person"]["role"], "company": row["person"]["company"], "updated_at": utc_now()}
        decisions[key] = decision
    existing = out / "review.json"
    if existing.exists():
        decisions = {**rig.replay_decisions(existing, queue), **decisions}
    rig.write_results(out, queue, decisions)
    state["feedback"].update(updates)
    atomic_json(args.project / "state.json", state)
    print(f"Saved {len(updates)} votes for future runs.")


def execute(args, rig):
    if args.step == "start":
        start_project(args, rig)
        return
    with locked_project(args.project, rig) as state:
        if args.step == "status":
            brief = rig.read_brief(args.project / "brief.toml")
            approved = state["approval"] and state["approval"]["version"] == brief_version(brief)
            votes = list(state["feedback"].values())
            print(f"Brief: {'approved' if approved else 'awaiting approval'}. Full batch target: {brief['limits']['batch_target']}.")
            print(f"Saved feedback: {sum(v['vote'] == 'yay' for v in votes)} yay, "
                  f"{sum(v['vote'] == 'nay' for v in votes)} nay. Automation: off.")
        elif args.step == "enrich":
            from work_email import enrich

            enrich(args, state, rig, run_path(args.project, args.run))
        else:
            {"approve": approve, "run": run_preview, "review": review}[args.step](args, state, rig)
