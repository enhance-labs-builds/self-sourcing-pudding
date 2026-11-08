from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import Mock

from treg_adapter import PROFILE, Treg, bounded_call, journal


class TregSpendTest(TestCase):
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
