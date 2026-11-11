from email.message import Message
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import treg as t


class FakeClient:
    def __init__(self, *responses):
        self.responses, self.sent = list(responses), []

    def request(self, path, method, params, headers):
        self.sent.append((path, method, params, headers))
        return self.responses.pop(0)


def reply(status=200, cost="2000", data=None, **headers):
    return status, {"x-treg-cost-micro": cost, "x-treg-call-id": "call_1", **headers}, data or {"elements": []}


class Ledgered:
    def ledger(self, budget=100_000, resume=False):
        if not resume:
            folder = tempfile.TemporaryDirectory()
            self.addCleanup(folder.cleanup)
            self.out = Path(folder.name) / "ledger"
        return t.journal(self.out, {"budget_micro": budget}, "org", resume, caller="me")


class LedgerTest(Ledgered, unittest.TestCase):
    def test_a_settled_call_is_charged_once_and_reused(self):
        client = FakeClient(reply())
        params = {"search": '"Tool" "we switched"', "page": 1}
        with self.ledger() as (path, state):
            first = t.bounded_call(client, path, state, t.LINKEDIN, params, 4000, t.linkedin_posts)
            again = t.bounded_call(client, path, state, t.LINKEDIN, params, 4000, t.linkedin_posts)
            self.assertEqual((first, again, len(client.sent), t.billing(state)), ([], [], 1, 2000))
            headers = client.sent[0][3]
            self.assertEqual(headers["X-Treg-Route-Max-Cost"], "0.020000")
            self.assertTrue(headers["Idempotency-Key"].startswith("pudding-"))
        for name in ("treg-run.json", ".lock", ".gitignore"):
            self.assertEqual(oct((self.out / name).stat().st_mode & 0o777), "0o600")

    def test_lookups_sent_together_share_the_cap_and_each_is_sent_once(self):
        import threading, time
        from concurrent.futures import ThreadPoolExecutor

        class SlowClient:
            def __init__(self):
                self.sent, self.guard, self.limited = [], threading.Lock(), {"p9"}

            def request(self, path, method, params, headers):
                with self.guard:
                    self.sent.append(params["url"])
                time.sleep(0.02)  # Long enough for the others to be in flight too.
                if params["url"] in self.limited:  # Refused once for free, then answered.
                    self.limited.discard(params["url"])
                    return 429, {"x-treg-error": "1"}, {"detail": "slow down"}
                return reply(cost="3000")

        client = SlowClient()
        with self.ledger(budget=20_000) as (path, state):
            lookups = t.Lookups(client, path, state)
            ask = lambda url: lookups(t.PROFILE, {"url": url}, 4000, lambda data: "found")
            with ThreadPoolExecutor(4) as pool:
                same = list(pool.map(ask, ["p0"] * 4))
                many = list(pool.map(ask, [f"p{n}" for n in range(1, 9)]))
            # Four requests for one profile are one lookup. Eight more do not fit a cap of 20,000: the rest are never sent.
            self.assertEqual((same, client.sent.count("p0")), (["found"] * 4, 1))
            self.assertLessEqual(t.billing(state), 20_000)
            self.assertEqual((many.count("found"), many.count(None), t.pending_calls(state)), (len(client.sent) - 1, 9 - len(client.sent), {}))
            self.assertLess(len(client.sent), 9)
        with self.ledger(budget=100_000) as (path, state):
            lookups, client = t.Lookups(client, path, state), SlowClient()
            lookups.client = client
            real, t.sleep = t.sleep, lambda seconds: None
            self.addCleanup(setattr, t, "sleep", real)
            self.assertEqual(lookups(t.PROFILE, {"url": "p9"}, 4000, lambda data: "found"), "found")
            self.assertEqual((client.sent, t.billing(state)), (["p9", "p9"], 3000))
        # A lookup Treg turned away for an empty balance is not remembered as a miss: the next run sends it again.
        broke = (402, {"x-treg-error": "1", "x-treg-call-id": "call_2"}, {"detail": "insufficient_balance"})
        client = FakeClient(broke, reply(cost="3000"))
        with self.ledger(budget=100_000) as (path, state):
            self.assertIsNone(t.bounded_call(client, path, state, t.PROFILE, {"url": "p"}, 4000, lambda data: "found"))
            self.assertEqual((t.billing(state), state["calls"][t.call_key(t.PROFILE, {"url": "p"})]["status"]), (0, "refused"))
            self.assertEqual(t.bounded_call(client, path, state, t.PROFILE, {"url": "p"}, 4000, lambda data: "found"), "found")
            self.assertEqual(t.billing(state), 3000)
        # A charge this process did not start still stops everything.
        with self.ledger(budget=100_000) as (path, state):
            state["calls"]["stray"] = {"endpoint": t.PROFILE, "params": {}, "status": "pending", "reserved_micro": 15_000}
            with self.assertRaises(t.PendingCall):
                t.Lookups(client, path, state)(t.PROFILE, {"url": "p1"}, 4000, lambda data: "found")

    def test_a_call_that_does_not_fit_the_cap_is_never_sent(self):
        client = FakeClient()
        with self.ledger(budget=3000) as (path, state):
            self.assertIsNone(t.bounded_call(client, path, state, t.LINKEDIN, {"search": "x"}, 4000, t.linkedin_posts))
            self.assertEqual((client.sent, state["calls"]), ([], {}))

    def test_a_charge_above_the_reservation_stops_the_run(self):
        client = FakeClient(reply(cost="25000"))
        with self.ledger() as (path, state):
            with self.assertRaises(t.PendingCall):
                t.bounded_call(client, path, state, t.LINKEDIN, {"search": "x"}, 4000, t.linkedin_posts)
            self.assertEqual(len(t.pending_calls(state)), 1)

    def test_an_interrupted_call_blocks_new_spend_and_replays_with_the_same_key(self):
        client = FakeClient(reply(status=409, cost=""))
        with self.ledger() as (path, state):
            with self.assertRaises(t.PendingCall):
                t.bounded_call(client, path, state, t.LINKEDIN, {"search": "x"}, 4000, t.linkedin_posts)
            with self.assertRaisesRegex(t.PendingCall, "different request is still pending"):
                t.bounded_call(client, path, state, t.X, {"query": "y"}, 750, t.x_posts)
        replay = reply(cost="0", **{"x-treg-idempotent-replay": "true", "x-treg-original-cost-micro": "2000"})
        client.responses.append(replay)
        with self.ledger(resume=True) as (path, state):
            self.assertEqual(t.bounded_call(client, path, state, t.LINKEDIN, {"search": "x"}, 4000, t.linkedin_posts), [])
            self.assertEqual((t.billing(state), t.pending_calls(state)), (2000, {}))
        self.assertEqual(client.sent[0][3]["Idempotency-Key"], client.sent[1][3]["Idempotency-Key"])

    def test_a_rate_limited_lookup_is_free_and_tried_again_under_a_new_key(self):
        limited = (429, {"x-treg-error": "1", "x-treg-call-id": "call_1"}, {"detail": "slow down"})
        client = FakeClient(limited, reply())
        with self.ledger() as (path, state):
            self.assertIsNone(t.bounded_call(client, path, state, t.PROFILE, {"url": "p"}, 4000, lambda data: "found"))
            self.assertEqual((t.billing(state), t.pending_calls(state)), (0, {}))
            self.assertEqual(t.bounded_call(client, path, state, t.PROFILE, {"url": "p"}, 4000, lambda data: "found"), "found")
            self.assertEqual((t.billing(state), len(state["calls"])), (2000, 2))
        first, second = (sent[3]["Idempotency-Key"] for sent in client.sent)
        self.assertEqual(second, first + "-r1")

    def test_resume_needs_the_same_cap(self):
        with self.ledger():
            pass
        with self.assertRaisesRegex(ValueError, "original"):
            with self.ledger(budget=5, resume=True):
                pass


