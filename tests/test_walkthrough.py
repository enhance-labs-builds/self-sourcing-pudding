from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

import rig


class WalkthroughTest(TestCase):
    def test_fresh_example_from_url_to_saved_votes(self):
        html = ("<title>Voice guidance for every user</title>"
                "<meta name='description' content='Screen share voice agents for your customer lifecycle'>"
                "<h2>Customer onboarding</h2>")
        answers = ["example.com", "a", "y", "y", "", "", "", "", "y", "n", "n", ""]
        console = StringIO()
        with TemporaryDirectory() as folder, redirect_stdout(console), \
                patch("url_seed.fetch_page", return_value=("https://example.com/", html)), \
                patch("treg_adapter.Treg") as provider, patch("builtins.input", side_effect=answers):
            project = Path(folder) / "new"
            rig.main(["walk", "--project", str(project)])
            out = project / "runs/example-preview"
            brief = rig.read_brief(project / "brief.toml")
            preview = rig.read_json(out / "preview.json")
            shortlist = rig.read_json(out / "shortlist.json")
            review = rig.read_json(out / "review.json")
            state = rig.read_json(project / "state.json")
        provider.assert_not_called()
        self.assertEqual(brief["signals"][0], "customer onboarding")
        self.assertEqual(preview["spend_usd"], 0)
        self.assertEqual(preview["held"], 1)
        self.assertEqual(shortlist["mode"], "example")
        self.assertEqual(shortlist["leads"][0]["work_email_status"], "example")
        self.assertTrue(shortlist["leads"][0]["work_email"].endswith(".example"))
        self.assertEqual({v["vote"] for v in state["feedback"].values()}, {"yay", "nay"})
        self.assertTrue(any(r["outcome"] == "held" and "Saved for follow-up" in r["reason"] for r in review["outcomes"]))
        self.assertIn("Profiles, posts and work emails below are fictional", console.getvalue())
