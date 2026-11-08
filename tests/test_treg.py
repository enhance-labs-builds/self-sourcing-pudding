from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

from rig import build_queue, discovery_terms, match_terms, read_json
from treg_adapter import LINKEDIN, PROFILE, SAFE_REPLAY_SECONDS, WEB, X, PendingCall, Treg, billing, bounded_call, journal, run_live


class TregSpendTest(TestCase):
    def test_problem_search_checks_approved_phrases_before_limiting_results(self):
        brief = {"signals": ["customer onboarding", "guided onboarding"], "alternatives": [],
                 "searches": [{"lane": "problem", "phrase": term}
                              for term in ("customer onboarding", "guided onboarding")],
                 "limits": {"source_age_days": 30}}
        client = Mock()
        client.preflight.return_value = {LINKEDIN: 2000, X: 600}

        def request(path, method, payload, headers):
            if path.endswith(LINKEDIN) and payload["search"] == "guided onboarding":
                result = {"elements": [
                    {"linkedinUrl": "https://www.linkedin.com/posts/noise", "content": "Unrelated launch"},
                    {"linkedinUrl": "https://www.linkedin.com/posts/relevant", "content": "Our customer onboarding needs work"},
                ]}
            elif path.endswith(LINKEDIN):
                result = {"elements": []}
            else:
                result = {"output": {"data": {"items": []}}}
            return 200, {"x-treg-cost-micro": "0"}, result

        client.request.side_effect = request
        with TemporaryDirectory() as root, patch.dict("os.environ", {"TREG_TOKEN": "test", "TREG_ORG": "team"}), \
                patch("treg_adapter.Treg", return_value=client):
            args = SimpleNamespace(searches=None, budget_usd="0.10", profiles=0, dry_run=False, results_per_search=1,
                                   out=Path(root) / "run", resume=False)
            corpus = run_live(brief, args, match_terms, discovery_terms(brief))
        self.assertEqual(len(corpus["observations"]), 1)
        self.assertEqual(corpus["observations"][0]["found_by"], [
            {"lane": "problem", "phrase": "guided onboarding", "matched_problem_terms": ["customer onboarding"]},
        ])

    def test_explicit_queries_run_on_both_channels_and_preserve_why_a_post_was_found(self):
        brief = {
            "signals": ["agent sandbox"], "alternatives": ["Daytona"],
            "searches": [
                {"lane": "problem", "phrase": "agent sandbox"},
                {"lane": "brand", "phrase": "boat.dev"},
                {"lane": "alternative", "phrase": "Daytona sandbox"},
            ],
            "limits": {"source_age_days": 30},
        }
        client = Mock()
        client.preflight.return_value = {LINKEDIN: 2_000, X: 600}
        client.request.side_effect = lambda path, *_: (200, {"x-treg-cost-micro": "0"}, {
            "elements": [
                {"linkedinUrl": "https://www.linkedin.com/posts/work", "content": "Our agent sandbox uses boat.dev."},
                {"linkedinUrl": "https://www.linkedin.com/posts/racing", "content": "Daytona racing this weekend."},
            ],
        } if path.endswith(LINKEDIN) else {
            "output": {"data": {"items": [
                {"authorUsername": "builder", "id": "123", "text": "We use Daytona sandbox for builds."},
            ]}},
        })
        with TemporaryDirectory() as root, patch.dict("os.environ", {"TREG_TOKEN": "test", "TREG_ORG": "team"}), \
                patch("treg_adapter.Treg", return_value=client):
            args = SimpleNamespace(searches=None, budget_usd="0.10", profiles=0, dry_run=False,
                                   out=Path(root) / "run", resume=False)
            corpus = run_live(brief, args, match_terms, discovery_terms(brief))

        self.assertEqual([call.args[2]["search"] for call in client.request.call_args_list[::2]],
                         ["agent sandbox", "boat.dev", "Daytona sandbox"])
        self.assertEqual([call.args[2]["query"].split(" since:")[0] for call in client.request.call_args_list[1::2]],
                         ['"agent sandbox"', '"boat.dev"', '"Daytona sandbox"'])
        by_channel = {post["channel"]: post["found_by"] for post in corpus["observations"]}
        self.assertEqual(len(corpus["observations"]), 2)
        self.assertEqual(by_channel, {"linkedin": brief["searches"][:2], "x": brief["searches"][2:]})

    def test_paired_queries_filter_collisions_and_keep_stories_out_of_social_review(self):
        brief = {
            "signals": ["customer support"], "alternatives": ["Sierra"],
            "searches": [
                {"lane": "alternative", "phrase": "Sierra", "workflow": ["customer support", "refund routing"],
                 "exclude_phrases": ["Tata Sierra"]},
                {"lane": "account", "phrase": "Example Bank", "workflow": ["refund routing"],
                 "seed_url": "https://example.com/customers/bank"},
            ],
            "customer_stories": [
                {"competitor": "Sierra", "site": "https://example.com/customers", "workflow": "customer support"},
            ],
            "limits": {"source_age_days": 30},
        }
        client = Mock()
        client.preflight.return_value = {LINKEDIN: 2_000, X: 600, WEB: 5_000}

        def request(path, method, payload, headers):
            if path.endswith(WEB):
                self.assertEqual(payload["q"], 'site:example.com/customers "customer support"')
                return 200, {"x-treg-cost-micro": "5000"}, {"web": {"results": [
                    {"url": "https://example.com/customers/bank?tracking=1", "title": "Example Bank"},
                    {"url": "https://example.com/customers/bank#top", "title": "Example Bank"},
                    {"url": "https://example.com/customers/"},
                    {"url": "https://example.com/blog/case-study"},
                    {"url": "https://elsewhere.example/customers/bank"},
                ]}}
            if path.endswith(LINKEDIN):
                return 200, {"x-treg-cost-micro": "2000"}, {"elements": [
                    {"linkedinUrl": "https://www.linkedin.com/posts/name-only", "content": "Sierra announced an event."},
                    {"linkedinUrl": "https://www.linkedin.com/posts/workflow-only", "content": "Our refund routing works."},
                    {"linkedinUrl": "https://www.linkedin.com/posts/wrong-entity", "content": "Tata Sierra customer support helped."},
                    {"linkedinUrl": "https://www.linkedin.com/posts/work", "content": "Example Bank uses Sierra for refund routing."},
                ]}
            return 200, {"x-treg-cost-micro": "600"}, {"output": {"data": {"items": [
                {"authorUsername": "builder", "id": "42", "text": "Sierra helps our customer support team."},
            ]}}}

        client.request.side_effect = request
        with TemporaryDirectory() as root, patch.dict("os.environ", {"TREG_TOKEN": "test", "TREG_ORG": "team"}), \
                patch("treg_adapter.Treg", return_value=client):
            args = SimpleNamespace(searches=None, budget_usd="0.0102", profiles=0, dry_run=False,
                                   out=Path(root) / "run", resume=False)
            corpus = run_live(brief, args, match_terms, discovery_terms(brief))
            queue = build_queue(brief, corpus)
            stories = read_json(args.out / "customer-story-queue.json")["stories"]

        client.preflight.assert_called_once_with({LINKEDIN, X, WEB})
        self.assertEqual(client.request.call_args_list[0].args[2]["search"],
                         '"Sierra" AND ("customer support" OR "refund routing")')
        self.assertEqual(client.request.call_args_list[1].args[2]["query"].split(" since:")[0],
                         '"Sierra" ("customer support" OR "refund routing")')
        self.assertEqual(client.request.call_args.args[3]["X-Treg-Route-Max-Cost"], "0.005000")
        self.assertEqual(len(stories), 1)
        self.assertEqual(stories[0]["url"], "https://example.com/customers/bank")
        self.assertEqual(stories[0]["status"], "needs_source_review")
        self.assertEqual(len(queue["candidates"]), 2)
        self.assertEqual([p["found_by"] for p in corpus["observations"]], [
            [{"lane": "alternative", "phrase": "Sierra", "workflow_matches": ["refund routing"]},
             {"lane": "account", "phrase": "Example Bank", "workflow_matches": ["refund routing"],
              "seed_url": "https://example.com/customers/bank"}],
            [{"lane": "alternative", "phrase": "Sierra", "workflow_matches": ["customer support"]}],
        ])

    def test_preflight_refuses_a_team_with_provider_keys(self):
        client = Treg("test-token", "demo-team")
        client.request = Mock(return_value=(200, {}, [{"name": "connected provider"}]))
        with self.assertRaisesRegex(ValueError, "no connected provider keys"):
            client.preflight({PROFILE})
        client.request.assert_called_once_with("/secrets")

    def test_remaining_budget_prevents_a_second_lookup_and_replay_is_local(self):
        client = Mock()
        client.request.return_value = (200, {"x-treg-cost-micro": "6400", "x-treg-call-id": "receipt"}, {"ok": True})
        plan = {"budget_micro": 10_000}
        with TemporaryDirectory() as root:
            out = Path(root) / "run"
            with journal(out, plan, "demo-team", False) as (path, state):
                first = bounded_call(client, path, state, PROFILE, {"url": "a"}, 6400, dict)
                self.assertEqual(first, {"ok": True})
                self.assertEqual(client.request.call_args.args[3]["X-Treg-Route-Max-Cost"], "0.010000")
                second = bounded_call(client, path, state, PROFILE, {"url": "b"}, 6400, dict)
                self.assertIsNone(second)
            with journal(out, plan, "demo-team", True) as (path, state):
                replay = bounded_call(client, path, state, PROFILE, {"url": "a"}, 6400, dict)
                self.assertEqual(replay, first)
            self.assertEqual(client.request.call_count, 1)

    def test_timeout_recovers_the_original_charge_and_blocks_unrelated_requests(self):
        client = Mock()
        client.request.side_effect = [
            ValueError("Connection dropped"),
            (409, {"x-treg-cost-micro": "0"}, {}),
            (200, {"x-treg-cost-micro": "0", "x-treg-idempotent-replay": "true"}, {"ok": True}),
            (200, {"x-treg-cost-micro": "0", "x-treg-idempotent-replay": "true",
                   "x-treg-original-cost-micro": "6400", "x-treg-call-id": "receipt"}, {"ok": True}),
        ]
        with TemporaryDirectory() as root:
            out = Path(root) / "run"
            plan = {"budget_micro": 10_000}

            def lookup(url="a", resume=True, caller="original"):
                with journal(out, plan, "demo-team", resume, caller=caller) as (path, state):
                    return bounded_call(client, path, state, PROFILE, {"url": url}, 6400, dict)

            with self.assertRaisesRegex(PendingCall, "Connection dropped"):
                lookup(resume=False)
            with self.assertRaisesRegex(PendingCall, "different request"):
                lookup("b")
            with self.assertRaisesRegex(PendingCall, "original TREG_TOKEN"):
                lookup(caller="rotated")
            with self.assertRaisesRegex(PendingCall, "still processing"):
                lookup()
            with self.assertRaisesRegex(PendingCall, "without a settled receipt"):
                lookup()
            self.assertEqual(lookup(), {"ok": True})
            self.assertEqual(lookup(), {"ok": True})
            self.assertIsNone(lookup("b"))
            self.assertEqual(billing(read_json(out / "treg-run.json")), 6400)
            self.assertEqual(client.request.call_count, 4)
            self.assertTrue(all(call == client.request.call_args_list[0] for call in client.request.call_args_list))

    def test_expired_or_unretained_result_never_sends_another_call(self):
        for reason in ("expired", "unretained"):
            with self.subTest(reason=reason), TemporaryDirectory() as root:
                client = Mock()
                client.request.side_effect = (ValueError("Connection dropped") if reason == "expired"
                                              else lambda *_: (410, {}, {"detail": {"call_id": "receipt"}}))
                out = Path(root) / "run"
                plan = {"budget_micro": 10_000}
                with patch("treg_adapter.time", return_value=100), self.assertRaises(PendingCall):
                    with journal(out, plan, "demo-team", False) as (path, state):
                        bounded_call(client, path, state, PROFILE, {"url": "a"}, 6400, dict)
                moment = 100 + (SAFE_REPLAY_SECONDS if reason == "expired" else 1)
                with patch("treg_adapter.time", return_value=moment), self.assertRaisesRegex(PendingCall, "cannot safely replay"):
                    with journal(out, plan, "demo-team", True) as (path, state):
                        bounded_call(client, path, state, PROFILE, {"url": "a"}, 6400, dict)
                self.assertEqual(client.request.call_count, 1)
