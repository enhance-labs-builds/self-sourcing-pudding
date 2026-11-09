"""Read public posts and professional roles through Treg's hosted API."""

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import hashlib
from http.client import HTTPException
import json
import os
import re
import tempfile
from time import time
from urllib.error import HTTPError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
from uuid import uuid4

from url_seed import terminal_text


LINKEDIN = "harvestapi.linkedin.post.search"
X = "anyapi.x.search.posts"
LINKEDIN_COMMENTS = "harvestapi.linkedin.post.comments"
X_REPLIES = "anyapi.x.post.comments"
X_QUOTES = "x.x.get-posts-quoted-posts"
X_PROFILE = "anyapi.x.user.profile"
PROFILE = "harvestapi.linkedin.user.profile"
COMPANY = "harvestapi.linkedin.company.profile"
WEB = "bravesearch.web.search"
WORK_EMAIL = "anyapi.linkedin.email.work.find"
VERIFY_EMAIL = "hunter.people.email.verify"
EMAIL_ENDPOINTS = {COMPANY, WORK_EMAIL, VERIFY_EMAIL}
METHODS = {LINKEDIN: "GET", X: "POST", PROFILE: "GET", COMPANY: "GET", WEB: "GET",
           WORK_EMAIL: "POST", VERIFY_EMAIL: "GET", LINKEDIN_COMMENTS: "GET", X_REPLIES: "POST", X_QUOTES: "GET",
           X_PROFILE: "POST"}
PER_CALL = {LINKEDIN: 20_000, X: 3_000, PROFILE: 15_000, COMPANY: 5_000, WEB: 5_000,
            WORK_EMAIL: 11_000, VERIFY_EMAIL: 13_000, LINKEDIN_COMMENTS: 5_000, X_REPLIES: 14_000,
            X_QUOTES: 50_000, X_PROFILE: 2_000}
SPIDER_RESULTS = 8
X_QUOTE_PAGE = 10
FIRSTHAND = re.compile(
    r"\b(?:(?:we|i) (?:use|built|run|tested|tried|migrated|own|maintain|shipped)|our (?:team|production|customers))\b",
    re.I,
)
# Treg retains a caller's idempotency key for 24 hours. Leave a margin for clock skew.
SAFE_REPLAY_SECONDS = 23 * 60 * 60


class PendingCall(ValueError):
    """The run must stop spending until an outstanding call can be accounted for."""


