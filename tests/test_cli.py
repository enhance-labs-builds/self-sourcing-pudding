import csv
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


CLI = Path(__file__).resolve().parents[1] / "rig.py"


class OfflineRigTest(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)

    def rig(self, *args, stdin="", exit_code=0):
        run = subprocess.run(
            [sys.executable, str(CLI), *args], cwd=self.root, input=stdin,
            text=True, capture_output=True, timeout=10,
        )
        self.assertEqual(run.returncode, exit_code, run.stdout + run.stderr)
        return run

    def read(self, path):
        return json.loads((self.root / path).read_text())

    def test_demo_preserves_evidence_and_holds(self):
        self.rig("demo")
        review = self.read("runs/demo/review.json")
        by_id = {row["id"]: row["outcome"] for row in review["outcomes"]}
        self.assertEqual(by_id, {
            "person:devon": "shortlisted", "person:nia": "shortlisted",
            "person:mara": "shortlisted", "person:theo": "shortlisted", "person:lena": "shortlisted",
            "person:caleb": "shortlisted", "person:priya": "shortlisted", "person:jonah": "shortlisted",
            "person:elena": "shortlisted", "person:mateo": "shortlisted",
            "person:jules": "passed", "person:sam": "held", "person:val": "passed",
            "person:eli": "held", "person:imani": "held", "source:unbound-x": "held",
        })
        shortlist = self.read("runs/demo/shortlist.json")
        self.assertEqual(shortlist["mode"], "example")
        leads = shortlist["leads"]
        nia = next(lead for lead in leads if lead["person_id"] == "nia")
        self.assertEqual({item["channel"] for item in nia["sightings"]}, {"x", "linkedin"})
        self.assertTrue(all(lead["history_status"] == "unchecked" for lead in leads))
        with (self.root / "runs/demo/shortlist.csv").open(newline="") as file:
            rows = {row["name"]: row for row in csv.DictReader(file)}
        with (CLI.parent / "examples/ramp-demo/shortlist.csv").open(newline="") as file:
            self.assertEqual(list(rows.values()), list(csv.DictReader(file)))
        self.assertEqual({row["source_url"] for row in rows.values()}, {lead["source_url"] for lead in leads})
        self.assertEqual(rows["Nia Alder"]["work_email"], "nia@junipervale.example")
        self.assertEqual(rows["Nia Alder"]["work_email_status"], "example")
        self.assertEqual(rows["Devon Flint"]["work_email"], "")

    def test_guided_brief_changes_discovery_and_can_be_reviewed(self):
        self.rig("init", stdin="\n".join([
            "Purchasing approvals", "Slow security reviews",
            "Procurement Operations", "security review", "Zip", "Promotional posts",
            "Describes owning an approval workflow", "Routes purchase requests for review",
            "Vendor promoting a feature", "",
        ]))
        self.assertIn("Search signals: security review", self.rig("plan").stdout)
        self.rig("source", "--out", "runs/first")
        queue = self.read("runs/first/queue.json")
        self.assertEqual([item["id"] for item in queue["candidates"]],
                         ["person:devon", "person:val", "person:mateo", "person:theo", "source:unbound-x"])
        self.rig("review", "--run", "runs/first",
                 stdin="w\n1\n\nOwns purchase approvals.\np\nPromotional post.\n\n\n")
        self.assertEqual([lead["person_id"] for lead in self.read("runs/first/shortlist.json")["leads"]],
                         ["devon"])

        path = self.root / "brief.toml"
        path.write_text(path.read_text().replace("Describes owning an approval workflow", "Owns stalled purchase approvals"))
        self.rig("source", "--out", "runs/changed")
        error = self.rig("review", "--run", "runs/changed", "--decisions",
                         "runs/first/review.json", exit_code=2)
        self.assertIn("different queue", error.stderr)

    def test_review_cannot_borrow_evidence_or_override_identity_hold(self):
        self.rig("demo")
        original = self.read("runs/demo/review.json")
        attempts = [
            ("person:sam", "nia-linkedin", "I run procurement intake", "attributed to this person"),
            ("source:unbound-x", "unbound-x", "take five days", "no verified profile binding"),
        ]
        for candidate, source, excerpt, error in attempts:
            with self.subTest(candidate=candidate):
                review = {**original, "decisions": {**original["decisions"], candidate: {
                    "decision": "qualify", "source_id": source, "excerpt": excerpt,
                    "evidence_kind": "firsthand_problem", "reason": "Attempt to bypass the gate.",
                }}}
                (self.root / "edited.json").write_text(json.dumps(review))
                failure = self.rig("review", "--run", "runs/demo", "--decisions", "edited.json", exit_code=2)
                self.assertIn(error, failure.stderr)
                self.assertEqual(self.read("runs/demo/review.json"), original)


if __name__ == "__main__":
    unittest.main()
