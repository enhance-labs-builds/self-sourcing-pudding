"""Read public posts and professional roles through Treg's hosted API."""

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
import os
import re
import tempfile
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
from uuid import uuid4


LINKEDIN = "harvestapi.linkedin.post.search"
X = "anyapi.x.search.posts"
PROFILE = "harvestapi.linkedin.user.profile"
COMPANY = "harvestapi.linkedin.company.profile"
WEB = "bravesearch.web.search"
WORK_EMAIL = "anyapi.linkedin.email.work.find"
VERIFY_EMAIL = "hunter.people.email.verify"
EMAIL_ENDPOINTS = {COMPANY, WORK_EMAIL, VERIFY_EMAIL}
METHODS = {LINKEDIN: "GET", X: "POST", PROFILE: "GET", COMPANY: "GET", WEB: "GET",
           WORK_EMAIL: "POST", VERIFY_EMAIL: "GET"}
PER_CALL = {LINKEDIN: 20_000, X: 3_000, PROFILE: 15_000, COMPANY: 5_000, WEB: 5_000,
            WORK_EMAIL: 11_000, VERIFY_EMAIL: 13_000}


def micro_dollars(value):
    try:
        micro = Decimal(str(value)) * 1_000_000
        if micro.is_finite() and 0 < micro <= 1_000_000 and micro == micro.to_integral_value():
            return int(micro)
    except InvalidOperation:
        pass
    raise ValueError("Use a USD amount between 0.000001 and 1 with at most six decimal places.")


def dollars(micro):
    return f"{Decimal(micro) / 1_000_000:.6f}"


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


class Treg:
    def __init__(self, token, org):
        self.headers = {"X-Treg-Token": token, "X-Treg-Org": org, "X-Treg-Client": "sourcing-rig"}
        self.opener = build_opener(NoRedirect)

    def request(self, path, method="GET", params=None, headers=None, *, public=False):
        request_headers = {"Accept": "application/json", **({} if public else self.headers), **(headers or {})}
        url = "https://treg.to" + path
        data = None
        if method == "POST":
            request_headers["Content-Type"] = "application/json"
            data = json.dumps(params).encode("utf-8")
        elif params:
            url += "?" + urlencode(params)
        request = Request(url, headers=request_headers, method=method, data=data)
        try:
            response = self.opener.open(request, timeout=35)
        except HTTPError as error:
            response = error
        except (URLError, TimeoutError) as error:
            raise ValueError("Could not reach treg.to. Check the connection before continuing.") from error
        with response:
            raw = response.read(8 * 1024 * 1024 + 1)
            try:
                body = json.loads(raw) if len(raw) <= 8 * 1024 * 1024 else None
            except (ValueError, UnicodeError):
                body = None
            return response.code, {key.lower(): value for key, value in response.headers.items()}, body

    def preflight(self, endpoints):
        for path in ("/secrets", "/tools"):
            status, _, rows = self.request(path)
            if status != 200 or not isinstance(rows, list):
                raise ValueError(f"Could not verify Treg team billing mode ({path}, HTTP {status}). Check TREG_TOKEN and TREG_ORG.")
            if rows:
                raise ValueError("Use a Treg team with no connected provider keys or custom tools so every call is covered by Treg's spend cap.")
        return self.endpoint_prices(endpoints)

    def endpoint_prices(self, endpoints):
        quotes = {}
        for endpoint in sorted(endpoints):
            status, _, payload = self.request(f"/catalog/endpoints/{endpoint}", public=True)
            if status != 200 or not isinstance(payload, dict):
                raise ValueError(f"Could not check the current catalog entry for {endpoint}.")
            row = payload.get("endpoint", {})
            price = row.get("cost", {})
            currencies = {"USD", "credit"} if endpoint == VERIFY_EMAIL else {"USD"}
            if (row.get("method") != METHODS[endpoint] or row.get("platform_eligible") is not True
                    or row.get("platform_blocked") or price.get("currency") not in currencies
                    or price.get("unit") != "call" or price.get("type") not in {"per_call", "per_success"}):
                raise ValueError(f"{endpoint} no longer has a supported Treg platform price or request contract.")
            quotes[endpoint] = micro_dollars(price["usd"])
            if quotes[endpoint] > PER_CALL[endpoint]:
                raise ValueError(f"{endpoint} exceeds this adapter's per-call cap.")
        return quotes


def atomic_json(path, data):
    with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, encoding="utf-8", delete=False) as file:
        temp = file.name
        try:
            json.dump(data, file, ensure_ascii=False, indent=2)
            file.flush()
            os.fsync(file.fileno())
        except BaseException:
            os.unlink(temp)
            raise
    try:
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