def micro_dollars(value):
    try:
        micro = Decimal(str(value)) * 1_000_000
        if micro.is_finite() and 0 < micro < 10**15 and micro == micro.to_integral_value():
            return int(micro)
    except InvalidOperation:
        pass
    raise ValueError("Use a positive USD amount with at most six decimal places.")


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
        except (OSError, HTTPException) as error:
            raise ValueError("Could not reach treg.to. Check the connection before continuing.") from error
        with response:
            try:
                raw = response.read(8 * 1024 * 1024 + 1)
            except (OSError, HTTPException) as error:
                raise ValueError("The connection to Treg dropped while receiving the response.") from error
            try:
                body = json.loads(raw) if len(raw) <= 8 * 1024 * 1024 else None
            except (ValueError, UnicodeError):
                body = None
            return response.code, {key.lower(): value for key, value in response.headers.items()}, body

    def preflight(self, endpoints, *, include_x_quotes=False):
        message = ("Use a Treg team with no connected provider keys or custom tools. "
                   "Pudding also supports one Treg-managed read-only X connection.")
        team = {}
        for path in ("/secrets", "/tools"):
            status, _, rows = self.request(path)
            if status != 200 or not isinstance(rows, list):
                raise ValueError(f"Could not verify Treg team billing mode ({path}, HTTP {status}). Check TREG_TOKEN and TREG_ORG.")
            if path == "/secrets" and rows and (len(rows) != 1 or rows[0].get("kind") != "oauth"):
                raise ValueError(message)
            team[path] = rows
        has_connection = any(team.values())
        if has_connection and not self.read_only_x_connection(team["/secrets"], team["/tools"]):
            raise ValueError(message)
        quotes = self.endpoint_prices(endpoints)
        if include_x_quotes and has_connection:
            status, _, access = self.request(f"/catalog/endpoints/{X_QUOTES}/access")
            if (status == 200 and isinstance(access, dict)
                    and access.get("tier") in {"tool", "credential"} and access.get("metered") is True):
                try:
                    quotes.update(self.endpoint_prices({X_QUOTES}))
                except ValueError:
                    print("X quotes skipped. Could not confirm the catalog price for the run.")
            else:
                print("X quotes skipped. Treg did not confirm a metered connection for quote posts.")
        return quotes

    def read_only_x_connection(self, secrets, registered):
        if len(secrets) != 1 or len(registered) > 1 or secrets[0].get("kind") != "oauth":
            return False
        secret_id = secrets[0].get("id")
        if secret_id is None:
            return False
        for tool in registered:
            bindings = tool.get("bindings") or []
            if (tool.get("base_url", "").rstrip("/") != "https://api.x.com" or len(bindings) != 1
                    or bindings[0].get("secret_id") != secret_id or bindings[0].get("injector") != "oauth"):
                return False
        status, _, connections = self.request("/connections")
        if status != 200 or not isinstance(connections, list) or len(connections) != 1:
            return False
        x = connections[0]
        scopes = set(x.get("scopes") or [])
        return (x.get("id") == secret_id and x.get("provider") == "x" and not x.get("paused")
                and not x.get("needs_reconnect") and {"tweet.read", "users.read"} <= scopes
                and scopes <= {"tweet.read", "users.read", "offline.access"})

    def endpoint_prices(self, endpoints):
        quotes = {}
        for endpoint in sorted(endpoints):
            status, _, payload = self.request(f"/catalog/endpoints/{endpoint}", public=True)
            if status != 200 or not isinstance(payload, dict):
                raise ValueError(f"Could not check the current catalog entry for {endpoint}.")
            row = payload.get("endpoint", {})
            price = row.get("cost", {})
            currencies = {"USD", "credit"} if endpoint == VERIFY_EMAIL else {"USD"}
            unit, types = ("post", {"per_result"}) if endpoint == X_QUOTES else ("call", {"per_call", "per_success"})
            if (row.get("method") != METHODS[endpoint] or row.get("platform_eligible") is not True
                    or row.get("platform_blocked") or price.get("currency") not in currencies
                    or price.get("unit") != unit or price.get("type") not in types):
                raise ValueError(f"{endpoint} no longer has a supported Treg platform price or request contract.")
            quotes[endpoint] = micro_dollars(price["usd"]) * (X_QUOTE_PAGE if endpoint == X_QUOTES else 1)
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
def journal(out, plan, org, resume, *, caller=None):
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
            if pending_calls(state) and state.get("caller") != caller:
                raise PendingCall("Resume needs the original TREG_TOKEN while a charge is pending. Check Treg Activity if the token is unavailable.")
        else:
            state = {"plan": plan, "org": org, "id": uuid4().hex, "calls": {}}
            atomic_json(path, state)
        state["caller"] = caller
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


def pending_calls(state):
    return {key: call for key, call in state["calls"].items() if call["status"] == "pending"}


def call_key(endpoint, params):
    return hashlib.sha256(json.dumps([endpoint, params], sort_keys=True).encode()).hexdigest()