class SettlementTest(Ledgered, unittest.TestCase):
    def attempt(self, client, state, path, transform=t.linkedin_posts):
        return t.bounded_call(client, path, state, t.LINKEDIN, {"search": "x"}, 4000, transform)

    def test_a_reply_with_no_receipt_stops_the_run(self):
        with self.ledger() as (path, state):
            with self.assertRaisesRegex(t.PendingCall, "without a settled receipt"):
                self.attempt(FakeClient(reply(status=500, cost="")), state, path)
            self.assertEqual(len(t.pending_calls(state)), 1)

    def test_a_receipt_that_is_not_a_number_stops_the_run(self):
        with self.ledger() as (path, state), self.assertRaises(t.PendingCall):
            self.attempt(FakeClient(reply(cost="-5")), state, path)

    def test_an_unreplayable_call_holds_its_reservation(self):
        client = FakeClient(reply(status=202, cost=""))
        with self.ledger() as (path, state):
            with self.assertRaisesRegex(t.PendingCall, "replayable"):
                self.attempt(client, state, path)
            with self.assertRaisesRegex(t.PendingCall, "cannot safely replay"):
                self.attempt(client, state, path)
        self.assertEqual(len(client.sent), 1)

    def test_a_pending_call_past_the_replay_window_is_not_resent(self):
        client = FakeClient(reply(status=409, cost=""))
        with self.ledger() as (path, state):
            with self.assertRaises(t.PendingCall):
                self.attempt(client, state, path)
            next(iter(t.pending_calls(state).values()))["started_at"] -= t.SAFE_REPLAY_SECONDS + 1
            with self.assertRaisesRegex(t.PendingCall, "cannot safely replay"):
                self.attempt(client, state, path)
        self.assertEqual(len(client.sent), 1)

    def test_a_lost_connection_keeps_the_reservation(self):
        class Offline:
            def request(self, *_):
                raise ValueError("Could not reach treg.to.")

        with self.ledger() as (path, state):
            with self.assertRaisesRegex(t.PendingCall, "The run is saved"):
                self.attempt(Offline(), state, path)
            self.assertEqual(len(t.pending_calls(state)), 1)

    def test_an_unexpected_response_keeps_the_receipt(self):
        with self.ledger() as (path, state):
            with self.assertRaisesRegex(ValueError, "charge receipt was saved"):
                self.attempt(FakeClient(reply(data={"unexpected": True})), state, path)
            self.assertEqual(t.billing(state), 2000)
            self.assertEqual(next(iter(state["calls"].values()))["status"], "schema_error")

    def test_an_upstream_failure_is_billed_as_reported_and_not_parsed(self):
        with self.ledger() as (path, state):
            self.assertIsNone(self.attempt(FakeClient(reply(**{"x-treg-upstream-failed": "1"})), state, path))
            self.assertEqual(t.billing(state), 2000)

    def test_a_refused_replay_does_not_settle_the_first_request(self):
        client = FakeClient(reply(status=409, cost=""), reply(status=401, cost="", **{"x-treg-error": "1"}))
        with self.ledger() as (path, state):
            with self.assertRaises(t.PendingCall):
                self.attempt(client, state, path)
            with self.assertRaises(t.PendingCall):
                self.attempt(client, state, path)
            self.assertEqual(len(t.pending_calls(state)), 1)

    def test_the_reservation_shrinks_to_what_is_left(self):
        client = FakeClient(reply(cost="1000"))
        with self.ledger(budget=5000) as (path, state):
            self.attempt(client, state, path)
        self.assertEqual(client.sent[0][3]["X-Treg-Route-Max-Cost"], "0.005000")

    def test_a_folder_already_in_use_says_so(self):
        with self.ledger():
            with self.assertRaisesRegex(ValueError, "Another Pudding step"):
                with self.ledger(resume=True):
                    pass

    def test_a_pending_charge_needs_the_token_that_made_it(self):
        with self.ledger() as (path, state):
            with self.assertRaises(t.PendingCall):
                self.attempt(FakeClient(reply(status=409, cost="")), state, path)
        with self.assertRaisesRegex(t.PendingCall, "original TREG_TOKEN"):
            with t.journal(self.out, {"budget_micro": 100_000}, "org", True, caller="someone else"):
                pass


