from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

import rig
from work_email import due, verified, work_address


class PilotTest(TestCase):
    def test_edited_brief_needs_approval_and_feedback_survives_a_fresh_run(self):
        fixture = rig.EXAMPLE
        corpus = rig.read_json(fixture / "corpus.json")
        for person in corpus["people"]:
            person["profile_url"] = f"https://www.linkedin.com/in/sourcing-rig-fixture-{person['id']}"
        html = ('<title>Agent sandboxes</title><meta name="description" content="Linux VMs for agents">'
                '<a href="https://x.com/example">X</a><a href="/compare/example-vs-sandboxlane">Compare</a>')
        with TemporaryDirectory() as root, redirect_stdout(StringIO()), \
                patch("url_seed.fetch_page", return_value=("https://example.com/", html)):
            project = Path(root) / "pilot"
            path = Path(root) / "corpus.json"
            votes = Path(root) / "votes.json"
            rig.write_json(path, corpus)

            def run(*args):
                return rig.main(["pilot", *args, "--project", str(project)])

            run("start", "example.com", "--starter", str(fixture / "brief.toml"), "--target", "1")
            state_path = project / "state.json"
            seed = rig.read_json(state_path)["seed"]
            self.assertEqual(seed["linked_profiles"], {"x": "https://x.com/example"})
            self.assertEqual(list(seed["comparisons"]), ["sandboxlane"])
            with self.assertRaises(SystemExit) as unapproved:
                run("run", "--run", "first", "--corpus", str(path))
            self.assertEqual(unapproved.exception.code, 2)
            run("approve", "--yes")
            run("run", "--run", "first", "--corpus", str(path))
            first = project / "runs/first"
            self.assertEqual(rig.read_json(first / "preview.json")["max_candidates"], 20)
            self.assertTrue(rig.read_json(first / "holds.json")["candidates"])
            yes = rig.read_json(fixture / "decisions.json")["person:nia"]
            yes.pop("decision")
            rig.write_json(votes, {"person:nia": {**yes, "vote": "yay"},
                                   "person:jules": {"vote": "nay", "reason_code": "weak_evidence"}})
            run("review", "--run", "first", "--votes", str(votes))
            self.assertEqual([p["person_id"] for p in rig.read_json(first / "shortlist.json")["leads"]], ["nia"])
            self.assertEqual({v["vote"] for v in rig.read_json(state_path)["feedback"].values()}, {"yay", "nay"})
            run("run", "--run", "second", "--corpus", str(path))
            second = project / "runs/second"
            self.assertEqual(rig.read_json(second / "preview.json")["already_reviewed"], 2)
            self.assertFalse({"person:nia", "person:jules"} &
                             {c["id"] for c in rig.read_json(second / "queue.json")["candidates"]})
            run("run", "--run", "batch", "--corpus", str(path), "--batch")
            self.assertEqual(rig.read_json(project / "runs/batch/preview.json")["candidates"], 1)
            draft = project / "brief.toml"
            draft.write_text(draft.read_text().replace("batch_target = 1", "batch_target = 2"))
            with self.assertRaises(SystemExit) as edited:
                run("run", "--run", "edited", "--corpus", str(path))
            self.assertEqual(edited.exception.code, 2)

    def test_email_requires_fresh_nonreply_and_exact_work_address(self):
        now = datetime(2026, 11, 9, 9, tzinfo=timezone.utc)
        event = {"status": "pending", "source_url": "https://example.com/event",
                 "linkedin_sent_at": (now - timedelta(hours=78)).isoformat(),
                 "status_checked_at": (now - timedelta(hours=1)).isoformat()}
        self.assertTrue(due(event, now))
        self.assertFalse(due({**event, "status": "replied"}, now))
        self.assertFalse(due({**event, "linkedin_sent_at": (now - timedelta(hours=71)).isoformat()}, now))
        self.assertFalse(due({**event, "status_checked_at": (now - timedelta(hours=25)).isoformat()}, now))
        profile = "https://www.linkedin.com/in/sourcing-rig-fixture"
        address = "operator@example.com"
        response = {"output": {"found": True, "data": {"linkedinUrl": profile, "emails": [
            {"email": address}, {"email": "operator@example.org"}, {"email": "info@example.com"},
        ]}}}
        self.assertEqual(work_address(response, profile, "example.com"), address)
        self.assertIsNone(work_address(response, profile + "-someone-else", "example.com"))
        proof = {"email": address, "status": "valid", "accept_all": False, "webmail": False}
        self.assertTrue(verified({"data": proof}, address))
        self.assertFalse(verified({"data": {**proof, "accept_all": True}}, address))

    def test_reviewed_x_identity_merges_with_the_same_linkedin_profile(self):
        from pilot import attach_identities

        corpus = rig.read_json(rig.EXAMPLE / "corpus.json")
        person = next(p for p in corpus["people"] if p["id"] == "nia")
        person["profile_url"] = "https://www.linkedin.com/in/sourcing-rig-fixture-nia"
        source = next(s for s in corpus["observations"] if s.get("person_id") == "nia" and s["channel"] == "x")
        del source["person_id"]
        binding = {"source_url": source["url"], "author": source["author"], "profile_url": person["profile_url"],
                   "binding_source": "https://example.com/author-bio", "role_source": "https://example.com/team"}
        with self.assertRaisesRegex(ValueError, "exact source URL and author"):
            attach_identities(corpus, [{**binding, "author": "A different author"}], rig)
        attach_identities(corpus, [binding], rig)
        queue = rig.build_queue(rig.read_brief(rig.EXAMPLE / "brief.toml"), corpus)
        row = next(c for c in queue["candidates"] if c["id"] == "person:nia")
        self.assertEqual({s["channel"] for s in row["sources"]}, {"linkedin", "x"})
        self.assertEqual(source["binding_source"], binding["binding_source"])
