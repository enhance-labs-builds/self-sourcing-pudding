"""Find and verify work email for the strongest candidates in a sourcing run."""

import re
from urllib.parse import urlsplit

from treg_adapter import (COMPANY, EMAIL_ENDPOINTS, PER_CALL, VERIFY_EMAIL, WORK_EMAIL, billing, bounded_call,
                          call_key, linkedin_profile, linkedin_url)
from url_seed import public_url


def company_website(data, company_url):
    company = data.get("element") or {}
    website = company.get("website")
    if linkedin_url(company.get("linkedinUrl"), "company") != company_url or not isinstance(website, str) or not website:
        return None
    try:
        site = public_url(re.sub(r"^http://", "https://", website.strip(), flags=re.I))
    except ValueError:
        return None
    return {"url": site, "name": company.get("name") or ""}


def work_address(data, profile, domain):
    output = data.get("output") or {}
    result = output.get("data") or {}
    if not output.get("found") or linkedin_profile(result.get("linkedinUrl")) != profile:
        return None
    addresses = set()
    for row in result.get("emails") or []:
        address = (row.get("email") or "").strip().casefold()
        local, _, host = address.rpartition("@")
        if (host == domain and re.fullmatch(r"[a-z0-9._+%-]+", local)
                and local not in {"hello", "info", "contact", "sales", "support", "admin", "team", "careers", "office"}):
            addresses.add(address)
    return next(iter(addresses)) if len(addresses) == 1 else None


def verified(data, address):
    record = data.get("data") or {}
    return ((record.get("email") or "").casefold() == address and record.get("status") == "valid"
            and record.get("accept_all") is False and record.get("webmail") is False)


def candidate_email(person, client, path, ledger, quotes):
    profile = linkedin_profile(person["profile_url"])
    company_url = linkedin_url(person.get("company_url"), "company")
    if not company_url:
        return {"status": "employer_unconfirmed"}

    def remaining():
        return ledger["plan"]["budget_micro"] - billing(ledger)

    calls = ledger["calls"]
    company_params = {"url": company_url}
    if call_key(COMPANY, company_params) not in calls and remaining() < sum(PER_CALL[key] for key in EMAIL_ENDPOINTS):
        return {"status": "budget_limit"}
    site = bounded_call(client, path, ledger, COMPANY, company_params, quotes[COMPANY],
                        lambda data: company_website(data, company_url))
    if not site or " ".join(site["name"].split()).casefold() != " ".join(person["company"].split()).casefold():
        return {"status": "employer_unconfirmed"}
    domain = urlsplit(site["url"]).hostname.removeprefix("www.")
    profile_params = {"profileUrl": profile}
    if call_key(WORK_EMAIL, profile_params) not in calls and remaining() < PER_CALL[WORK_EMAIL] + PER_CALL[VERIFY_EMAIL]:
        return {"status": "budget_limit"}
    address = bounded_call(client, path, ledger, WORK_EMAIL, profile_params, quotes[WORK_EMAIL],
                           lambda data: work_address(data, profile, domain))
    if not address or address.rpartition("@")[2] != domain:
        return {"status": "no_matching_work_email"}
    address_params = {"email": address}
    if call_key(VERIFY_EMAIL, address_params) not in calls and remaining() < quotes[VERIFY_EMAIL]:
        return {"status": "budget_limit"}
    if not bounded_call(client, path, ledger, VERIFY_EMAIL, address_params, quotes[VERIFY_EMAIL],
                        lambda data: verified(data, address)):
        return {"status": "unverified"}
    return {"status": "verified", "address": address, "company_website": site["url"],
            "checked_on": ledger["as_of"]}


def enrich_candidates(cards, client, path, ledger, quotes):
    paused = False
    for row in cards:
        if not row["role_matches"]:
            email = {"status": "outside_target_roles"}
        elif paused or quotes is None:
            email = {"status": "provider_unavailable"}
        elif not quotes:
            email = {"status": "budget_limit"}
        else:
            try:
                email = candidate_email(row["person"], client, path, ledger, quotes)
            except ValueError as error:
                # Search results remain reviewable even if a contact call did not settle.
                print(f"Stopped work email lookups: {error}")
                paused = True
                email = {"status": "provider_unavailable"}
        row["work_email"] = email
