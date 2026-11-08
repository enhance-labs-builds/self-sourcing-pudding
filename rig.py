#!/usr/bin/env python3
"""Turn an editable sourcing brief and local source records into a reviewed shortlist."""

import argparse
import csv
import hashlib
import json
import re
import sys
import tomllib
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit


EXAMPLE = Path(__file__).resolve().parent / "examples" / "preview-environments"
CHANNELS = {"linkedin", "x"}
SOURCE_KINDS = {"post", "comment", "reply", "quote"}
EVIDENCE_KINDS = {"firsthand_problem", "explicit_work"}
CSV_FIELDS = (
    "name", "role", "company", "profile_url", "role_checked_on", "evidence_kind",
    "source_url", "published_on", "excerpt", "reason", "history_status",
)


def nonempty(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} needs text.")
    return value.strip()


def values(value, label, required=True):
    if not isinstance(value, list) or (required and not value):
        raise ValueError(f"{label} needs a list{' with at least one item' if required else ''}.")
    return list(dict.fromkeys(nonempty(item, label) for item in value))


def read_brief(path):
    with path.open("rb") as file:
        brief = tomllib.load(file)
    if brief.get("schema_version") != 1:
        raise ValueError("Set schema_version = 1 in the brief.")
    for key in ("product", "problem", "qualifies", "more_like", "less_like"):
        brief[key] = nonempty(brief.get(key), key)
    for key in ("target_roles", "signals", "alternatives", "exclusions"):
        brief[key] = values(brief.get(key, []), key, key in {"target_roles", "signals"})
    limits = brief.get("limits", {})
    for key in ("source_age_days", "role_age_days", "shortlist_size"):
        value = limits.get(key)
        if type(value) is not int or value < 1:
            raise ValueError(f"limits.{key} must be a positive whole number.")
    return brief


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def queue_digest(queue):
    data = json.dumps(queue, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def replay_decisions(path, queue):
    previous = read_json(path)
    if previous.get("queue_sha256") != queue_digest(queue):
        raise ValueError("These decisions belong to a different queue. Review the current queue.")
    return previous["decisions"]


def prompt(label, example=None):
    if example:
        print(f"  Example: {example}")
    return input(f"{label}: ").strip()


def init_brief(path, example):
    if path.exists():
        raise ValueError(f"{path} already exists. Edit it or choose another path.")
    if example:
        contents = (EXAMPLE / "brief.toml").read_text(encoding="utf-8")
    else:
        fields = [
            ("product", "What do you build?", "A tool that makes preview deployments reliable", False, True),
            ("problem", "What problem or workflow do you want to find?", "Preview environments break or take too long to spin up", False, True),
            ("target_roles", "Who does or owns this work? Use commas", "Platform Engineer, Developer Experience, DevOps", True, True),
            ("signals", "What phrases would those people use? Use commas", "preview deploy, preview environment, staging bottleneck", True, True),
            ("alternatives", "Competitors, alternatives, or workarounds? Use commas or leave blank", "BranchDock, deploy script, shared staging", True, False),
            ("exclusions", "Who or what should be passed over? Use commas or leave blank", "generic launch praise, vendor staff promoting their tool", True, False),
            ("qualifies", "What evidence would qualify someone?", "They describe owning or doing this work on a software team", False, True),
            ("more_like", "Give one example of a good fit", "An engineer explaining how they debug their team's failed preview deploys", False, True),
            ("less_like", "Give one example of a near miss", "A platform engineer sharing a product launch with no account of their own work", False, True),
        ]
        lines = ["schema_version = 1", ""]
        for key, label, hint, multiple, required in fields:
            answer = prompt(label, hint)
            while required and not answer:
                answer = prompt("Enter a value")
            value = [item.strip() for item in answer.split(",") if item.strip()] if multiple else answer
            while required and not value:
                value = [item.strip() for item in prompt("Enter at least one term").split(",") if item.strip()]
            # JSON string and string-list syntax is valid TOML with Unicode left intact.
            encoded = json.dumps(value, ensure_ascii=False).replace("\x7f", "\\u007f")
            lines.append(f"{key} = {encoded}")
        lines.extend(("", "[limits]", "source_age_days = 30", "role_age_days = 90", "shortlist_size = 10"))
        contents = "\n".join(lines) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as file:
        file.write(contents)
    print(f"Saved {path}. Edit it anytime, then run plan to preview your search.")


def show_plan(brief):
    print(f"Product: {brief['product']}\nProblem: {brief['problem']}")
    print(f"Prioritize roles: {', '.join(brief['target_roles'])}")
    print(f"Search signals: {', '.join(brief['signals'])}")
    print(f"Also search for: {', '.join(brief['alternatives']) or '(none)'}")
    print(f"Qualify when: {brief['qualifies']}")
    print(f"Pass over: {', '.join(brief['exclusions']) or '(none listed)'}")
    print(f"More like: {brief['more_like']}\nLess like: {brief['less_like']}")
    limits = brief["limits"]
    print(f"Limits: {limits['source_age_days']} days for sources, "
          f"{limits['role_age_days']} days for role checks, {limits['shortlist_size']} shortlisted.")


def match_terms(text, terms):
    return [
        term for term in terms
        if re.search(r"(?<!\w)" + re.escape(term.casefold()) + r"(?!\w)", text.casefold())
    ]


def checked_url(value, label):
    value = nonempty(value, label)
    url = urlsplit(value)
    if url.scheme != "https" or not url.hostname or url.username is not None:
        raise ValueError(f"{label} must be an HTTPS URL without credentials.")
    return value


def index_records(records, label):
    index = {}
    for record in records:
        key = nonempty(record["id"], f"{label} id")
        if key != record["id"] or key in index:
            raise ValueError(f"Invalid or duplicate {label} id: {key}")
        index[key] = record
    return index


def age_hold(stamp, as_of, limit, subject):
    if stamp is None:
        return f"{subject} date is missing."
    age = (as_of - date.fromisoformat(stamp)).days
    if age < 0:
        return f"{subject} is dated after the run."
    if age > limit:
        return f"{subject} is {age} days old; limit is {limit}."
    return None


def build_queue(brief, corpus, as_of=None):
    if corpus.get("schema_version") != 1:
        raise ValueError("The corpus needs schema_version 1.")
    as_of = date.fromisoformat(as_of or corpus["as_of"])
    people = index_records(corpus["people"], "person")
    observations = index_records(corpus["observations"], "source")
    profiles = set()
    for person in people.values():
        for key in ("name", "role", "company"):
            nonempty(person[key], key)
        profile = checked_url(person["profile_url"], "profile_url").rstrip("/").casefold()
        if profile in profiles:
            raise ValueError("A profile appears under multiple person IDs; reconcile its aliases first.")
        profiles.add(profile)

    matches = {}
    source_urls = set()
    terms = list(dict.fromkeys(brief["signals"] + brief["alternatives"]))
    for key, source in observations.items():
        if source["channel"] not in CHANNELS or source["kind"] not in SOURCE_KINDS:
            raise ValueError(f"Unsupported channel or source type for {key}.")
        url = checked_url(source["url"], "source url")
        if url in source_urls:
            raise ValueError(f"Duplicate source URL: {url}")
        source_urls.add(url)
        nonempty(source["author"], "source author")
        matches[key] = match_terms(nonempty(source["text"], "source text"), terms)
        if source.get("person_id") is not None and source["person_id"] not in people:
            raise ValueError(f"{key} points to an unknown person.")
        parent = source.get("parent_id")
        if parent is not None and (
            parent == key or parent not in observations or observations[parent].get("parent_id")
        ):
            raise ValueError(f"{key} needs an existing top-level parent source.")

    candidates = {}
    limits = brief["limits"]
    for key, source in observations.items():
        parent = source.get("parent_id")
        if not matches[key] and not matches.get(parent):
            continue
        person = people.get(source.get("person_id"))
        hint = source.get("profile_hint")
        if hint:
            checked_url(hint, "profile_hint")
        candidate_key = f"person:{person['id']}" if person else (
            f"profile:{hint}" if hint else f"source:{key}"
        )
        if candidate_key not in candidates:
            if person:
                hold = age_hold(person.get("role_checked_on"), as_of, limits["role_age_days"], "Role check")
            elif hint:
                hold = "Post links to a professional profile, but no single current role was verified."
            else:
                hold = "Author has no verified profile binding."
            candidates[candidate_key] = {
                "id": candidate_key, "person": person, "hold": hold, "sources": [],
                "role_matches": match_terms(person["role"], brief["target_roles"]) if person else [],
            }
        candidates[candidate_key]["sources"].append({
            **source,
            "matches": matches[key],
            "parent_matches": matches.get(parent, []),
            "hold": age_hold(source.get("published_on"), as_of, limits["source_age_days"], "Source"),
        })

    ranked = sorted(candidates.values(), key=lambda row: (
        bool(candidate_hold(row)), not row["role_matches"],
        not any(source["matches"] for source in row["sources"]), row["id"],
    ))
    return {"schema_version": 1, "as_of": as_of.isoformat(), "brief": brief, "candidates": ranked}


def candidate_hold(candidate):
    if candidate["hold"]:
        return candidate["hold"]
    if all(source["hold"] for source in candidate["sources"]):
        if len(candidate["sources"]) == 1:
            return candidate["sources"][0]["hold"]
        return "No current source in the queue. Check the dates on this candidate's sources."
    return None


def interactive_review(queue):
    print(f"Reviewing {len(queue['candidates'])} candidates as of {queue['as_of']}.")
    show_plan(queue["brief"])
    decisions = {}
    for row in queue["candidates"]:
        print()
        person = row["person"]
        print(f"{person['name']} · {person['role']} · {person['company']}" if person else row["sources"][0]["author"])
        if person:
            print(f"  Profile: {person['profile_url']}")
        usable = []
        for source in row["sources"]:
            if source["hold"]:
                label = f"Held: {source['hold']}"
            else:
                usable.append(source)
                label = str(len(usable))
            print(f"  [{label}] {source['channel']} {source['kind']} · {source.get('published_on') or 'unknown date'}")
            print(f"      {source['text']}\n      {source['url']}")
        hold = candidate_hold(row)
        if hold:
            print(f"  Held: {hold}")
            continue
        choice = prompt("Choose [f]irsthand problem, explicit [w]ork, [h]old, [p]ass, or Enter to skip").lower()
        while choice not in {"f", "w", "h", "p", ""}:
            choice = prompt("Choose f, w, h, p, or Enter to skip").lower()
        if not choice:
            continue
        if choice in {"h", "p"}:
            decisions[row["id"]] = {
                "decision": "hold" if choice == "h" else "pass",
                "reason": required_prompt("What needs checking?" if choice == "h" else "Why pass?"),
            }
            continue
        number = prompt("Which source proves the fit? Enter its number")
        while not number.isascii() or not number.isdecimal() or not 1 <= int(number) <= len(usable):
            number = prompt(f"Enter a number from 1 to {len(usable)}")
        source = usable[int(number) - 1]
        excerpt = prompt("Paste the exact excerpt, or press Enter to use the full source") or source["text"]
        while excerpt not in source["text"]:
            excerpt = required_prompt("Copy an exact excerpt from the selected source")
        decisions[row["id"]] = {
            "decision": "qualify", "source_id": source["id"], "excerpt": excerpt,
            "evidence_kind": "firsthand_problem" if choice == "f" else "explicit_work",
            "reason": required_prompt("How does this connect the person to the work in the brief?"),
        }
    return decisions


def required_prompt(label):
    result = prompt(label)
    while not result:
        result = prompt("Enter a reason or excerpt")
    return result


def apply_reviews(queue, decisions):
    candidates = {row["id"]: row for row in queue["candidates"]}
    if set(decisions) - set(candidates):
        raise ValueError("Decisions include IDs outside this queue. Review the current queue first.")
    results, shortlist = [], []
    limit = queue["brief"]["limits"]["shortlist_size"]
    for key, row in candidates.items():
        decision = decisions.get(key)
        hold = candidate_hold(row)
        if hold and decision and decision["decision"] == "qualify":
            raise ValueError(f"{key} cannot qualify: {hold}")
        if hold:
            outcome, reason = "held", hold
        elif decision is None:
            outcome, reason = "unreviewed", "Waiting for a fit decision."
        else:
            reason = nonempty(decision["reason"], f"{key} review reason")
            action = decision["decision"]
            if action in {"hold", "pass"}:
                outcome = "held" if action == "hold" else "passed"
            elif action == "qualify":
                source = next((item for item in row["sources"] if item["id"] == decision["source_id"]), None)
                if not source or source["hold"]:
                    raise ValueError(f"{key} needs a current source attributed to this person.")
                excerpt = nonempty(decision["excerpt"], f"{key} evidence excerpt")
                if excerpt not in source["text"] or decision["evidence_kind"] not in EVIDENCE_KINDS:
                    raise ValueError(f"{key} needs an exact excerpt and a supported evidence kind.")
                if len(shortlist) < limit:
                    person = row["person"]
                    shortlist.append({
                        **{field: person[field] for field in ("name", "role", "company", "profile_url", "role_checked_on")},
                        "person_id": person["id"], "evidence_kind": decision["evidence_kind"],
                        "source_url": source["url"], "published_on": source["published_on"],
                        "excerpt": excerpt, "reason": reason, "history_status": "unchecked",
                        "sightings": [
                            {"channel": item["channel"], "url": item["url"]} for item in row["sources"]
                        ],
                    })
                    outcome = "shortlisted"
                else:
                    outcome = "over_limit"
            else:
                raise ValueError(f"Unknown decision for {key}: {action}")
        person = row["person"]
        results.append({
            "id": key, "name": person["name"] if person else row["sources"][0]["author"],
            "outcome": outcome, "reason": reason,
        })
    return results, shortlist


def csv_value(value):
    # Prevent imported strings from being evaluated as spreadsheet formulas.
    if value.lstrip().startswith(("=", "+", "-", "@")) or value.startswith(("\t", "\r", "\n")):
        return "'" + value
    return value


def write_results(run, queue, decisions):
    results, shortlist = apply_reviews(queue, decisions)
    write_json(run / "review.json", {
        "as_of": queue["as_of"], "queue_sha256": queue_digest(queue),
        "decisions": decisions, "outcomes": results,
    })
    write_json(run / "shortlist.json", {"as_of": queue["as_of"], "leads": shortlist})
    with (run / "shortlist.csv").open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows({key: csv_value(row[key]) for key in CSV_FIELDS} for row in shortlist)
    for row in results:
        print(f"{row['outcome']:>11}  {row['name']}: {row['reason']}")
    print(f"\n{len(shortlist)} shortlisted. See {run / 'shortlist.csv'} and {run / 'shortlist.json'}.")


def new_run(path, queue):
    try:
        path.mkdir(parents=True)
    except FileExistsError:
        raise ValueError(f"{path} already exists. Choose a fresh run directory.") from None
    write_json(path / "queue.json", queue)


def main(argv=None):
    cli = argparse.ArgumentParser(description=__doc__)
    commands = cli.add_subparsers(dest="command", required=True)
    demo = commands.add_parser("demo", help="run the fictional example end to end")
    demo.add_argument("--out", type=Path, default=Path("runs/demo"))
    setup = commands.add_parser("init", help="write an editable brief")
    setup.add_argument("--brief", type=Path, default=Path("brief.toml"))
    setup.add_argument("--example", action="store_true", help="start with the filled-in example")
    plan = commands.add_parser("plan", help="show search terms and qualification criteria")
    plan.add_argument("--brief", type=Path, default=Path("brief.toml"))
    source = commands.add_parser("source", help="find candidates in a local corpus")
    source.add_argument("--brief", type=Path, default=Path("brief.toml"))
    source.add_argument("--corpus", type=Path, default=EXAMPLE / "corpus.json")
    source.add_argument("--out", type=Path, required=True)
    source.add_argument("--as-of", metavar="YYYY-MM-DD", help="override the corpus snapshot date")
    live = commands.add_parser("live", help="build a review queue from public posts using Treg")
    live.add_argument("--brief", type=Path, default=Path("brief.toml"))
    live.add_argument("--out", type=Path, required=True)
    live.add_argument("--budget-usd", required=True, help="maximum Treg spend for this run, up to $1")
    live.add_argument("--searches", type=int, choices=range(1, 5), default=2, metavar="1–4",
                      help="number of queries per channel")
    live.add_argument("--profiles", type=int, choices=range(11), default=4, metavar="0–10",
                      help="maximum independent LinkedIn role lookups")
    live.add_argument("--dry-run", action="store_true", help="preview the queries and cap offline")
    live.add_argument("--resume", action="store_true", help="reuse completed calls in the same run")
    review = commands.add_parser("review", help="review a queue and export a shortlist")
    review.add_argument("--run", type=Path, required=True)
    review.add_argument("--decisions", type=Path, help="replay a review.json from the same queue")
    args = cli.parse_args(argv)

    try:
        if args.command == "init":
            init_brief(args.brief, args.example)
        elif args.command == "plan":
            show_plan(read_brief(args.brief))
        elif args.command == "source":
            queue = build_queue(read_brief(args.brief), read_json(args.corpus), args.as_of)
            new_run(args.out, queue)
            print(f"Queued {len(queue['candidates'])} candidates in {args.out / 'queue.json'}.")
        elif args.command == "live":
            from treg_adapter import atomic_json, run_live

            brief = read_brief(args.brief)
            corpus = run_live(brief, args, match_terms)
            if corpus is not None:
                queue = build_queue(brief, corpus)
                atomic_json(args.out / "queue.json", queue)
                print(f"Queued {len(queue['candidates'])} candidates. Run review to make fit decisions.")
        elif args.command == "review":
            queue = read_json(args.run / "queue.json")
            decisions = replay_decisions(args.decisions, queue) if args.decisions else interactive_review(queue)
            write_results(args.run, queue, decisions)
        elif args.command == "demo":
            brief = read_brief(EXAMPLE / "brief.toml")
            queue = build_queue(brief, read_json(EXAMPLE / "corpus.json"))
            new_run(args.out, queue)
            show_plan(brief)
            print()
            write_results(args.out, queue, read_json(EXAMPLE / "decisions.json"))
    except (OSError, ValueError, TypeError, AttributeError, KeyError) as error:
        cli.exit(2, f"rig: {error}\n")
    except (EOFError, KeyboardInterrupt):
        cli.exit(130, "\nStopped. No new decisions were exported.\n")


if __name__ == "__main__":
    main()
