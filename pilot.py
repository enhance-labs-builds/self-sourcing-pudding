"""Keep the approved brief, candidate previews, and feedback together."""

import hashlib
import json
import re
from argparse import Namespace
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from treg_adapter import FIRSTHAND, atomic_json, billing, linkedin_profile, linkedin_url, pending_calls, run_live
from url_seed import discover_seed, terminal_text


NAY_REASONS = ("wrong_role", "wrong_account", "weak_evidence", "duplicate", "other")


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
    run.add_argument("--target", type=int, metavar="1–500", help="maximum people to review in this run")
    run.add_argument("--spider", action="store_true", help="follow threads and search relevant employers")
    run.add_argument("--no-email", action="store_true", help="skip work email lookup and verification")
    run.add_argument("--dry-run", action="store_true", help="show this preview's search plan without credentials or spending")
    run.add_argument("--resume", action="store_true", help="continue the same live run and recover any pending call")
    run.add_argument("--corpus", type=Path, help="preview previously collected records offline")
    run.add_argument("--identities", type=Path, help="reviewed links between social authors and LinkedIn profiles")
    review = steps.add_parser("review", help="record yay or nay and remember the reason")
    review.add_argument("--run", required=True)
    review.add_argument("--votes", type=Path, help="record decisions from a JSON file")
    steps.add_parser("status", help="show the approval and saved feedback")
    for step in (start, approve, run, review, steps.choices["status"]):
        step.add_argument("--project", type=Path, required=True)
    return steps


def draft(seed, target, *, ask=None):
    description = seed["description"]
    host = urlsplit(seed["website"]).hostname
    data = {
        "schema_version": 1,
        "product": f"{description} {seed['website']}",
        "problem": f"Describe the workflow someone would use {seed['title']} for.",
        "target_roles": ["Choose who owns this workflow"],
        "signals": [host],
        "alternatives": list(seed.get("comparisons", {})),
        "company_signals": [],
        "derive_searches": True,
        "exclusions": ["Vendor announcements without firsthand evidence"],
        "qualifies": "The person describes doing, operating, or evaluating the workflow for their team.",
        "more_like": "A practitioner describes their team's work and a concrete constraint.",
        "less_like": "Someone repeats a product announcement without describing their own work.",
    }
    text = f"{seed['title']} {description} {seed.get('headings', '')}".lower()
    if "agent" in text and ("sandbox" in text or re.search(r"\bvms?\b", text)):
        data["problem"] = "Teams running AI agents need isolated execution with the tooling and persistence their workloads require."
        data["target_roles"] = ["Platform Engineer", "Infrastructure Engineer", "Engineering Lead", "CTO", "Founder"]
        data["signals"] = ["agent sandbox", "sandbox infrastructure", "persistent sandbox", "AI agents"]
    elif ("onboarding" in text or "implementation" in text) and ("customer" in text or "user" in text):
        data["problem"] = "Customer teams need to guide new users through setup and adoption without a live call for every account."
        data["target_roles"] = ["Head of Customer Success", "Director of Customer Success", "Customer Onboarding Lead", "Implementation Manager", "Product Growth Lead"]
        data["signals"] = ["customer onboarding", "guided onboarding", "onboarding calls", "time to value"]
        data["qualifies"] = "The person owns customer onboarding or adoption and describes a bottleneck, an experiment, or a rollout their team is working on."
    elif ask:
        print(terminal_text(f"\n{seed['title']}\n{description}\n{seed['website']}"))
        print("Use what you know about the people who do this work to finish the brief.")
        data["problem"] = ask("What problem or workflow should we look for?", required=True)
        data["target_roles"] = ask("Who does or owns that work? Separate roles with commas.", required=True, split=True)
        data["signals"] = ask("What phrases would they use in a post? Separate them with commas.", required=True, split=True)
        alternatives = ask("Any competitors or workarounds to search? Separate them with commas.", split=True)
        data["alternatives"] = list(dict.fromkeys(data["alternatives"] + alternatives))
        data["company_signals"] = ask("What kinds of companies should move up for review? Enter phrases or leave blank.",
                                      split=True)
    lines = ["# Roles, problem and search terms are hypotheses. Edit them before approval.",
             "# Use company_signals for phrases you would expect to see on a relevant employer’s public profile.",
             *[f"{key} = {json.dumps(value, ensure_ascii=False)}" for key, value in data.items()]]
    if seed.get("comparisons"):
        lines.extend(("", "[comparison_sources]"))
        for competitor, source in seed["comparisons"].items():
            lines.append(f"{json.dumps(competitor, ensure_ascii=False)} = {json.dumps(source)}")
    lines.extend(("", "[limits]", "source_age_days = 45", "role_age_days = 30",
                  "shortlist_size = 20", f"batch_target = {target}"))
    return "\n".join(lines) + "\n"