@contextmanager
def journal(out, plan, org, resume):
    import fcntl

    if not resume:
        out.mkdir(parents=True, mode=0o700)
        (out / ".gitignore").write_text("*\n", encoding="utf-8")
    with (out / ".lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        path = out / "treg-run.json"
        if resume:
            state = json.loads(path.read_text(encoding="utf-8"))
            if state["plan"] != plan or state["org"] != org:
                raise ValueError("Resume needs the original brief, options and Treg team.")
            if any(call["status"] == "pending" for call in state["calls"].values()):
                raise ValueError("A call has an uncertain outcome. Check Treg Activity before starting any new run.")
        else:
            state = {"plan": plan, "org": org, "id": uuid4().hex, "calls": {}}
            atomic_json(path, state)
        yield path, state


def planned_searches(brief, count):
    if "searches" in brief:
        return brief["searches"][:count]
    terms = list(dict.fromkeys(brief["signals"][:1] + brief["alternatives"] + brief["signals"]))
    return [{"lane": "problem" if term in brief["signals"] else "alternative", "phrase": term}
            for term in terms[:count]]


def social_queries(search):
    phrase = search["phrase"]
    quoted = '"' + phrase.replace('"', "") + '"'
    workflow = search.get("workflow")
    if not workflow:
        return phrase, quoted
    alternatives = " OR ".join(f'"{term}"' for term in workflow)
    return f"{quoted} AND ({alternatives})", f"{quoted} ({alternatives})"


def story_query(search):
    site = urlsplit(search["site"])
    directory = (site.netloc + site.path).rstrip("/")
    return f'site:{directory} "{search["workflow"]}"'


def story_results(data, search):
    site = urlsplit(search["site"])
    directory = site.path.rstrip("/") + "/"
    matches = {}
    for row in (data.get("web") or {}).get("results", []):
        url = urlsplit(row.get("url", ""))
        if (url.scheme != "https" or url.username is not None or not url.hostname
                or url.hostname.removeprefix("www.") != site.hostname.removeprefix("www.")
                or not url.path.startswith(directory) or url.path.rstrip("/") == site.path.rstrip("/")):
            continue
        permalink = url._replace(query="", fragment="").geturl().rstrip("/")
        matches[permalink] = {
            "url": permalink, "title": row.get("title", ""),
            "snippet": row.get("description", ""),
            "status": "needs_source_review",
        }
    return list(matches.values())


def billing(state):
    calls = state["calls"].values()
    return sum(call.get("cost_micro", 0) for call in calls)


def call_key(endpoint, params):
    return hashlib.sha256(json.dumps([endpoint, params], sort_keys=True).encode()).hexdigest()


def bounded_call(client, path, state, endpoint, params, quote, transform, *, reserve=0):
    key = call_key(endpoint, params)
    calls = state["calls"]
    if key in calls:
        return calls[key].get("result")
    remaining = state["plan"]["budget_micro"] - billing(state) - reserve
    ceiling = min(PER_CALL[endpoint], remaining)
    if ceiling < quote:
        print(f"Skipped {endpoint}: the remaining budget is below its listed price.")
        return None
    call = {"endpoint": endpoint, "params": params, "status": "pending", "reserved_micro": ceiling}
    calls[key] = call
    atomic_json(path, state)
    status, headers, data = client.request("/call/" + endpoint, METHODS[endpoint], params, {
        "Idempotency-Key": f"sourcing-rig-{state['id']}-{key[:24]}",
        "X-Treg-Route-Max-Cost": dollars(ceiling),
        "Cache-Control": "no-cache",
    })
    cost = headers.get("x-treg-cost-micro", "")
    call.update(http_status=status, call_id=headers.get("x-treg-call-id"))
    call["cache"] = headers.get("x-treg-cache")
    atomic_json(path, state)
    # A bare transport or proxy error may hide a completed charge. Keep its reservation.
    if status in {202, 409, 410} or not cost.isascii() or not cost.isdecimal():
        if status in {400, 401, 402, 403, 404, 422, 428, 429} and headers.get("x-treg-error") == "1" and not cost:
            cost = "0"
        else:
            raise ValueError(f"{endpoint} returned HTTP {status} without a settled receipt. Stopped; check Treg Activity.")
    charged = int(cost)
    if charged > ceiling:
        raise ValueError(f"{endpoint} reported a charge above its reservation. Stopped; check Treg Activity.")
    call.update(status="settled", cost_micro=charged)
    try:
        if status == 200 and not headers.get("x-treg-upstream-failed"):
            call["result"] = transform(data)
        else:
            print(f"{endpoint} returned HTTP {status}. See treg-run.json for the receipt.")
    except (KeyError, TypeError, ValueError, AttributeError) as error:
        call["status"] = "schema_error"
        raise ValueError(f"Unexpected response from {endpoint}; the charge receipt was saved.") from error
    finally:
        atomic_json(path, state)
    return call.get("result")


def linkedin_url(url, kind):
    parsed = urlsplit(url or "")
    if (parsed.scheme == "https" and parsed.hostname in {"linkedin.com", "www.linkedin.com"}
            and parsed.username is None and parsed.port in (None, 443)
            and re.fullmatch(rf"/{kind}/[\w%.-]+/?", parsed.path)):
        return "https://www.linkedin.com" + parsed.path.rstrip("/").lower()
    return None


def linkedin_profile(url):
    return linkedin_url(url, "in")


def linkedin_posts(data):
    output = []
    for row in data["elements"]:
        author = row.get("author") or {}
        url, body = row.get("linkedinUrl"), row.get("content")
        if not url or urlsplit(url).hostname not in {"linkedin.com", "www.linkedin.com"} or not body:
            continue
        stamp = (row.get("postedAt") or {}).get("date")
        output.append({
            "channel": "linkedin", "kind": "post", "author": author.get("name") or "Unknown LinkedIn author",
            "url": url.split("?")[0], "text": body, "published_on": stamp[:10] if stamp else None,
            "profile": linkedin_profile(author.get("linkedinUrl")), "headline": author.get("info") or "",
        })
    return output


def x_posts(data):
    output = []
    for row in data["output"]["data"]["items"]:
        handle, post_id = row.get("authorUsername", ""), str(row.get("id", ""))
        if not re.fullmatch(r"[A-Za-z0-9_]{1,15}", handle) or not post_id.isdigit() or not row.get("text"):
            continue
        stamp = row.get("createdUtc")
        output.append({
            "channel": "x", "kind": "reply" if row.get("isReply") is True else "post",
            "author": f"@{handle}", "url": f"https://x.com/{handle}/status/{post_id}",
            "text": row["text"], "published_on": datetime.fromtimestamp(stamp, timezone.utc).date().isoformat() if stamp else None,
            "profile": None, "headline": "",
        })
    return output


def profile_record(data, profile, today):
    row = data.get("element") or {}
    if linkedin_profile(row.get("linkedinUrl")) != profile:
        return None
    positions = [
        role for role in row.get("currentPosition") or []
        if role.get("position") and role.get("companyName") and not (role.get("endDate") or {}).get("year")
    ]
    roles = list(dict.fromkeys((role["position"], role["companyName"]) for role in positions))
    name = " ".join(filter(None, [row.get("firstName"), row.get("lastName")]))
    if not name or len(roles) != 1:
        return None
    role, company = roles[0]
    person = {
        "id": profile.rsplit("/", 1)[-1], "name": name, "role": role,
        "company": company, "profile_url": profile, "role_checked_on": today,
    }
    company_urls = {linkedin_url(position.get("companyLinkedinUrl"), "company") for position in positions}
    company_urls.discard(None)
    if len(company_urls) == 1:
        person["company_url"] = company_urls.pop()
    return person


def run_live(brief, args, match_terms, discovery_terms, *, enrich=None):
    explicit_searches = "searches" in brief
    search_count = args.searches or (4 if explicit_searches else 2)
    searches = planned_searches(brief, search_count)
    pages = getattr(args, "pages", 1)
    per_search = getattr(args, "results_per_search", 12)
    terms = [search["phrase"] for search in searches]
    story_searches = brief.get("customer_stories", [])
    budget = micro_dollars(args.budget_usd)
    print(f"Treg run ceiling: US${dollars(budget)}. Up to {len(terms) * (pages + 1)} social searches, "
          f"{len(story_searches)} customer story searches, and {args.profiles} role lookups.", flush=True)
    for search in searches:
        lane = search["lane"]
        linkedin, x = social_queries(search)
        if search.get("workflow"):
            print(f"  LinkedIn [{lane}]: {linkedin}\n  X [{lane}]: {x}", flush=True)
        else:
            print(f"  LinkedIn and X [{lane}]: {linkedin}", flush=True)
        if search.get("exclude_phrases"):
            print("    Skip these phrases for this search: " + ", ".join(search["exclude_phrases"]), flush=True)
    for story in story_searches:
        print(f"  Customer stories [{story['competitor']}]: {story_query(story)}", flush=True)
    if args.dry_run:
        return None

    token, org = os.environ.get("TREG_TOKEN"), os.environ.get("TREG_ORG")
    if not token or not org:
        raise ValueError("Set TREG_TOKEN and TREG_ORG for your Treg team.")
    client = Treg(token, org)
    plan = {"brief": brief, "terms": terms, "profiles": args.profiles, "budget_micro": budget}
    if pages != 1:
        plan["linkedin_pages"] = pages
    if per_search != 12:
        plan["results_per_search"] = per_search
    endpoints = {LINKEDIN, X}
    if args.profiles:
        endpoints.add(PROFILE)
    if story_searches:
        endpoints.add(WEB)
    if enrich:
        plan["work_email"] = True
    quotes = client.preflight(endpoints)
    minimum = (quotes[LINKEDIN] * pages + quotes[X]) * len(terms) + quotes.get(WEB, 0) * len(story_searches)
    if budget < minimum:
        raise ValueError("The budget is below the listed cost of the planned searches. Reduce --searches or raise the cap.")
    email_quotes = {}
    email_reserve = 0
    if enrich and budget - minimum >= sum(PER_CALL[endpoint] for endpoint in EMAIL_ENDPOINTS) + quotes.get(PROFILE, 0):
        try:
            email_quotes = client.endpoint_prices(EMAIL_ENDPOINTS)
        except ValueError as error:
            email_quotes = None
            print(f"Work email is unavailable: {error}")
        if email_quotes:
            email_reserve = sum(PER_CALL[endpoint] for endpoint in EMAIL_ENDPOINTS)
    with journal(args.out, plan, org, args.resume) as (path, state):
        if "as_of" not in state:
            state["as_of"] = datetime.now(timezone.utc).date().isoformat()
            atomic_json(path, state)
        today = state["as_of"]
        since = (datetime.fromisoformat(today) - timedelta(days=brief["limits"]["source_age_days"])).date()
        posts = {}
        for search in searches:
            term = search["phrase"]
            linkedin, x = social_queries(search)
            linkedin_sort = "date" if search.get("workflow") else "relevance"
            keep_terms = [term] if explicit_searches else discovery_terms
            requests = [(LINKEDIN, {"search": linkedin, "sortBy": linkedin_sort, "page": 1}, linkedin_posts),
                        (X, {"query": f"{x} since:{since}", "queryType": "Latest", "limit": per_search}, x_posts)]
            requests.extend((LINKEDIN, {"search": linkedin, "sortBy": linkedin_sort, "page": page}, linkedin_posts)
                            for page in range(2, pages + 1))
            for endpoint, payload, transform in requests:
                result = bounded_call(client, path, state, endpoint, payload, quotes[endpoint], transform)
                for post in (result or [])[:per_search]:
                    body = post["text"]
                    if not match_terms(body, keep_terms) or match_terms(body, search.get("exclude_phrases", [])):
                        continue
                    workflow_matches = match_terms(body, search.get("workflow", []))
                    if search.get("workflow") and not workflow_matches:
                        continue
                    observed = posts.setdefault(post["url"], dict(post))
                    if explicit_searches:
                        found_by = observed.setdefault("found_by", [])
                        query = {"lane": search["lane"], "phrase": term}
                        if workflow_matches:
                            query["workflow_matches"] = workflow_matches
                        if search.get("seed_url"):
                            query["seed_url"] = search["seed_url"]
                        if query not in found_by:
                            found_by.append(query)
        if story_searches:
            stories = {}
            for story in story_searches:
                result = bounded_call(client, path, state, WEB, {"q": story_query(story), "count": 8},
                                      quotes[WEB], lambda data: story_results(data, story))
                for match in result or []:
                    stories.setdefault((story["competitor"], match["url"]), {
                        **match, "competitor": story["competitor"], "workflow": story["workflow"],
                    })
            atomic_json(args.out / "customer-story-queue.json", {"as_of": today, "stories": list(stories.values())})
            print(f"Found {len(stories)} customer stories to check at the original source.")
        ranked = sorted(
            (post for post in posts.values() if post["profile"] and str(since) <= (post["published_on"] or "") <= today),
            key=lambda post: (bool(match_terms(post["headline"], brief["target_roles"])),
                              len(match_terms(post["text"], brief["signals"])), post["published_on"]),
            reverse=True,
        )
        profiles = list(dict.fromkeys(post["profile"] for post in ranked))[:args.profiles]
        people = {}
        for profile in profiles:
            person = bounded_call(client, path, state, PROFILE, {"url": profile}, quotes[PROFILE],
                                  lambda data: profile_record(data, profile, today), reserve=email_reserve)
            if person:
                people[profile] = person
        observations = []
        for index, post in enumerate(posts.values(), 1):
            observation = {key: value for key, value in post.items() if key not in {"profile", "headline"}}
            observation["id"] = f"treg-{index}"
            person = people.get(post["profile"])
            if person:
                observation["person_id"] = person["id"]
            elif post["profile"]:
                observation["profile_hint"] = post["profile"]
            observations.append(observation)
        corpus = {"schema_version": 1, "as_of": today, "people": list(people.values()), "observations": observations}
        atomic_json(args.out / "corpus.json", corpus)
        if enrich:
            enrich(corpus, client, path, state, email_quotes)
        billed = billing(state)
        print(f"Treg charged US${dollars(billed)} across {len(state['calls'])} calls. "
              f"Kept {len(observations)} posts and checked {len(people)} current roles.")
        return corpus