def bounded_call(client, path, state, endpoint, params, quote, transform, *, reserve=0):
    key = call_key(endpoint, params)
    calls = state["calls"]
    call = calls.get(key)
    if call and call["status"] != "pending":
        return call.get("result")
    if call is None:
        skipped = state.setdefault("spider_skips", []) if state["plan"].get("spider") else []
        if key in skipped:
            return None
        remaining = state["plan"]["budget_micro"] - billing(state) - reserve
        ceiling = min(PER_CALL[endpoint], remaining)
        if quote is None or ceiling < quote:
            if state["plan"].get("spider"):
                # A resumed run must not insert an earlier call ahead of the pending one.
                skipped.append(key)
                atomic_json(path, state)
            if quote is not None:
                print(f"Skipped {endpoint}: the remaining budget is below its required reservation.")
            return None
    pending = pending_calls(state)
    if pending and set(pending) != {key}:
        raise PendingCall("A different request is still pending. No new paid requests were sent. Check Treg Activity.")
    recovering = call is not None
    if recovering:
        started_at = call.get("started_at")
        if (call.get("retry_blocked") or not call.get("idempotency_key") or started_at is None
                or not 0 <= time() - started_at < SAFE_REPLAY_SECONDS):
            reference = f" (call {call['call_id']})" if call.get("call_id") else ""
            raise PendingCall(f"Treg cannot safely replay {endpoint}{reference}. Check Treg Activity; the reservation is still held.")
    else:
        call = {"endpoint": endpoint, "params": params, "status": "pending", "reserved_micro": ceiling,
                "started_at": time(), "idempotency_key": f"sourcing-rig-{state['id']}-{key[:24]}"}
        calls[key] = call
        atomic_json(path, state)
    ceiling = call["reserved_micro"]
    try:
        status, headers, data = client.request("/call/" + endpoint, METHODS[endpoint], call["params"], {
            "Idempotency-Key": call["idempotency_key"],
            "X-Treg-Route-Max-Cost": dollars(ceiling),
            "Cache-Control": "no-cache",
        })
    except ValueError as error:
        raise PendingCall(f"{error} The run is saved. Resume this same run when the connection is back.") from error
    cost = headers.get("x-treg-cost-micro", "")
    replayed = headers.get("x-treg-idempotent-replay", "").lower() == "true"
    call_id = headers.get("x-treg-call-id")
    if not call_id and status == 410 and isinstance(data, dict):
        detail = data.get("detail")
        call_id = data.get("call_id") or (detail.get("call_id") if isinstance(detail, dict) else None)
    if call_id is not None and re.fullmatch(r"[a-zA-Z0-9_-]{1,128}", str(call_id)):
        call["call_id"] = str(call_id)
    call["http_status"] = status
    call["cache"] = headers.get("x-treg-cache")
    if status in {202, 410}:
        call["retry_blocked"] = True
    atomic_json(path, state)
    if status == 409:
        raise PendingCall(f"Treg is still processing {endpoint}. Wait briefly, then resume this same run.")
    if status in {202, 410}:
        raise PendingCall(f"Treg did not return a replayable result for {endpoint}. Check Treg Activity; the reservation is still held.")
    if replayed:
        cost = headers.get("x-treg-original-cost-micro", "") if cost == "0" else ""
    elif recovering and status != 200:
        # A refusal to replay (e.g. failed authentication) does not settle the first request.
        cost = ""
    elif status in {400, 401, 402, 403, 404, 422, 428, 429} and headers.get("x-treg-error") == "1" and not cost:
        cost = "0"
    if not cost.isascii() or not cost.isdecimal():
        raise PendingCall(f"{endpoint} returned HTTP {status} without a settled receipt. The run is saved; check Treg Activity.")
    charged = int(cost)
    if charged > ceiling:
        raise PendingCall(f"{endpoint} reported a charge above its reservation. Stopped; check Treg Activity.")
    call.update(status="settled", cost_micro=charged)
    if replayed:
        call["replayed"] = True
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
    if replayed:
        print(f"Recovered {endpoint}. Original charge: US${dollars(charged)}; replay: US$0.")
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


def linkedin_comments(data):
    output = []
    for row in data["elements"]:
        actor = row.get("actor") or {}
        url = urlsplit(row.get("linkedinUrl") or "")
        body = row.get("commentary")
        if (url.scheme != "https" or url.hostname not in {"linkedin.com", "www.linkedin.com"}
                or url.username is not None or url.port not in {None, 443} or not url.path or not body):
            continue
        stamp = row.get("createdAt")
        output.append({
            "channel": "linkedin", "kind": "comment", "author": actor.get("name") or "Unknown LinkedIn author",
            "url": url._replace(fragment="").geturl(), "text": body, "published_on": stamp[:10] if stamp else None,
            "profile": linkedin_profile(actor.get("linkedinUrl")), "headline": actor.get("position") or "",
        })
    return output