def start_project(args, rig, *, seed=None, show=True):
    if not 1 <= args.target <= 500:
        raise ValueError("Set a full batch target between 1 and 500.")
    if seed is None:
        seed = discover_seed(args.url, args.website)
    if args.starter:
        starter = rig.read_brief(args.starter)
        body = args.starter.read_text(encoding="utf-8")
        if "batch_target" not in starter["limits"]:
            # The editable limit belongs under [limits] even when more tables follow it.
            body = re.sub(r"(?m)^\[limits\]\s*$", f"[limits]\nbatch_target = {args.target}", body, count=1)
        body = re.sub(r"(?m)^shortlist_size\s*=.*$", "shortlist_size = 20", body, count=1)
    else:
        body = draft(seed, args.target, ask=getattr(args, "ask", None))
    args.project.mkdir(mode=0o700, parents=True)
    (args.project / ".gitignore").write_text("*\n", encoding="utf-8")
    (args.project / "runs").mkdir()
    (args.project / "brief.toml").write_text(body, encoding="utf-8")
    atomic_json(args.project / "state.json", {"seed": seed, "approval": None, "feedback": {}})
    print(terminal_text(f"Company: {seed['title']}\nWebsite: {seed['website']}\n{seed['description']}"))
    for channel in ("linkedin", "x"):
        print(f"{channel}: {seed['linked_profiles'].get(channel, 'no company link found on the site')}")
    if show:
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


def approve(args, state, rig, *, show=True):
    brief = rig.read_brief(args.project / "brief.toml")
    if "Choose who owns this workflow" in brief["target_roles"] or brief["problem"].startswith("Describe the workflow someone would use "):
        raise ValueError("Fill in the workflow and target roles in brief.toml before approving.")
    if show:
        rig.show_plan({**brief, "limits": {**brief["limits"], "shortlist_size": 20}})
        print(f"Review preview: up to 20 people. Full batch target: {brief['limits']['batch_target']}.")
    if not args.yes and input("Approve this version? [y/N] ").strip().lower() not in {"y", "yes"}:
        print("Edit brief.toml and approve when it is ready.")
        return
    state["approval"] = {"version": brief_version(brief), "approved_at": utc_now()}
    atomic_json(args.project / "state.json", state)
    print("Approved. Use pilot run to start a capped preview." if show else "Brief approved.")


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


def select_preview(queue, feedback, limit, rig, *, example=False):
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
            seen_sources = set(history["seen_sources"])
            row = {**row, "previous_feedback": history["vote"],
                   "sources": [source for source in row["sources"] if source["url"] not in seen_sources]}
        if person and not example and not linkedin_profile(person["profile_url"]):
            row = {**row, "hold": "The author has no verified LinkedIn profile."}
        (held if rig.candidate_hold(row) else known).append(row)
    # Keep the person with attributable, current evidence ahead of a name needing research.
    known.sort(key=rig.candidate_priority, reverse=True)
    return known[:limit], held, seen


