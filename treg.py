"""Paid lookups through Treg's hosted API, with one spend cap and a receipt for every call."""

from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from http.client import HTTPException
import hashlib
import json
import os
import re
import tempfile
from time import time
from urllib.error import HTTPError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
from uuid import uuid4

LINKEDIN = "harvestapi.linkedin.post.search"
X = "anyapi.x.search.posts"
LINKEDIN_COMMENTS = "harvestapi.linkedin.post.comments"
X_REPLIES = "anyapi.x.post.comments"
X_QUOTES = "x.x.get-posts-quoted-posts"
X_PROFILE = "anyapi.x.user.profile"
PROFILE = "harvestapi.linkedin.user.profile"
COMPANY = "harvestapi.linkedin.company.profile"
SEMANTIC_PEOPLE = "exa.people.search"
BUYER_WEB = "serper.web.search"
WORK_EMAIL = "anyapi.linkedin.email.work.find"
VERIFY_EMAIL = "hunter.people.email.verify"
EMAIL_ENDPOINTS = (COMPANY, WORK_EMAIL, VERIFY_EMAIL)
METHODS = {LINKEDIN: "GET", X: "POST", PROFILE: "GET", COMPANY: "GET", WORK_EMAIL: "POST", VERIFY_EMAIL: "GET",
           LINKEDIN_COMMENTS: "GET", X_REPLIES: "POST", X_QUOTES: "GET", X_PROFILE: "POST", SEMANTIC_PEOPLE: "POST",
           BUYER_WEB: "POST"}
# The most a single call may cost, in millionths of a US dollar.
PER_CALL = {LINKEDIN: 20_000, X: 3_000, PROFILE: 15_000, COMPANY: 5_000, WORK_EMAIL: 11_000, VERIFY_EMAIL: 13_000,
            LINKEDIN_COMMENTS: 5_000, X_REPLIES: 14_000, X_QUOTES: 50_000, X_PROFILE: 2_000, SEMANTIC_PEOPLE: 7_000,
            BUYER_WEB: 1_000}
X_QUOTE_PAGE = 10


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
        self.headers = {"X-Treg-Token": token, "X-Treg-Org": org, "X-Treg-Client": "self-sourcing-pudding"}
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
                print("X quotes skipped. Treg did not confirm a metered connection.")
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
            currencies = {"USD", "credit"} if endpoint in {VERIFY_EMAIL, BUYER_WEB} else {"USD"}
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


def social_source_key(post):
    url = post["url"]
    if post["kind"] == "post":
        if post["channel"] == "x":
            return "x:" + url.rsplit("/", 1)[-1]
        if match := re.search(r"(?:activity[-:]|ugcPost:)(\d{17,22})(?!\d)", url):
            return "linkedin:" + match[1]
    return url


def billing(state):
    calls = state["calls"].values()
    return sum(call.get("cost_micro", 0) for call in calls)


def pending_calls(state):
    return {key: call for key, call in state["calls"].items() if call["status"] == "pending"}


def call_key(endpoint, params):
    return hashlib.sha256(json.dumps([endpoint, params], sort_keys=True).encode()).hexdigest()


def prepare_call(path, state, endpoint, params, quote, *, reserve=0):
    key = call_key(endpoint, params)
    calls = state["calls"]
    call = calls.get(key)
    retries = sum(1 for other in calls if other.startswith(key + ":rate-limited:"))
    if call and call["status"] == "rate_limited":
        # Keep the receipt, and let this attempt go out under a new idempotency key.
        calls[f"{key}:rate-limited:{retries}"] = calls.pop(key)
        call, retries = None, retries + 1
    if call and call["status"] != "pending":
        return None
    if call is None:
        remaining = state["plan"]["budget_micro"] - billing(state) - reserve
        ceiling = min(PER_CALL[endpoint], remaining)
        if quote is None or ceiling < quote:
            if quote is not None:
                print(f"Skipped {endpoint}: the remaining budget is below its required reservation.")
            return None
    if set(pending_calls(state)) - {key}:
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
                "started_at": time(), "idempotency_key": f"pudding-{state['id']}-{key[:24]}" + (f"-r{retries}" if retries else "")}
        calls[key] = call
        atomic_json(path, state)
    return call, recovering


def send_call(client, call):
    endpoint = call["endpoint"]
    try:
        return client.request("/call/" + endpoint, METHODS[endpoint], call["params"], {
            "Idempotency-Key": call["idempotency_key"],
            "X-Treg-Route-Max-Cost": dollars(call["reserved_micro"]),
            "Cache-Control": "no-cache",
        })
    except ValueError as error:
        raise PendingCall(f"{error} The run is saved. Resume this same run when the connection is back.") from error


def settle_call(path, state, call, recovering, response, transform):
    endpoint = call["endpoint"]
    status, headers, data = response
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
    if charged > call["reserved_micro"]:
        raise PendingCall(f"{endpoint} reported a charge above its reservation. Stopped; check Treg Activity.")
    call.update(status="settled", cost_micro=charged)
    if status == 429 and charged == 0:
        call["status"] = "rate_limited"  # Free and empty: a later run may try it again.
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


def bounded_call(client, path, state, endpoint, params, quote, transform, *, reserve=0):
    prepared = prepare_call(path, state, endpoint, params, quote, reserve=reserve)
    if prepared is None:
        return state["calls"].get(call_key(endpoint, params), {}).get("result")
    call, recovering = prepared
    return settle_call(path, state, call, recovering, send_call(client, call), transform)


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
            "channel": "x", "kind": "quote", "author": f"X user {author_id}", "x_author_id": author_id,
            "url": f"https://x.com/i/web/status/{post_id}", "text": row["text"],
            "published_on": stamp[:10] if stamp else None, "profile": None, "headline": "",
        })
    return output


def linkedin_links(links):
    profiles = set()
    for link in links:
        if isinstance(link, str):
            try:
                if profile := linkedin_profile(link):
                    profiles.add(profile)
            except ValueError:
                continue
    return profiles