class Answer(io.BytesIO):
    code = 200
    headers = {"X-Treg-Cost-Micro": "10"}


class FakeOpener:
    def __init__(self, result):
        self.result, self.requests = result, []

    def open(self, request, timeout):
        self.requests.append(request)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


class ClientTest(unittest.TestCase):
    def client(self, result=None):
        client = t.Treg("secret-token", "org")
        client.opener = FakeOpener(Answer(b"{}") if result is None else result)
        return client

    def test_the_token_goes_to_treg_and_only_on_private_calls(self):
        client = self.client()
        client.request("/secrets")
        client.opener.result = Answer(b"{}")
        client.request("/catalog/endpoints/x", public=True)
        private, public = client.opener.requests
        self.assertEqual((urlsplit(private.full_url).scheme, urlsplit(private.full_url).hostname), ("https", "treg.to"))
        self.assertEqual(private.get_header("X-treg-token"), "secret-token")
        self.assertIsNone(public.get_header("X-treg-token"))

    def test_redirects_are_never_followed(self):
        self.assertIsNone(t.NoRedirect().redirect_request(None, None, 302, "", {}, "https://attacker.example/"))
        self.assertTrue(any(isinstance(handler, t.NoRedirect) for handler in t.Treg("a", "b").opener.handlers))

    def test_a_post_sends_json_and_a_get_sends_a_query(self):
        client = self.client()
        client.request("/call/x", "POST", {"a": 1})
        self.assertEqual((client.opener.requests[0].data, client.opener.requests[0].get_header("Content-type")), (b'{"a": 1}', "application/json"))
        client.opener.result = Answer(b"{}")
        client.request("/call/y", "GET", {"q": "a b"})
        self.assertTrue(client.opener.requests[1].full_url.endswith("/call/y?q=a+b"))

    def test_response_headers_are_lower_cased_and_errors_read_as_responses(self):
        self.assertEqual(self.client().request("/x"), (200, {"x-treg-cost-micro": "10"}, {}))
        error = HTTPError("https://treg.to/x", 403, "no", Message(), io.BytesIO(b'{"detail": "no"}'))
        self.assertEqual(self.client(error).request("/x")[0::2], (403, {"detail": "no"}))

    def test_a_network_failure_never_shows_the_token(self):
        with self.assertRaises(ValueError) as caught:
            self.client(OSError("down")).request("/x")
        self.assertNotIn("secret-token", str(caught.exception))

    def test_a_response_too_large_or_not_json_has_no_body(self):
        self.assertIsNone(self.client(Answer(b"x" * (8 * 1024 * 1024 + 2))).request("/x")[2])
        self.assertIsNone(self.client(Answer(b"not json")).request("/x")[2])