def channel_status(ledger, adapter):
    coverage = {}
    for channel, endpoint in (("linkedin", adapter.LINKEDIN), ("x", adapter.X)):
        calls = [call for call in ledger["calls"].values()
                 if call["endpoint"] == endpoint and not call["params"].get("authorsCompany")]
        ok = sum("result" in call for call in calls)
        planned = len(ledger["plan"]["terms"])
        if channel == "linkedin":
            planned *= ledger["plan"].get("linkedin_pages", 1)
        coverage[channel] = {"succeeded": ok, "attempted": len(calls), "planned": planned,
                             "status": "complete" if planned and ok == planned else "partial" if ok else "unavailable"}
    return coverage


def run_preview(args, state, rig, *, example=None):
    import treg_adapter

    if args.spider and (args.corpus or example is not None):
        raise ValueError("Use --spider with a live search.")
    brief = rig.read_brief(args.project / "brief.toml")
    out = run_path(args.project, args.run)
    target = getattr(args, "target", None)
    if target is not None and (args.batch or not 1 <= target <= 500):
        raise ValueError("Use --target from 1 to 500 without --batch.")
    limit = target if target is not None else brief["limits"]["batch_target"] if args.batch else 20
    run_brief = {**brief, "limits": {**brief["limits"], "shortlist_size": limit}}
    count = args.searches or min(len(brief.get("searches", [])) or 2, 20)
    options = Namespace(searches=count, budget_usd=args.budget_usd,
                        profiles=args.profiles if args.profiles is not None else limit,
                        out=out, resume=args.resume, dry_run=args.dry_run, pages=args.pages, spider=args.spider,
                        results_per_search=args.results_per_search or (30 if args.batch else 12))
    if args.dry_run:
        if args.resume or args.corpus:
            raise ValueError("Use --dry-run to plan a new live preview.")
        run_live(run_brief, options, rig.match_terms, rig.discovery_terms(run_brief))
        if not args.no_email:
            print("The live preview also attempts work email lookup within the same spend limit.")
        return
    version = brief_version(brief)
    if not state["approval"] or state["approval"]["version"] != version:
        raise ValueError("Approve the current brief before running a preview.")
    previous = rig.read_json(out / "preview.json") if (out / "preview.json").exists() else None
    recovering_email = previous and previous["mode"] == "live" and previous.get("pending_spend_usd")
    if out.exists() and (not args.resume or (previous and not recovering_email) or args.corpus or example is not None):
        raise ValueError("Choose a fresh run name. Resume is for interrupted live runs.")
    if recovering_email and (previous["brief_version"] != version or previous["max_candidates"] != limit or args.no_email):
        raise ValueError("Resume work email using the original approved brief and run options.")
    identities = rig.read_json(args.identities) if args.identities else None
    prepared = None
    previous_decisions = None
    if recovering_email:
        # A saved preview can already have votes. Refresh only its emails, never its candidate list.
        queue = rig.read_json(out / "queue.json")
        previous_cards = queue, rig.read_json(out / "holds.json")["candidates"], previous["already_reviewed"]
        if (out / "review.json").exists():
            previous_decisions = rig.replay_decisions(out / "review.json", queue)

    def prepare(corpus):
        if identities:
            attach_identities(corpus, identities, rig)
        queue = rig.build_queue(run_brief, corpus)
        cards, held, seen = select_preview(queue, state["feedback"], limit, rig, example=example is not None)
        return {**queue, "candidates": cards, "brief_version": version}, held, seen

    def enrich(corpus, client, path, ledger, quotes):
        from work_email import enrich_candidates

        nonlocal prepared
        prepared = previous_cards if recovering_email else prepare(corpus)
        enrich_candidates(prepared[0]["candidates"], client, path, ledger, quotes)

    if example is not None:
        corpus = example
        stats = {"mode": "example", "spend_usd": 0, "snapshot": corpus["as_of"]}
    elif args.corpus:
        corpus = rig.read_json(args.corpus)
        stats = {"mode": "replay", "spend_usd": 0, "snapshot": corpus["as_of"]}
    else:
        corpus = run_live(run_brief, options, rig.match_terms, rig.discovery_terms(run_brief),
                          enrich=None if args.no_email else enrich)
        ledger = rig.read_json(out / "treg-run.json")
        stats = {"mode": "live", "spend_usd": billing(ledger) / 1_000_000,
                 "channels": channel_status(ledger, treg_adapter)}
        if args.spider:
            stats["followup_sources"] = sum(
                any(entry.get("lane") in {"thread", "employer"} for entry in source.get("found_by", []))
                for source in corpus["observations"]
            )
            print(f"Follow-up searches found {stats['followup_sources']} sources for the same review queue.")
        pending = sum(call["reserved_micro"] for call in pending_calls(ledger).values())
        if pending:
            stats["pending_spend_usd"] = pending / 1_000_000
    queue, held, seen = prepared if prepared is not None else prepare(corpus)
    cards = queue["candidates"]
    if example is not None:
        rig.mark_example_emails(queue)
    if args.corpus or example is not None:
        rig.new_run(out, queue)
    else:
        atomic_json(out / "queue.json", queue)
    atomic_json(out / "holds.json", {"candidates": held})
    stats.update({"run": args.run, "brief_version": version, "max_candidates": limit,
                  "candidates": len(cards), "held": len(held), "already_reviewed": seen,
                  "observations": len(corpus["observations"])})
    if prepared is not None:
        stats["verified_work_emails"] = sum(row["work_email"]["status"] == "verified" for row in cards)
        print(f"Verified work email: {stats['verified_work_emails']}/{len(cards)} candidates.")
    if previous_decisions is not None:
        rig.write_results(out, queue, previous_decisions)
    atomic_json(out / "preview.json", stats)
    if stats.get("pending_spend_usd"):
        print("Work email is still pending. You can review candidates now and resume this run later.")
    if seen:
        print(f"Skipped {seen} previously reviewed {'match' if seen == 1 else 'matches'}.")
    if example is not None:
        print(f"Example preview: {len(cards)} fictional candidates, {len(held)} held. Spend: US$0.")
    else:
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
        if identity.get("company_url"):
            company_url = linkedin_url(identity["company_url"], "company")
            if (not company_url or person.get("company_url", company_url) != company_url
                    or identity.get("company") != person["company"]):
                raise ValueError("The supplied employer page must match the person's confirmed current employer.")
            person["company_url"] = company_url
        if source.get("person_id") and source["person_id"] != person["id"]:
            raise ValueError("The source already belongs to a different verified identity.")
        source["person_id"] = person["id"]
        for field in ("binding_source", "role_source"):
            source[field] = rig.checked_url(identity[field], field)
    corpus["people"] = list(people.values())