def x_posts(data, *, replies=False):
    output = []
    response = data["output"]
    if response.get("found") is False:
        return output
    for row in response["data"]["items"]:
        handle = row.get("authorUsername") or row.get("authorHandle") or ""
        post_id = str(row.get("id", ""))
        if not re.fullmatch(r"[A-Za-z0-9_]{1,15}", handle) or not post_id.isdigit() or not row.get("text"):
            continue
        stamp = row.get("createdUtc")
        output.append({
            "channel": "x", "kind": "reply" if replies or row.get("isReply") is True else "post",
            "author": f"@{handle}", "url": f"https://x.com/{handle}/status/{post_id}",
            "text": row["text"], "published_on": datetime.fromtimestamp(stamp, timezone.utc).date().isoformat() if stamp else None,
            "profile": None, "headline": "",
        })
    return output


def x_quotes(data, seed_id):
    output = []
    for row in data.get("data") or []:
        post_id, author_id = str(row.get("id", "")), str(row.get("author_id", ""))
        if not (re.fullmatch(r"[0-9]{1,19}", post_id) and re.fullmatch(r"[0-9]{1,19}", author_id)
                and row.get("text") and any(
                    item.get("type") == "quoted" and item.get("id") == seed_id
                    for item in row.get("referenced_tweets") or []
                )):
            continue
        stamp = row.get("created_at")
        output.append({
            "channel": "x", "kind": "quote", "author": f"X user {author_id}",
            "url": f"https://x.com/i/web/status/{post_id}", "text": row["text"],
            "published_on": stamp[:10] if stamp else None, "profile": None, "headline": "",
        })
    return output


def x_profile_link(data, handle):
    response = data.get("output") or {}
    row = response.get("data") or {}
    if not response.get("found") or (row.get("handle") or "").casefold() != handle.casefold():
        return None
    try:
        profile = linkedin_profile(row.get("website"))
    except ValueError:
        return None
    name = " ".join((row.get("displayName") or "").casefold().split())
    if profile and name:
        return {"profile": profile, "name": name}
    return None


def evidence_priority(text, matches):
    if not matches:
        return 0
    return 2 if FIRSTHAND.search(text) else 1


def verified_author(post, people):
    person = people.get(post["profile"])
    if person and (post["channel"] == "linkedin" or
                   " ".join(person["name"].casefold().split()) == post.get("x_profile_name")):
        return person
    return None


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


def workflow_signals(brief):
    return list(dict.fromkeys([
        *brief["signals"],
        *(search["phrase"] for search in brief.get("searches", []) if search["lane"] == "problem"),
        *(term for search in brief.get("searches", []) for term in search.get("workflow", [])),
    ]))


def employer_scope(text, company, workflow, match_terms):
    outside_work = (r"\b(?:side project|personal project|hobby project|outside work|on my own time|"
                    r"for (?:a|my|our|one of (?:my|our)) clients?|my (?:previous|former) (?:role|employer))\b")
    if re.search(outside_work, text, re.I):
        return None
    employer = re.compile(r"\b(?:at|within)\s+" + re.escape(company) +
                          r"(?=\s*(?:[,.;:!?]|$)|\s+(?:we|I|our)\b)", re.I)
    for span in re.split(r"\n+|(?<=[.!?])\s+", text):
        if employer.search(span) and FIRSTHAND.search(span) and match_terms(span, workflow):
            return span.strip()
    return None