class Scripted(t.Treg):
    def __init__(self, **replies):
        super().__init__("token", "org")
        self.replies = replies

    def request(self, path, method="GET", params=None, headers=None, *, public=False):
        return self.replies[path]


GOOD_PRICE = {"endpoint": {"method": "GET", "platform_eligible": True, "cost": {"usd": "0.002", "currency": "USD", "unit": "call", "type": "per_call"}}}


class PreflightTest(unittest.TestCase):
    endpoint = f"/catalog/endpoints/{t.LINKEDIN}"

    def priced(self, change):
        row = json.loads(json.dumps(GOOD_PRICE))
        change(row["endpoint"])
        return Scripted(**{self.endpoint: (200, {}, row)})

    def test_a_clean_team_passes_and_gets_its_prices(self):
        client = Scripted(**{"/secrets": (200, {}, []), "/tools": (200, {}, []), self.endpoint: (200, {}, GOOD_PRICE)})
        self.assertEqual(client.preflight({t.LINKEDIN}), {t.LINKEDIN: 2000})

    def test_a_team_with_its_own_provider_keys_is_refused(self):
        client = Scripted(**{"/secrets": (200, {}, [{"kind": "api_key", "id": 1}]), "/tools": (200, {}, [])})
        with self.assertRaisesRegex(ValueError, "no connected provider keys"):
            client.preflight({t.LINKEDIN})

    def test_a_bad_sign_in_is_reported(self):
        with self.assertRaisesRegex(ValueError, "HTTP 401"):
            Scripted(**{"/secrets": (401, {}, None)}).preflight({t.LINKEDIN})

    def x_connection(self, scopes):
        tool = {"base_url": "https://api.x.com", "bindings": [{"secret_id": 7, "injector": "oauth"}]}
        return Scripted(**{"/connections": (200, {}, [{"id": 7, "provider": "x", "scopes": scopes}])}), [{"kind": "oauth", "id": 7}], [tool]

    def test_a_read_only_x_connection_is_allowed_and_a_writing_one_is_not(self):
        client, secrets, tools = self.x_connection(["tweet.read", "users.read", "offline.access"])
        self.assertTrue(client.read_only_x_connection(secrets, tools))
        client, secrets, tools = self.x_connection(["tweet.read", "users.read", "tweet.write"])
        self.assertFalse(client.read_only_x_connection(secrets, tools))

    def test_a_price_above_the_adapters_limit_is_refused(self):
        client = self.priced(lambda row: row["cost"].update(usd="1.00"))
        with self.assertRaisesRegex(ValueError, "per-call cap"):
            client.endpoint_prices({t.LINKEDIN})

    def test_a_changed_contract_is_refused(self):
        for change in (lambda row: row.update(method="POST"), lambda row: row.update(platform_blocked=True),
                       lambda row: row.update(platform_eligible=False), lambda row: row["cost"].update(currency="EUR"),
                       lambda row: row["cost"].update(type="per_token")):
            with self.assertRaisesRegex(ValueError, "no longer has a supported"):
                self.priced(change).endpoint_prices({t.LINKEDIN})


