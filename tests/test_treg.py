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


if __name__ == "__main__":
    unittest.main()
