from contextlib import redirect_stdout
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import Mock, patch

import rig
from treg_adapter import COMPANY, LINKEDIN, PROFILE, VERIFY_EMAIL, WORK_EMAIL, X
from work_email import candidate_email, verified, work_address


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

    def test_live_pilot_enriches_before_review_under_the_same_cap(self):
        now = datetime.now(timezone.utc)
        profiles = [f"https://www.linkedin.com/in/sourcing-rig-fixture-{i}" for i in range(2)]
        company = "https://www.linkedin.com/company/sourcing-rig-fixture"
        address = "operator@example.com"
        excerpt = "We built a preview deploy to test each change."
        prices = {LINKEDIN: 2_000, X: 600, PROFILE: 6_400, COMPANY: 4_000, WORK_EMAIL: 11_000, VERIFY_EMAIL: 12_250}
        responses = {
            LINKEDIN: {"elements": [{"linkedinUrl": f"https://www.linkedin.com/posts/fixture-{i}",
                                    "content": excerpt, "postedAt": {"date": now.isoformat()},
                                    "author": {"name": "Example Operator", "linkedinUrl": url,
                                               "info": "Platform Engineer"}} for i, url in enumerate(profiles)]},
            X: {"output": {"data": {"items": []}}},
            PROFILE: {"element": {"linkedinUrl": profiles[0], "firstName": "Example", "lastName": "Operator",
                                  "currentPosition": [{"position": "Platform Engineer", "companyName": "Example Co",
                                                       "companyLinkedinUrl": company}]}},
            COMPANY: {"element": {"linkedinUrl": company, "name": "Example Co", "website": "https://example.com"}},
            WORK_EMAIL: {"output": {"found": True, "data": {"linkedinUrl": profiles[0], "emails": [{"email": address}]}}},
            VERIFY_EMAIL: {"data": {"email": address, "status": "valid", "accept_all": False, "webmail": False}},
        }
        client = Mock()
        client.preflight.side_effect = client.endpoint_prices.side_effect = lambda endpoints: {e: prices[e] for e in endpoints}

        def request(path, method, params, headers):
            endpoint = path.removeprefix("/call/")
            self.assertGreaterEqual(float(headers["X-Treg-Route-Max-Cost"]), prices[endpoint] / 1_000_000)
            return 200, {"x-treg-cost-micro": str(prices[endpoint])}, responses[endpoint]

        client.request.side_effect = request
        with TemporaryDirectory() as root, redirect_stdout(StringIO()), \
                patch("url_seed.fetch_page", return_value=("https://example.com/", "<title>Example</title>")), \
                patch.dict("os.environ", {"TREG_TOKEN": "test", "TREG_ORG": "fixture"}), \
                patch("treg_adapter.Treg", return_value=client):
            project = Path(root) / "pilot"
            votes = Path(root) / "votes.json"

            def run(*args):
                rig.main(["pilot", *args, "--project", str(project)])

            run("start", "example.com", "--starter", str(rig.EXAMPLE / "brief.toml"))
            run("approve", "--yes")
            run("run", "--run", "live", "--budget-usd", "0.042", "--searches", "1", "--profiles", "2")
            out = project / "runs/live"
            cards = rig.read_json(out / "queue.json")["candidates"]
            self.assertEqual(len(cards), 1)
            self.assertEqual(cards[0]["work_email"]["address"], address)
            self.assertEqual(rig.read_json(out / "preview.json")["spend_usd"], 0.03625)
            self.assertEqual([c.args[0].removeprefix("/call/") for c in client.request.call_args_list], list(prices))
            rig.write_json(votes, {cards[0]["id"]: {"vote": "yay", "source_id": cards[0]["sources"][0]["id"],
                                                    "excerpt": excerpt, "evidence_kind": "explicit_work"}})
            run("review", "--run", "live", "--votes", str(votes))
            self.assertEqual(rig.read_json(out / "shortlist.json")["leads"][0]["work_email"], address)

    def test_email_requires_an_exact_work_address(self):
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
        result = candidate_email({"profile_url": profile, "company": "Stealth Startup",
                                  "company_url": "https://www.linkedin.com/company/stealth-startup"},
                                 None, None, None, None)
        self.assertEqual(result, {"status": "employer_unconfirmed"})

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
