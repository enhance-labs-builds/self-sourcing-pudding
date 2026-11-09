from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

import rig
from pilot import channel_status, select_preview
from rig import build_queue, discovery_terms, match_terms, read_json
import treg_adapter
from treg_adapter import (COMPANY, LINKEDIN, LINKEDIN_COMMENTS, PROFILE, SAFE_REPLAY_SECONDS, WEB, X, X_PROFILE,
                          X_QUOTES, X_REPLIES, PendingCall, Treg, billing, bounded_call, employer_scope, journal,
                          run_live)


class TregSpendTest(TestCase):
    def test_spider_feeds_threads_and_verified_employer_posts_into_one_queue_on_resume(self):
        now = datetime.now(timezone.utc)
        company = "https://www.linkedin.com/company/fixture-team"
        other_company = "https://www.linkedin.com/company/other-team"
        profiles = {name: f"https://www.linkedin.com/in/fixture-{name}"
                    for name in ("seed", "coworker", "outsider", "teammate", "wrong-company", "reassigned")}
        seed_url = "https://www.linkedin.com/posts/fixture-seed"
        seed_x = "https://x.com/fixture/status/100"
        role = "Platform Engineer"
        first_person = "We built ephemeral stacks for our app team."
        workflow_phrase = "ephemeral environment"
        prices = {LINKEDIN: 4_000, X: 750, PROFILE: 6_400, LINKEDIN_COMMENTS: 4_000, X_REPLIES: 500, X_PROFILE: 220,
                  X_QUOTES: 5_000, COMPANY: 4_000}
        client = Mock()
        client.endpoint_prices.side_effect = lambda endpoints: {e: prices[e] for e in endpoints}
        client.preflight.side_effect = lambda endpoints, include_x_quotes=False: {
            **{e: prices[e] for e in endpoints}, **({X_QUOTES: 50_000} if include_x_quotes else {}),
        }
        requests = []

        def post(name):
            content = (f"We maintain an {workflow_phrase} for every pull request." if name == "teammate"
                       else f"{first_person} It uses an {workflow_phrase}.")
            if name == "reassigned":
                content = "This is a public roundup of ephemeral stacks and preview deploy tools."
            if name == "seed":
                content = f"Discussion of ephemeral stacks and how to run a preview deploy in an {workflow_phrase}."
            return {"linkedinUrl": f"https://www.linkedin.com/posts/fixture-{name}", "content": content,
                    "postedAt": {"date": now.isoformat()},
                    "author": {"name": name, "linkedinUrl": profiles[name], "info": role}}

        def comment(name, identifier):
            text = (f"At Fixture Company, we built ephemeral stacks using an {workflow_phrase}."
                    if name == "coworker" else "Same here.")
            return {"linkedinUrl": f"{seed_url}?commentUrn={identifier}", "commentary": text,
                    "createdAt": now.isoformat(),
                    "actor": {"name": name, "linkedinUrl": profiles[name], "position": role}}

        def request(path, method, params, headers):
            endpoint = path.removeprefix("/call/")
            requests.append((endpoint, params, headers))
            paid = {"x-treg-cost-micro": str(prices[endpoint])}
            if endpoint == LINKEDIN:
                if "authorsCompany" not in params:
                    return 200, paid, {"elements": [post("reassigned"), post("seed")]}
                self.assertEqual(params, {"authorsCompany": company,
                                          "search": f'"ephemeral stacks" OR "{workflow_phrase}"',
                                          "sortBy": "date", "page": 1})
                return 200, paid, {"elements": [post("teammate"), post("wrong-company"), post("reassigned")]}
            if endpoint == X:
                return 200, paid, {"output": {"data": {"items": [
                    {"id": "100", "text": first_person, "authorUsername": "fixture", "createdUtc": now.timestamp()},
                    {"id": "101", "text": first_person, "authorUsername": "already", "createdUtc": now.timestamp()},
                ]}}}
            if endpoint == LINKEDIN_COMMENTS:
                self.assertEqual(params, {"post": seed_url, "sortBy": "date", "page": 1})
                return 200, paid, {"elements": [comment("outsider", 1), comment("coworker", 2), comment("teammate", 3)]}
            if endpoint == X_REPLIES:
                self.assertEqual(params, {"url": seed_x, "limit": 8})
                attempts = [request for request in requests if request[0] == X_REPLIES]
                if len(attempts) == 1:
                    raise ValueError("Connection dropped after billing")
                self.assertEqual(attempts[0], attempts[1])
                replay = {"x-treg-cost-micro": "0", "x-treg-idempotent-replay": "true",
                          "x-treg-original-cost-micro": str(prices[endpoint])}
                return 200, replay, {"output": {"found": True, "data": {"items": [
                    {"id": "101", "text": first_person, "authorHandle": "ALREADY", "createdUtc": now.timestamp()},
                    {"id": "102", "text": "Same here.", "authorHandle": "newperson", "createdUtc": now.timestamp()},
                ]}}}
            if endpoint == X_QUOTES:
                self.assertEqual(params, {"id": "100", "max_results": 10,
                                          "tweet.fields": "author_id,created_at,referenced_tweets"})
                self.assertEqual(headers["X-Treg-Route-Max-Cost"], "0.050000")
                return 200, paid, {"data": [
                    {"id": "103", "author_id": "456", "text": "We ran into that issue too.", "created_at": now.isoformat(),
                     "referenced_tweets": [{"type": "quoted", "id": "100"}]},
                    {"id": "104", "author_id": "789", "text": "A different quote.", "created_at": now.isoformat(),
                     "referenced_tweets": [{"type": "quoted", "id": "999"}]},
                ]}
            if endpoint == X_PROFILE:
                handle = params["handle"]
                name = "Coworker Example" if handle == "fixture" else "Someone Else"
                profile = profiles["coworker" if handle == "fixture" else "outsider"]
                return 200, paid, {"output": {"found": True, "data": {
                    "handle": handle, "website": profile, "displayName": name,
                }}}
            if endpoint == COMPANY:
                org_url = params["url"]
                description = "We build regulated software for clinics." if org_url == other_company else "Developer tools."
                return 200, paid, {"element": {"linkedinUrl": org_url, "description": description}}
            self.assertEqual(endpoint, PROFILE)
            name = next(name for name, url in profiles.items() if url == params["url"])
            current_company = other_company if name in {"outsider", "wrong-company", "reassigned"} else company
            return 200, paid, {"element": {
                "linkedinUrl": params["url"], "firstName": name, "lastName": "Example",
                "currentPosition": [{"position": "Systems Lead" if name == "coworker" else role, "companyName": "Fixture Company",
                                     "companyLinkedinUrl": current_company}],
            }}

        client.request.side_effect = request
        with TemporaryDirectory() as folder, patch.dict("os.environ", {"TREG_TOKEN": "test", "TREG_ORG": "team"}), \
                patch("treg_adapter.Treg", return_value=client):
            out = Path(folder) / "run"
            brief_path = Path(folder) / "brief.toml"
            brief_path.write_text(f"""schema_version = 1
product = "Temporary environments for testing changes"
problem = "Teams need isolated environments for review."
target_roles = ["Platform Engineer"]
signals = ["ephemeral stacks", "preview deploy"]
company_signals = ["regulated software"]
qualifies = "The author describes maintaining their team's test environments."
more_like = "A practitioner describing their own setup."
less_like = "A roundup of tools."

[limits]
source_age_days = 30
role_age_days = 90
shortlist_size = 10

[[searches]]
lane = "problem"
phrase = "ephemeral stacks"

[[searches]]
lane = "alternative"
phrase = "Example Sandbox"
workflow = ["{workflow_phrase}"]
""", encoding="utf-8")
            options = ["live", "--brief", str(brief_path), "--out", str(out), "--budget-usd", "0.12",
                       "--searches", "1", "--profiles", "6", "--spider"]
            with self.assertRaises(SystemExit) as interrupted:
                rig.main(options)
            self.assertEqual(interrupted.exception.code, 2)
            self.assertFalse((out / "queue.json").exists())
            rig.main([*options, "--resume"])
            queue = read_json(out / "queue.json")
            corpus = read_json(out / "corpus.json")
            ledger = read_json(out / "treg-run.json")

        endpoints = [entry[0] for entry in requests]
        self.assertEqual(endpoints.count(LINKEDIN_COMMENTS), 1)
        self.assertEqual(endpoints.count(X_REPLIES), 2)
        self.assertEqual(endpoints.count(X_QUOTES), 1)
        self.assertEqual(endpoints.count(LINKEDIN), 2)
        self.assertEqual(endpoints.count(PROFILE), 6)
        self.assertEqual(next(params["url"] for endpoint, params, _ in requests if endpoint == PROFILE), profiles["coworker"])
        self.assertEqual(billing(ledger), 65_310)
        self.assertEqual(endpoints.count(COMPANY), 2)
        self.assertEqual(channel_status(ledger, treg_adapter)["linkedin"]["status"], "complete")
        sources = {source["url"]: source for source in corpus["observations"]}
        self.assertEqual(len(sources), 10)
        self.assertNotIn("https://www.linkedin.com/posts/fixture-wrong-company", sources)
        self.assertNotIn("https://x.com/ALREADY/status/101", sources)
        self.assertNotIn("https://x.com/i/web/status/104", sources)
        self.assertEqual(sources["https://x.com/already/status/101"]["kind"], "reply")
        self.assertNotIn("person_id", sources["https://x.com/already/status/101"])
        self.assertEqual(sources[seed_x]["person_id"], sources[f"{seed_url}?commentUrn=2"]["person_id"])
        self.assertEqual(sources[seed_x]["binding_source"], "https://x.com/fixture")
        self.assertEqual(sources["https://x.com/i/web/status/103"]["kind"], "quote")
        self.assertEqual([item["lane"] for item in sources["https://www.linkedin.com/posts/fixture-reassigned"]["found_by"]],
                         ["problem"])
        for child, parent in [(f"{seed_url}?commentUrn=2", seed_url), ("https://x.com/newperson/status/102", seed_x),
                              ("https://x.com/already/status/101", seed_x), ("https://x.com/i/web/status/103", seed_x)]:
            self.assertEqual(sources[child]["parent_id"], sources[parent]["id"])
            self.assertEqual(sources[child]["found_by"][-1]["seed_url"], parent)
        self.assertEqual(sources["https://www.linkedin.com/posts/fixture-teammate"]["found_by"][0]["lane"], "employer")
        self.assertEqual(sources["https://www.linkedin.com/posts/fixture-teammate"]["found_by"][0]["seed_url"],
                         f"{seed_url}?commentUrn=2")
        self.assertIn("At Fixture Company", sources["https://www.linkedin.com/posts/fixture-teammate"]
                      ["found_by"][0]["scope_excerpt"])
        self.assertEqual(sources["https://www.linkedin.com/posts/fixture-teammate"]["found_by"][0]["root_url"], seed_url)
        cards, held, _ = select_preview(queue, {}, 20, rig)
        names = [row["person"]["name"] for row in cards]
        teammate = next(row for row in cards if row["person"]["name"] == "teammate Example")
        self.assertEqual(len(teammate["sources"]), 2)
        self.assertEqual(names[0], "coworker Example")
        self.assertLess(names.index("coworker Example"), names.index("outsider Example"))
        outsider = next(row["person"] for row in cards if row["person"]["name"] == "outsider Example")
        self.assertNotIn("employer_signal", outsider)
        self.assertEqual(outsider["company_fit"], {
            "source_url": other_company, "excerpt": "We build regulated software for clinics.",
            "signals": ["regulated software"],
        })
        self.assertTrue(any(source["url"] == "https://x.com/newperson/status/102"
                            for row in held for source in row["sources"]))
        with self.assertRaisesRegex(ValueError, "attributed to this person"):
            rig.apply_reviews(queue, {"person:fixture-coworker": {
                "decision": "qualify", "reason": "test", "evidence_kind": "explicit_work",
                "source_id": sources[seed_url]["id"], "excerpt": first_person,
            }})

    def test_employer_pivot_needs_work_at_the_verified_employer(self):
        def scope(text):
            return employer_scope(text, "Fixture Company", ["preview deploy"], match_terms)

        self.assertEqual(scope("At Fixture Company we built a preview deploy."), "At Fixture Company we built a preview deploy.")
        for text in ("We built a preview deploy.", "At Former Company we built a preview deploy.",
                     "At Fixture Company Labs we built a preview deploy.",
                     "At Fixture Company we built a preview deploy for a client.",
                     "At Fixture Company we built a preview deploy as a side project."):
            with self.subTest(text=text):
                self.assertIsNone(scope(text))

    def test_spider_skips_followups_when_the_budget_cannot_cover_them(self):
        now = datetime.now(timezone.utc)
        client = Mock()
        client.preflight.return_value = {LINKEDIN: 4_000, X: 750}
        client.endpoint_prices.side_effect = lambda endpoints: {e: 500 for e in endpoints}
        client.request.side_effect = [
            (200, {"x-treg-cost-micro": "4000"}, {"elements": [
                {"linkedinUrl": "https://www.linkedin.com/posts/fixture", "content": "We built a preview deploy.",
                 "postedAt": {"date": now.isoformat()}},
            ]}),
            (200, {"x-treg-cost-micro": "750"}, {"output": {"data": {"items": [
                {"authorUsername": "fixture", "id": "10", "text": "We built a preview deploy.",
                 "createdUtc": now.timestamp()},
            ]}}}),
        ]
        with TemporaryDirectory() as folder, patch.dict("os.environ", {"TREG_TOKEN": "test", "TREG_ORG": "team"}), \
                patch("treg_adapter.Treg", return_value=client):
            brief = {"signals": ["preview deploy"], "alternatives": [], "limits": {"source_age_days": 30}}
            args = SimpleNamespace(searches=1, budget_usd="0.005", profiles=0, spider=True, dry_run=False,
                                   out=Path(folder) / "run", resume=False)
            corpus = run_live(brief, args, match_terms, discovery_terms(brief))
            self.assertEqual(billing(read_json(args.out / "treg-run.json")), 4_750)
        self.assertEqual(client.request.call_count, 2)
        self.assertEqual(len(corpus["observations"]), 2)

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
            "signals": ["agent sandbox"], "alternatives": ["Example Sandbox"],
            "searches": [
                {"lane": "problem", "phrase": "agent sandbox"},
                {"lane": "brand", "phrase": "Example Build"},
                {"lane": "alternative", "phrase": "Example Sandbox workspace"},
            ],
            "limits": {"source_age_days": 30},
        }
        client = Mock()
        client.preflight.return_value = {LINKEDIN: 2_000, X: 600}
        client.request.side_effect = lambda path, *_: (200, {"x-treg-cost-micro": "0"}, {
            "elements": [
                {"linkedinUrl": "https://www.linkedin.com/posts/work", "content": "Our agent sandbox uses Example Build."},
                {"linkedinUrl": "https://www.linkedin.com/posts/release", "content": "Example Sandbox is hiring."},
            ],
        } if path.endswith(LINKEDIN) else {
            "output": {"data": {"items": [
                {"authorUsername": "builder", "id": "123", "text": "We use an Example Sandbox workspace for builds."},
            ]}},
        })
        with TemporaryDirectory() as root, patch.dict("os.environ", {"TREG_TOKEN": "test", "TREG_ORG": "team"}), \
                patch("treg_adapter.Treg", return_value=client):
            args = SimpleNamespace(searches=None, budget_usd="0.10", profiles=0, dry_run=False,
                                   out=Path(root) / "run", resume=False)
            corpus = run_live(brief, args, match_terms, discovery_terms(brief))

        self.assertEqual([call.args[2]["search"] for call in client.request.call_args_list[::2]],
                         ["agent sandbox", "Example Build", "Example Sandbox workspace"])
        self.assertEqual([call.args[2]["query"].split(" since:")[0] for call in client.request.call_args_list[1::2]],
                         ['"agent sandbox"', '"Example Build"', '"Example Sandbox workspace"'])
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

    def test_quote_preflight_requires_a_metered_read_only_x_connection(self):
        client = Treg("test-token", "demo-team")
        scopes = ["tweet.read", "users.read", "offline.access"]
        metered = True

        def request(path, **_kwargs):
            data = {
                "/secrets": [{"id": 1, "kind": "oauth"}],
                "/tools": [{"base_url": "https://api.x.com", "bindings": [{"secret_id": 1, "injector": "oauth"}]}],
                "/connections": [{"id": 1, "kind": "oauth", "provider": "x", "scopes": scopes}],
                f"/catalog/endpoints/{X_QUOTES}/access": {"tier": "tool", "metered": metered},
                f"/catalog/endpoints/{X_QUOTES}": {"endpoint": {"method": "GET", "platform_eligible": True,
                    "cost": {"type": "per_result", "unit": "post", "currency": "USD", "usd": 0.005}}},
            }[path]
            return 200, {}, data

        client.request = Mock(side_effect=request)
        self.assertEqual(client.preflight(set(), include_x_quotes=True), {X_QUOTES: 50_000})
        metered = False
        self.assertEqual(client.preflight(set(), include_x_quotes=True), {})
        scopes.append("tweet.write")
        with self.assertRaisesRegex(ValueError, "read-only X connection"):
            client.preflight(set(), include_x_quotes=True)

    def test_spider_resume_keeps_an_earlier_skip_when_the_endpoint_returns(self):
        client = Mock()
        replay = {"x-treg-cost-micro": "0", "x-treg-idempotent-replay": "true",
                  "x-treg-original-cost-micro": "500"}
        client.request.side_effect = [ValueError("Connection dropped"), (200, replay, {"ok": True})]
        comment_params = {"post": "https://www.linkedin.com/posts/fixture"}
        reply_params = {"url": "https://x.com/fixture/status/1"}
        plan = {"budget_micro": 20_000, "spider": True}
        with TemporaryDirectory() as folder:
            out = Path(folder) / "run"
            with journal(out, plan, "demo-team", False) as (path, state):
                self.assertIsNone(bounded_call(client, path, state, LINKEDIN_COMMENTS, comment_params, None, dict))
                with self.assertRaises(PendingCall):
                    bounded_call(client, path, state, X_REPLIES, reply_params, 14_000, dict)
            with journal(out, plan, "demo-team", True) as (path, state):
                self.assertIsNone(bounded_call(client, path, state, LINKEDIN_COMMENTS, comment_params, 5_000, dict))
                self.assertEqual(bounded_call(client, path, state, X_REPLIES, reply_params, 14_000, dict), {"ok": True})
                self.assertEqual(billing(state), 500)
        self.assertEqual([item.args[0] for item in client.request.call_args_list], [f"/call/{X_REPLIES}"] * 2)

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