def discover_followups(client, path, state, quotes, posts, people, brief, match_terms, *, since, today, reserve,
                       verify=None):
    """Read selected threads, then search employers where someone describes the work."""
    terms = workflow_signals(brief)

    def current(post):
        return str(since) <= (post["published_on"] or "") <= today

    seeds = sorted(
        (post for post in posts.values() if post["kind"] == "post" and current(post)),
        key=lambda post: (bool(FIRSTHAND.search(post["text"])), len(match_terms(post["text"], terms)),
                          post["published_on"]),
        reverse=True,
    )
    x_by_id = {post["url"].rsplit("/", 1)[-1]: post for post in posts.values() if post["channel"] == "x"}
    for channel in ("linkedin", "x"):
        seed = next((post for post in seeds if post["channel"] == channel), None)
        if not seed:
            continue
        if channel == "linkedin":
            lookups = [(LINKEDIN_COMMENTS, {"post": seed["url"], "sortBy": "date", "page": 1}, linkedin_comments)]
        else:
            seed_id = seed["url"].rsplit("/", 1)[-1]
            lookups = [(X_REPLIES, {"url": seed["url"], "limit": SPIDER_RESULTS},
                        lambda data: x_posts(data, replies=True))]
            if re.fullmatch(r"[0-9]{1,19}", seed_id):
                # Fetch post fields only. User expansions add a separately billed resource.
                lookups.append((X_QUOTES, {"id": seed_id, "max_results": X_QUOTE_PAGE,
                                           "tweet.fields": "author_id,created_at,referenced_tweets"},
                                lambda data: x_quotes(data, seed_id)))
        for endpoint, params, parse in lookups:
            # AnyAPI can switch to a dearer reply provider. Reserve its documented worst case.
            quote = (quotes[endpoint] if endpoint == X_QUOTES else PER_CALL[endpoint]) if endpoint in quotes else None
            rows = bounded_call(client, path, state, endpoint, params, quote, parse, reserve=reserve)
            for row in [item for item in rows or [] if item["url"] != seed["url"] and current(item)][:SPIDER_RESULTS]:
                kind = row["kind"]
                if channel == "x":
                    post_id = row["url"].rsplit("/", 1)[-1]
                    if post_id == seed_id:
                        continue
                    row = x_by_id.setdefault(post_id, row)
                observed = posts.setdefault(row["url"], dict(row))
                if channel == "x" and (observed["kind"] == "post" or kind == "quote"):
                    observed["kind"] = kind
                if observed["kind"] == "post":
                    continue
                observed.setdefault("parent_url", seed["url"])
                found_by = {"lane": "thread", "seed_url": seed["url"], "kind": kind}
                provenance = observed.setdefault("found_by", [])
                if found_by not in provenance:
                    provenance.append(found_by)

    pivots = seeds
    if verify is not None:
        verify()
        pivots = sorted(
            (post for post in posts.values() if current(post) and FIRSTHAND.search(post["text"])),
            key=lambda post: (len(match_terms(post["text"], terms)), post["published_on"]),
            reverse=True,
        )
    employers = {}
    for seed in pivots:
        person = verified_author(seed, people)
        workflow = match_terms(seed["text"], terms)
        if (not person or not person.get("company_url") or not workflow or not FIRSTHAND.search(seed["text"])):
            continue
        if verify is None and not match_terms(person["role"], brief["target_roles"]):
            continue
        scope = None
        if state["plan"].get("scope_spider"):
            scope = employer_scope(seed["text"], person["company"], workflow, match_terms)
            if not scope:
                continue
            workflow = match_terms(scope, workflow)
        company = person["company_url"]
        if company in employers:
            continue
        query = " OR ".join('"' + phrase.replace('"', "") + '"' for phrase in workflow[:2])
        params = {"authorsCompany": company, "search": query, "sortBy": "date", "page": 1}
        rows = bounded_call(client, path, state, LINKEDIN, params, quotes[LINKEDIN], linkedin_posts, reserve=reserve)
        scoped_source = {"scope_excerpt": scope, "root_url": seed.get("parent_url", seed["url"])} if scope else {}
        added = 0
        for row in rows or []:
            matched = match_terms(row["text"], workflow)
            if not row["profile"] or row["profile"] == seed["profile"] or not current(row) or not matched:
                continue
            observed = posts.setdefault(row["url"], {**row, "employer_search": company})
            found_by = {"lane": "employer", "company": company, "seed_url": seed["url"],
                        "workflow_matches": matched, **scoped_source}
            provenance = observed.setdefault("found_by", [])
            if found_by not in provenance:
                provenance.append(found_by)
            added += 1
            if added == SPIDER_RESULTS:
                break
        employers[company] = {"company_url": company, "seed_url": seed["url"],
                              "seed_profile": seed["profile"], **scoped_source}
        if len(employers) == (2 if verify is not None else 1):
            break
    return employers


