"""Optional work email lookup for reviewed leads after a LinkedIn non-reply."""

import os
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit

from treg_adapter import (Treg, VERIFY_EMAIL, WORK_EMAIL, atomic_json, billing, bounded_call, call_key,
                          dollars, journal, linkedin_profile, micro_dollars)
from url_seed import public_url


def due(event, now):
    if event.get("status") not in {"pending", "no_reply"} or not event.get("source_url"):
        return False
    try:
        sent = datetime.fromisoformat(event["linkedin_sent_at"])
        checked = datetime.fromisoformat(event["status_checked_at"])
    except (KeyError, ValueError, TypeError):
        return False
    return bool(sent.tzinfo and checked.tzinfo and now - sent >= timedelta(hours=72)
                and timedelta(0) <= now - checked <= timedelta(hours=24)
                and checked - sent >= timedelta(hours=72))


def work_address(data, profile, domain):
    output = data.get("output") or {}
    result = output.get("data") or {}
    if not output.get("found") or linkedin_profile(result.get("linkedinUrl")) != profile:
        return None
    addresses = set()
    for row in result.get("emails") or []:
        address = row.get("email", "").strip().casefold()
        local, _, host = address.rpartition("@")
        if (host == domain and re.fullmatch(r"[a-z0-9._+%-]+", local)
                and local not in {"hello", "info", "contact", "sales", "support", "admin", "team", "careers", "office"}):
            addresses.add(address)
    return next(iter(addresses)) if len(addresses) == 1 else None


def verified(data, address):
    record = data.get("data") or {}
    return (record.get("email", "").casefold() == address and record.get("status") == "valid"
            and record.get("accept_all") is False and record.get("webmail") is False)


def enrich(args, state, rig, out):
    queue = rig.read_json(out / "queue.json")
    if not state["approval"] or state["approval"]["version"] != queue["brief_version"]:
        raise ValueError("Work email requires a review on the currently approved brief.")
    decisions = rig.replay_decisions(out / "review.json", queue)
    _, leads = rig.apply_reviews(queue, decisions)
    now = datetime.now(timezone.utc)
    events = {}
    for event in rig.read_json(args.events):
        profile = linkedin_profile(event.get("profile_url"))
        if not profile or profile in events:
            raise ValueError("Provide one LinkedIn status record per exact profile URL.")
        events[profile] = event
    tasks = []
    for lead in leads:
        profile = linkedin_profile(lead["profile_url"])
        event = events.get(profile, {})
        if not due(event, now) or event.get("company", "").casefold() != lead["company"].casefold():
            continue
        limits = queue["brief"]["limits"]
        today = now.date()
        if (rig.age_hold(lead["role_checked_on"], today, limits["role_age_days"], "Role check")
                or rig.age_hold(lead["published_on"], today, limits["source_age_days"], "Source")):
            continue
        site = public_url(event["company_website"])
        tasks.append({"profile": profile, "domain": urlsplit(site).hostname.removeprefix("www."),
                      "company_website": site, "status_source": rig.checked_url(event["source_url"], "Status source")})
    budget = micro_dollars(args.budget_usd)
    print(f"Work email: {len(tasks)} eligible from {len(leads)} approved leads. Ceiling US${dollars(budget)}.")
    if args.dry_run or not tasks:
        return
    token, org = os.environ.get("TREG_TOKEN"), os.environ.get("TREG_ORG")
    if not token or not org:
        raise ValueError("Set TREG_TOKEN and TREG_ORG for your Treg team.")
    client = Treg(token, org)
    quotes = client.preflight({WORK_EMAIL, VERIFY_EMAIL})
    if budget < sum(quotes.values()):
        raise ValueError("The cap must cover one work email lookup and verification.")
    plan = {"tasks": tasks, "budget_micro": budget, "brief_version": queue["brief_version"]}
    target = out / "work-email"
    with journal(target, plan, org, args.resume) as (path, ledger):
        if "checked_at" not in ledger:
            ledger["checked_at"] = now.isoformat()
            atomic_json(path, ledger)
        results = []
        for task in tasks:
            lookup = {"profileUrl": task["profile"]}
            if call_key(WORK_EMAIL, lookup) not in ledger["calls"] and budget - billing(ledger) < sum(quotes.values()):
                results.append({"profile_url": task["profile"], "status": "budget_limit"})
                continue
            address = bounded_call(client, path, ledger, WORK_EMAIL, lookup,
                                   quotes[WORK_EMAIL], lambda data: work_address(data, task["profile"], task["domain"]))
            if (address and call_key(VERIFY_EMAIL, {"email": address}) not in ledger["calls"]
                    and budget - billing(ledger) < quotes[VERIFY_EMAIL]):
                results.append({"profile_url": task["profile"], "status": "budget_limit"})
                continue
            valid = address and bounded_call(client, path, ledger, VERIFY_EMAIL, {"email": address},
                                             quotes[VERIFY_EMAIL], lambda data: verified(data, address))
            row = {"profile_url": task["profile"], "status": "verified" if valid else "no_verified_work_email"}
            if valid:
                row.update(email=address, company_website=task["company_website"], checked_at=ledger["checked_at"])
            results.append(row)
        atomic_json(target / "results.json", {"spend_usd": billing(ledger) / 1_000_000, "results": results})
        print(f"Saved {sum(row['status'] == 'verified' for row in results)} verified work emails in {target}.")