class ParsingTest(unittest.TestCase):
    def test_malformed_links_are_skipped_rather_than_failing_the_page(self):
        for bad in ("https://[broken", "https://www.linkedin.com:port/in/ada", "http://www.linkedin.com/in/ada", None, 5,
                    "https://user@www.linkedin.com/in/ada", "javascript://linkedin.com/in/ada"):
            self.assertIsNone(t.linkedin_profile(bad), bad)
        rows = [{"linkedinUrl": "https://[broken", "content": "x"}, {"linkedinUrl": "javascript://linkedin.com/%0aa", "content": "x"}]
        self.assertEqual(t.linkedin_posts({"elements": rows}), [])
        self.assertEqual(t.linkedin_comments({"elements": [{"linkedinUrl": "https://[broken", "commentary": "x"}]}), [])
        self.assertEqual(t.linkedin_links(["https://[broken", None, "https://www.linkedin.com/in/ada"]), {"https://www.linkedin.com/in/ada"})

    def test_comments_and_quote_posts_are_read(self):
        comments = t.linkedin_comments({"elements": [{"linkedinUrl": "https://www.linkedin.com/feed/update/1#c", "commentary": "We use it.",
                                                      "createdAt": "2026-11-01T00:00:00Z", "actor": {"name": "Ada", "position": "CTO"}}]})
        self.assertEqual((comments[0]["kind"], comments[0]["url"], comments[0]["headline"]), ("comment", "https://www.linkedin.com/feed/update/1", "CTO"))
        quote = {"id": "9", "author_id": "4", "text": "We moved.", "created_at": "2026-11-02T00:00:00Z", "referenced_tweets": [{"type": "quoted", "id": "1"}]}
        other = {**quote, "id": "10", "referenced_tweets": [{"type": "quoted", "id": "2"}]}
        self.assertEqual([row["url"] for row in t.x_quotes({"data": [quote, other]}, "1")], ["https://x.com/i/web/status/9"])

    def test_an_absurd_cap_is_refused(self):
        for bad in ("NaN", "Infinity", "1e30"):
            with self.assertRaises(ValueError):
                t.micro_dollars(bad)

    def test_files_are_replaced_whole_and_stay_private(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "state.json"
            t.atomic_json(path, {"a": 1})
            self.assertEqual(oct(path.stat().st_mode & 0o777), "0o600")
            with self.assertRaises(TypeError):
                t.atomic_json(path, {"a": object()})
            self.assertEqual(json.loads(path.read_text()), {"a": 1})
            self.assertEqual([item.name for item in Path(folder).iterdir()], ["state.json"])

    def test_money_and_profile_links_are_normalised(self):
        self.assertEqual((t.micro_dollars("1.00"), t.dollars(326120)), (1_000_000, "0.326120"))
        for bad in ("0", "-1", "0.0000001", "abc"):
            with self.assertRaises(ValueError):
                t.micro_dollars(bad)
        self.assertEqual(t.linkedin_profile("https://www.linkedin.com/in/Ada-Example/"), "https://www.linkedin.com/in/ada-example")
        self.assertIsNone(t.linkedin_profile("https://www.linkedin.com/company/fig"))
        self.assertIsNone(t.linkedin_profile("https://evil.example/in/ada"))

    def test_posts_from_both_networks_share_one_shape(self):
        linkedin = t.linkedin_posts({"elements": [
            {"linkedinUrl": "https://www.linkedin.com/posts/ada_activity-7000000000000000001-abcd?utm=1", "content": "We switched.",
             "postedAt": {"date": "2026-11-01T10:00:00Z"}, "author": {"name": "Ada Example", "info": "Founder at Fig",
                                                                         "linkedinUrl": "https://www.linkedin.com/in/ada"}},
            {"linkedinUrl": "https://www.linkedin.com/posts/x", "content": ""}]})
        self.assertEqual(len(linkedin), 1)
        self.assertEqual((linkedin[0]["profile"], linkedin[0]["published_on"], linkedin[0]["headline"]),
                         ("https://www.linkedin.com/in/ada", "2026-11-01", "Founder at Fig"))
        self.assertEqual(t.social_source_key(linkedin[0]), "linkedin:7000000000000000001")
        x = t.x_posts({"output": {"data": {"items": [
            {"id": 42, "authorUsername": "ada", "text": "We left Tool1.", "createdUtc": 1793836800},
            {"id": "nope", "authorUsername": "ada", "text": "skipped"}]}}})
        self.assertEqual([(post["author"], post["url"], post["kind"]) for post in x], [("@ada", "https://x.com/ada/status/42", "post")])
        self.assertEqual(t.x_posts({"output": {"found": False}}), [])
        page = t.x_page({"output": {"data": {"nextCursor": "c2", "items": [
            {"id": 43, "authorUsername": "ada", "authorName": "Ada  Example", "authorFollowers": 2521, "text": "We left Tool1."}]}}})
        self.assertEqual((page["next"], page["posts"][0]["name"], page["posts"][0]["headline"]), ("c2", "Ada Example", "Ada Example · 2,521 followers"))
        self.assertEqual(t.x_page({"output": {"found": False}}), {"posts": [], "next": None})

    def test_linkedin_job_ads_and_people_are_read_with_the_employer_attached(self):
        found = t.linkedin_jobs({"elements": [
            {"id": "42", "title": "RevOps Lead", "postedDate": "2026-11-01T09:00:00.000Z", "company": {"name": "Fig"}},
            {"id": "nope", "title": "Skipped", "company": {"name": "Fig"}}, {"id": "43", "title": "No company"}]})
        self.assertEqual(found, [{"id": "42", "url": "https://www.linkedin.com/jobs/view/42", "title": "RevOps Lead",
                                  "company": "Fig", "published_on": "2026-11-01"}])
        ad = {"element": {"jobState": "LISTED", "title": "RevOps Lead", "postedDate": "2026-11-01T09:00:00.000Z",
                          "descriptionText": "You will own our CRM.",
                          "hiringTeam": [{"linkedinUrl": "https://in.linkedin.com/in/ada", "name": "Ada Example"},
                                         {"linkedinUrl": "https://example.com/in/x", "name": "Not LinkedIn"}],
                          "company": {"name": "Fig", "linkedinUrl": "https://www.linkedin.com/company/fig/life", "employeeCount": 14,
                                      "industries": [{"name": "Software Development"}], "description": "Invoices for\nsmall teams."}}}
        job = t.linkedin_job(ad)
        self.assertEqual((job["company_url"], job["hiring_team"], job["published_on"]),
                         ("https://www.linkedin.com/company/fig", [{"profile": "https://www.linkedin.com/in/ada", "name": "Ada Example"}], "2026-11-01"))
        self.assertEqual(job["employer"], {"name": "Fig", "url": None, "employees": 14, "industry": "Software Development",
                                           "about": "Invoices for small teams."})
        self.assertIsNone(t.linkedin_job({"element": {**ad["element"], "jobState": "CLOSED"}}))
        people = t.linkedin_people({"elements": [
            {"linkedinUrl": "https://www.linkedin.com/in/ada", "name": "Ada Example", "position": "Co-founder  Fig"},
            {"linkedinUrl": "https://www.linkedin.com/company/fig", "name": "Not a person"}]})
        self.assertEqual(people, [{"profile": "https://www.linkedin.com/in/ada", "name": "Ada Example", "text": "Co-founder Fig"}])


if __name__ == "__main__":
    unittest.main()