def interactive_votes(queue, rig):
    votes = {}
    if queue.get("mode") == "example":
        print("\nExample candidates. Profiles, posts and work emails below are fictional.")
    for row in queue["candidates"]:
        person = row["person"]
        label = (f"\n{person['name']} · {person['role']} · {person['company']}\n{person['profile_url']}" if person
                 else f"\n{row['sources'][0]['author']}")
        print(terminal_text(label))
        if person and person.get("employer_signal"):
            print(terminal_text(f"  A colleague posted about this work: {person['employer_signal']['seed_url']}"))
        if person and (fit := person.get("company_fit")):
            print(terminal_text(f"  Company fit · {fit['excerpt'][:400]}\n  {fit['source_url']}"))
        if row.get("work_email", {}).get("status") == "verified":
            print(f"Verified work email: {row['work_email']['address']}")
        elif row.get("work_email", {}).get("status") == "example":
            print(f"Example work email: {row['work_email']['address']}")
        sources = [source for source in row["sources"] if not source["hold"]]
        for i, source in enumerate(sources, 1):
            print(terminal_text(
                f"  {i}. {source['channel']} · {source.get('published_on') or 'date unknown'} · {source['url']}\n"
                f"     {source['text'][:650]}"
            ))
            for discovery in source.get("found_by", []):
                if discovery.get("lane") == "thread":
                    print(terminal_text(f"     Found in the conversation on {discovery['seed_url']}"))
                elif discovery.get("lane") == "employer":
                    print(terminal_text(f"     Found by searching the employer of the author of {discovery['seed_url']}"))
        action = input("[y] yay, [n] nay, Enter to skip, [q] save and quit: ").strip().lower()
        if action == "q":
            break
        if action == "n":
            print("Reasons: " + ", ".join(NAY_REASONS))
            code = input("Reason code [weak_evidence]: ").strip() or "weak_evidence"
            while code not in NAY_REASONS:
                print("Choose one of: " + ", ".join(NAY_REASONS))
                code = input("Reason code [weak_evidence]: ").strip() or "weak_evidence"
            votes[row["id"]] = {"vote": "nay", "reason_code": code}
        if action == "y":
            qualify = input("Add to the shortlist using firsthand evidence? [y/N, Enter keeps for follow-up] ").strip().lower()
            if qualify not in {"y", "yes"}:
                votes[row["id"]] = {"vote": "yay", "reason": "Saved for follow-up. Firsthand evidence still needs review."}
                continue
            i = input("Which source proves the fit? [1] ").strip() or "1"
            while not i.isascii() or not i.isdecimal() or not 1 <= int(i) <= len(sources):
                i = input(f"Choose a source from 1 to {len(sources)}: ").strip()
            source = sources[int(i) - 1]
            body = source["text"].strip()
            spans = re.split(r"\n+|(?<=[.!?])\s+", body)
            first = next((span for span in spans if FIRSTHAND.search(span)), spans[0])
            start = body.find(first) if len(body) > 240 else 0
            suggested = body[start:start + 240].rstrip()
            print(terminal_text(f"Suggested evidence: {suggested}"))
            excerpt = input("Enter to use that evidence, or paste a different exact excerpt: ").strip() or suggested
            while not excerpt or excerpt not in source["text"]:
                excerpt = input("Paste an exact excerpt from that source: ").strip()
            reason = rig.required_prompt("Why does this person fit the brief?")
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
    existing = out / "review.json"
    saved = rig.replay_decisions(existing, queue) if existing.exists() else {}
    unreviewed = [row for row in queue["candidates"] if row["id"] not in saved]
    if not args.votes and not unreviewed:
        print("No new candidates to review.")
    votes = rig.read_json(args.votes) if args.votes else interactive_votes({**queue, "candidates": unreviewed}, rig)
    decisions = {}
    updates = {}
    for key, vote in votes.items():
        if key not in rows or vote.get("vote") not in {"yay", "nay"}:
            raise ValueError("Each vote needs a candidate in this preview and a yay or nay decision.")
        row = rows[key]
        code = vote.get("reason_code", "other" if vote["vote"] == "yay" else "weak_evidence")
        if code not in NAY_REASONS:
            raise ValueError("Unknown feedback reason code.")
        label = feedback_key(row)
        previous = updates.get(label, state["feedback"].get(label, {}))
        sources = sorted(set(previous.get("seen_sources", [])) | {item["url"] for item in row["sources"]})
        proof_fields = ("source_id", "excerpt", "evidence_kind")
        decision = {"decision": "pass", "reason": vote.get("reason") or code.replace("_", " ")}
        if vote["vote"] == "yay":
            proof = {field: vote[field] for field in proof_fields if field in vote}
            if proof and len(proof) != len(proof_fields):
                raise ValueError("To add a yay to the shortlist, include the source, exact excerpt, and evidence kind.")
            if proof:
                decision.update(proof, decision="qualify")
            else:
                decision.update(decision="hold", reason=vote.get("reason") or "Saved for follow-up. Firsthand evidence still needs review.")
            code = "other"
        updates[label] = {"vote": vote["vote"], "reason_code": code, "reason": decision["reason"],
                          "seen_sources": sources, "run": args.run, "brief_version": queue["brief_version"],
                          "role": row["person"]["role"], "company": row["person"]["company"], "updated_at": utc_now()}
        decisions[key] = decision
    decisions = {**saved, **decisions}
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
        else:
            {"approve": approve, "run": run_preview, "review": review}[args.step](args, state, rig)
