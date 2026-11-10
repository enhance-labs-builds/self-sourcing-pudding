import sys
import tempfile
import unittest
from pathlib import Path

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


class LedgerTest(unittest.TestCase):
    def ledger(self, budget=100_000, resume=False):
        if not resume:
            folder = tempfile.TemporaryDirectory()
            self.addCleanup(folder.cleanup)
            self.out = Path(folder.name) / "ledger"
        return t.journal(self.out, {"budget_micro": budget}, "org", resume, caller="me")

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
        self.assertEqual(oct((self.out / "treg-run.json").stat().st_mode & 0o777), "0o600")

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


class ParsingTest(unittest.TestCase):
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