def run_live(brief, args, match_terms, discovery_terms, *, enrich=None):
    explicit_searches = "searches" in brief
    search_count = args.searches or (4 if explicit_searches else 2)
    searches = planned_searches(brief, search_count)
    problem_terms = [search["phrase"] for search in searches if search["lane"] == "problem"]
    pages = getattr(args, "pages", 1)
    per_search = getattr(args, "results_per_search", 12)
    terms = [search["phrase"] for search in searches]
    story_searches = brief.get("customer_stories", [])
    spider = getattr(args, "spider", False)
    budget = micro_dollars(args.budget_usd)
    print(f"Treg run ceiling: US${dollars(budget)}. Up to {len(terms) * (pages + 1)} social searches, "
          f"{len(story_searches)} customer story searches, and {args.profiles} role lookups.", flush=True)
    for search in searches:
        lane = search["lane"]
        linkedin, x = social_queries(search)
        if search.get("workflow"):
            print(terminal_text(f"  LinkedIn [{lane}]: {linkedin}\n  X [{lane}]: {x}"), flush=True)
        else:
            print(terminal_text(f"  LinkedIn and X [{lane}]: {linkedin}"), flush=True)
        if search.get("exclude_phrases"):
            print(terminal_text("    Skip these phrases for this search: " + ", ".join(search["exclude_phrases"])), flush=True)
    for story in story_searches:
        print(terminal_text(f"  Customer stories [{story['competitor']}]: {story_query(story)}"), flush=True)
    if spider:
        print("  Follow-ups: one LinkedIn comment page, one X reply page, and up to two employer searches.", flush=True)
        print("  A metered read-only X connection also enables one page of quote posts.", flush=True)
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
    if spider:
        plan["spider"] = True
        if args.resume:
            # Keep the original lookup order when an earlier version has a request in flight.
            saved_plan = json.loads((args.out / "treg-run.json").read_text())["plan"]
            for flag in ("evidence_spider", "scope_spider"):
                if saved_plan.get(flag):
                    plan[flag] = True
        else:
            plan.update(evidence_spider=True, scope_spider=True)
    endpoints = {LINKEDIN, X}
    if args.profiles:
        endpoints.add(PROFILE)
    if story_searches:
        endpoints.add(WEB)
    company_signals = brief.get("company_signals", []) if plan.get("scope_spider") and args.profiles else []
    if enrich:
        plan["work_email"] = True
    quotes = client.preflight(endpoints, include_x_quotes=True) if spider else client.preflight(endpoints)
    minimum = (quotes[LINKEDIN] * pages + quotes[X]) * len(terms) + quotes.get(WEB, 0) * len(story_searches)
    # A resume accounts for completed calls and reuses the original reservation for any pending call.
    if not args.resume and budget < minimum:
        raise ValueError(f"The listed cost of the planned searches is US${dollars(minimum)}. "
                         "Reduce --searches or raise the spend limit.")
    if spider:
        followup_endpoints = [LINKEDIN_COMMENTS, X_REPLIES]
        if plan.get("evidence_spider") and args.profiles:
            followup_endpoints.append(X_PROFILE)
        if company_signals:
            followup_endpoints.append(COMPANY)
        for endpoint in followup_endpoints:
            try:
                quotes.update(client.endpoint_prices({endpoint}))
            except ValueError as error:
                print(f"Follow-up search unavailable: {error}")
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

    def finish(corpus, path, state):
        if enrich:
            enrich(corpus, client, path, state, email_quotes)
        print(f"Treg charged US${dollars(billing(state))} across {len(state['calls'])} calls. "
              f"Kept {len(corpus['observations'])} posts and checked {len(corpus['people'])} current roles.")
        return corpus

    with journal(args.out, plan, org, args.resume, caller=hashlib.sha256(token.encode()).hexdigest()) as (path, state):
        corpus_path = args.out / "corpus.json"
        if args.resume and corpus_path.exists():
            # The social and profile work finished. Don't reconsider skipped lookups during email recovery.
            return finish(json.loads(corpus_path.read_text(encoding="utf-8")), path, state)
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
            keep_terms = discovery_terms
            if explicit_searches:
                keep_terms = problem_terms if search["lane"] == "problem" else [term]
            requests = [(LINKEDIN, {"search": linkedin, "sortBy": linkedin_sort, "page": 1}, linkedin_posts),
                        (X, {"query": f"{x} since:{since}", "queryType": "Latest", "limit": per_search}, x_posts)]
            requests.extend((LINKEDIN, {"search": linkedin, "sortBy": linkedin_sort, "page": page}, linkedin_posts)
                            for page in range(2, pages + 1))
            for endpoint, payload, transform in requests:
                result = bounded_call(client, path, state, endpoint, payload, quotes[endpoint], transform)
                kept = 0
                for post in result or []:
                    body = post["text"]
                    matches = match_terms(body, keep_terms)
                    if not matches or match_terms(body, search.get("exclude_phrases", [])):
                        continue
                    workflow_matches = match_terms(body, search.get("workflow", []))
                    if search.get("workflow") and not workflow_matches:
                        continue
                    observed = posts.setdefault(post["url"], dict(post))
                    if explicit_searches:
                        found_by = observed.setdefault("found_by", [])
                        query = {"lane": search["lane"], "phrase": term}
                        if search["lane"] == "problem" and term not in matches:
                            query["matched_problem_terms"] = matches
                        if workflow_matches:
                            query["workflow_matches"] = workflow_matches
                        if search.get("seed_url"):
                            query["seed_url"] = search["seed_url"]
                        if query not in found_by:
                            found_by.append(query)
                    kept += 1
                    if kept >= per_search:
                        break
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
        people = {}
        checked = set()
        evidence_spider = plan.get("evidence_spider")
        signals = workflow_signals(brief)

        def current(post):
            return str(since) <= (post["published_on"] or "") <= today

        def post_evidence(post):
            return evidence_priority(post["text"], match_terms(post["text"], signals))

        def resolve_x_profiles():
            if not args.profiles:
                return
            authors = [post for post in posts.values() if post["channel"] == "x" and current(post)
                       and post["author"].startswith("@")]
            ranked = sorted(
                (post for post in authors if post_evidence(post) or post.get("parent_url")),
                key=lambda post: (post_evidence(post), bool(post.get("parent_url")), post["published_on"]),
                reverse=True,
            )
            handles = list(dict.fromkeys(post["author"][1:].casefold() for post in ranked))
            links = {}
            for handle in handles[:min(4, args.profiles)]:
                quote = PER_CALL[X_PROFILE] if X_PROFILE in quotes else None
                link = bounded_call(client, path, state, X_PROFILE, {"handle": handle}, quote,
                                    lambda data: x_profile_link(data, handle), reserve=email_reserve + quotes[PROFILE])
                if link:
                    links[handle] = link
            for post in authors:
                handle = post["author"][1:].casefold()
                if link := links.get(handle):
                    post.update(profile=link["profile"], x_profile_name=link["name"],
                                binding_source=f"https://x.com/{handle}", role_source=link["profile"])

        def check_profiles(limit, *, choose_seeds=False):
            if len(checked) >= limit:
                return
            def rank(post):
                role_match = bool(match_terms(post["headline"], brief["target_roles"]))
                if evidence_spider:
                    return post_evidence(post), role_match, post["published_on"]
                matches = match_terms(post["text"], signals if choose_seeds else brief["signals"])
                return (choose_seeds and bool(matches and FIRSTHAND.search(post["text"])),
                        role_match, len(matches), post["published_on"])

            ranked = sorted(
                (post for post in posts.values() if post["profile"] and current(post)),
                key=rank, reverse=True,
            )
            for profile in dict.fromkeys(post["profile"] for post in ranked):
                if profile in checked:
                    continue
                checked.add(profile)
                person = bounded_call(client, path, state, PROFILE, {"url": profile}, quotes[PROFILE],
                                      lambda data: profile_record(data, profile, today), reserve=email_reserve)
                if person:
                    people[profile] = person
                if len(checked) == limit:
                    break

        employers = {}
        if spider:
            def verify():
                resolve_x_profiles()
                check_profiles(min(4, (args.profiles + 1) // 2))

            if not evidence_spider:
                check_profiles(min(2, args.profiles), choose_seeds=True)
            employers = discover_followups(client, path, state, quotes, posts, people, brief, match_terms,
                                           since=since, today=today, reserve=email_reserve,
                                           verify=verify if evidence_spider else None)
        check_profiles(args.profiles)
        if company_signals:
            from work_email import company_details

            # Check thread participants first. Company evidence can lift a short reply for review.
            thread_people = [verified_author(post, people) for post in posts.values() if post.get("parent_url")]
            companies = list(dict.fromkeys(person["company_url"] for person in [*thread_people, *people.values()]
                                          if person and person.get("company_url")))
            company_fits = {}
            for company in companies[:3]:
                profile = bounded_call(client, path, state, COMPANY, {"url": company}, quotes.get(COMPANY),
                                       lambda data: company_details(data, company), reserve=email_reserve)
                for span in re.split(r"\n+|(?<=[.!?])\s+", (profile or {}).get("description", "")):
                    if matches := match_terms(span, company_signals):
                        company_fits[company] = {"source_url": company, "excerpt": span.strip(), "signals": matches}
                        break
            for person in people.values():
                if fit := company_fits.get(person.get("company_url")):
                    person["company_fit"] = fit
        if pending_calls(state):
            raise PendingCall("A search is still pending. Resume this run before creating a new preview.")
        for profile, person in people.items():
            employer = employers.get(person.get("company_url"))
            if employer and profile != employer["seed_profile"]:
                person["employer_signal"] = {key: value for key, value in employer.items() if key != "seed_profile"}

        # Keep the provider's employer filter as a discovery hint until we check the current role.
        kept = []
        for post in posts.values():
            person = people.get(post["profile"])
            if person:
                company = person.get("company_url")
                if post.get("employer_search") and company != post["employer_search"]:
                    continue
                if "found_by" in post:
                    post["found_by"] = [entry for entry in post["found_by"]
                                        if entry.get("lane") != "employer" or entry.get("company") == company]
            kept.append(post)
        source_ids = {post["url"]: f"treg-{index}" for index, post in enumerate(kept, 1)}
        observations = []
        for post in kept:
            observation = {key: value for key, value in post.items()
                           if key not in {"profile", "headline", "parent_url", "employer_search", "x_profile_name",
                                          "binding_source", "role_source"}}
            observation["id"] = source_ids[post["url"]]
            if post.get("parent_url") in source_ids:
                observation["parent_id"] = source_ids[post["parent_url"]]
            person = verified_author(post, people)
            if person:
                observation["person_id"] = person["id"]
                if post["channel"] == "x":
                    observation.update(binding_source=post["binding_source"], role_source=post["role_source"])
            elif post["profile"] and post["channel"] == "linkedin":
                observation["profile_hint"] = post["profile"]
            observations.append(observation)
        corpus = {"schema_version": 1, "as_of": today, "people": list(people.values()), "observations": observations}
        atomic_json(corpus_path, corpus)
        return finish(corpus, path, state)
