from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

from rig import discovery_terms, match_terms
from treg_adapter import LINKEDIN, PROFILE, X, Treg, bounded_call, journal, run_live


class TregSpendTest(TestCase):
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

    def test_uncertain_call_preserves_reservation_and_blocks_resume(self):
        client = Mock()
        client.request.side_effect = ValueError("Connection dropped")
        with TemporaryDirectory() as root:
            out = Path(root) / "run"
            plan = {"budget_micro": 10_000}
            with self.assertRaisesRegex(ValueError, "Connection dropped"):
                with journal(out, plan, "demo-team", False) as (path, state):
                    bounded_call(client, path, state, PROFILE, {"url": "a"}, 6400, dict)
            with self.assertRaisesRegex(ValueError, "uncertain outcome"):
                with journal(out, plan, "demo-team", True):
                    self.fail("The outstanding charge should block paid calls")
            self.assertEqual(client.request.call_count, 1)
