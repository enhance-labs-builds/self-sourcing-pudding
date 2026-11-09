from contextlib import redirect_stdout
import csv
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

import rig
from pilot import interactive_votes


class WalkthroughTest(TestCase):
    def test_unfamiliar_url_uses_guided_answers_and_regenerates_searches_after_edit(self):
        html = "<title>Fieldwork\x1b]0;changed title\x07</title><h1>Preventive maintenance for fleets</h1>"
        answers = ["https://example.com/?product=fleet#intro", "Keep vehicles out of the shop", "Fleet Manager", "preventive maintenance",
                   "FleetLedger", "municipal fleet", "q"]
        console = StringIO()
        with TemporaryDirectory() as folder, redirect_stdout(console), \
                patch("url_seed.fetch_page", return_value=("https://example.com/?product=fleet", html)) as fetch, \
                patch("builtins.input", side_effect=answers):
            project = Path(folder) / "new"
            rig.main(["walk", "--project", str(project)])
            path = project / "brief.toml"
            brief = rig.read_brief(path)
            self.assertEqual(brief["company_signals"], ["municipal fleet"])
            self.assertEqual(brief["searches"][1]["workflow"], ["preventive maintenance"])
            path.write_text(path.read_text().replace("preventive maintenance", "fleet uptime"))
            edited = rig.read_brief(path)
            self.assertEqual(edited["searches"][0]["phrase"], "fleet uptime")
            self.assertEqual(edited["searches"][1]["workflow"], ["fleet uptime"])
        fetch.assert_called_once_with("https://example.com/?product=fleet")
        self.assertNotIn("?product=fleet", brief["product"])
        self.assertNotIn("\x1b", console.getvalue())
        self.assertNotIn("\x07", console.getvalue())

    def test_fresh_example_from_url_to_saved_votes(self):
        html = ("<title>Voice guidance for every user</title>"
                "<meta name='description' content='Screen share voice agents for your customer lifecycle'>"
                "<h2>Customer onboarding</h2>")
        answers = ["example.com", "a", "y", "y", "", "", "They own onboarding and describe a failure.",
                   "", "y", "n", "n", "weak", "weak_evidence"]
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
            with patch("builtins.input", side_effect=["a"]):
                rig.main(["walk", "--project", str(project), "--run", "example-pass-2"])
            second = rig.read_json(project / "runs/example-pass-2/preview.json")
            self.assertGreaterEqual(second["already_reviewed"], 2)
            self.assertEqual(second["candidates"], 0)
            with (project / "runs/example-pass-2/shortlist.csv").open(newline="") as file:
                reader = csv.DictReader(file)
                self.assertEqual(reader.fieldnames, list(rig.CSV_FIELDS))
                self.assertEqual(list(reader), [])
            self.assertEqual(rig.read_json(project / "state.json")["feedback"], state["feedback"])
            with patch("builtins.input", side_effect=["y", "y", "", "", "They ran an onboarding experiment.", "w"]):
                rig.main(["pilot", "review", "--project", str(project), "--run", "example-preview", "--follow-ups"])
            self.assertEqual(len(rig.read_json(out / "shortlist.json")["leads"]), 2)
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
        self.assertIn("A manual step failed last week", shortlist["leads"][0]["excerpt"])
        self.assertIn("Choose one of:", console.getvalue())
        self.assertIn("Run this URL again with your saved brief and feedback", console.getvalue())

    def test_interrupted_review_keeps_the_completed_vote(self):
        queue = rig.build_queue(rig.read_brief(rig.EXAMPLE_BRIEF), rig.read_json(rig.EXAMPLE / "corpus.json"))
        console = StringIO()
        with redirect_stdout(console), patch("builtins.input", side_effect=["n", "weak_evidence", KeyboardInterrupt]):
            votes = interactive_votes(queue, rig)
        self.assertEqual(votes, {queue["candidates"][0]["id"]: {"vote": "nay", "reason_code": "weak_evidence"}})
        self.assertIn("Saving completed votes", console.getvalue())
