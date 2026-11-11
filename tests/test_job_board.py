import io
import json
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import job_board


class JobBoardTest(unittest.TestCase):
    def test_only_single_ads_on_known_boards_are_accepted(self):
        self.assertEqual(job_board.posting_url("https://boards.greenhouse.io/fig/jobs/12345"),
                         "https://job-boards.greenhouse.io/fig/jobs/12345")
        self.assertEqual(job_board.posting_url("https://jobs.ashbyhq.com/Fig/0BE1F65B-4731-48B3-AC60-93A269266494/apply"),
                         "https://jobs.ashbyhq.com/Fig/0be1f65b-4731-48b3-ac60-93a269266494")
        self.assertEqual(job_board.posting_url("https://fig.wd5.myworkdayjobs.com/en-US/careers/job/Remote/RevOps_R-1"),
                         "https://fig.wd5.myworkdayjobs.com/en-US/careers/job/Remote/RevOps_R-1")
        for bad in ("https://job-boards.greenhouse.io/fig", "http://jobs.lever.co/fig/0be1f65b-4731-48b3-ac60-93a269266494",
                    "https://jobs.ashbyhq.com/fig/../x", "https://example.com/jobs/1", "https://user@jobs.lever.co/fig/1"):
            self.assertIsNone(job_board.posting_url(bad), bad)

    def test_roles_and_company_names_compare_without_noise(self):
        self.assertEqual(job_board.role_words("VP of Customer Experience & Ops"),
                         {"vice", "president", "customer", "experience", "operations"})
        self.assertEqual(job_board.company_key("Fig, Inc."), "fig")
        self.assertEqual(job_board.owner_search_query("Fig", ["Head of Revenue Operations", "VP Sales"]),
                         'site:linkedin.com/in "Fig" ("revenue operations" OR "sales")')

    def test_posting_text_keeps_lines_and_drops_scripts(self):
        page = job_board.PostingHTML("<h2>About</h2><p>You will own our CRM.</p><script>var x = 1;</script><li>Ship weekly</li>")
        self.assertEqual(page.text_lines(), ["About", "You will own our CRM.", "Ship weekly"])

    def test_each_board_shape_is_accepted_and_its_address_rebuilt(self):
        uuid = "0be1f65b-4731-48b3-ac60-93a269266494"
        for given, expected in (
                (f"https://jobs.lever.co/fig/{uuid}/apply", f"https://jobs.lever.co/fig/{uuid}"),
                ("https://apply.workable.com/fig/j/AB12CD/apply", "https://apply.workable.com/fig/j/AB12CD"),
                ("https://jobs.smartrecruiters.com/Fig/743999-revops-lead", "https://jobs.smartrecruiters.com/Fig/743999")):
            self.assertEqual(job_board.posting_url(given), expected)

    def test_addresses_off_the_known_boards_are_refused(self):
        for bad in ("https://greenhouse.io.attacker.example/fig/jobs/1", "https://fig.wd5.myworkdayjobs.com.attacker.example/a/job/b",
                    "https://jobs.lever.co:8443/fig/0be1f65b-4731-48b3-ac60-93a269266494", "https://localhost/fig/jobs/1"):
            self.assertIsNone(job_board.posting_url(bad), bad)


class ReadPostingTest(unittest.TestCase):
    def reading(self, url, *bodies):
        script, asked = list(bodies), []

        def fetch(address):
            asked.append(address)
            return script.pop(0)

        with mock.patch.object(job_board, "fetch", fetch):
            return job_board.read_posting(url), asked

    def ld(self, **row):
        return f'<script type="application/ld+json">{json.dumps({"@type": "JobPosting", **row})}</script>'

    def test_greenhouse_is_read_from_its_api(self):
        body = json.dumps({"company_name": "Fig", "title": "RevOps", "first_published": "2026-11-01", "content": "<p>Own it</p>"})
        got, asked = self.reading("https://job-boards.greenhouse.io/fig/jobs/1", body)
        self.assertEqual(got, ("Fig", "RevOps", "2026-11-01", "<p>Own it</p>"))
        self.assertEqual(asked, ["https://boards-api.greenhouse.io/v1/boards/fig/jobs/1"])

    def test_structured_boards_are_read_from_the_page(self):
        page = self.ld(title="RevOps", datePosted="2026-11-01", description="Own it", hiringOrganization={"name": "Fig"})
        got, _ = self.reading("https://jobs.lever.co/fig/x", page)
        self.assertEqual(got, ("Fig", "RevOps", "2026-11-01", "Own it"))

    def test_an_expired_or_missing_posting_is_refused(self):
        expired = self.ld(title="R", validThrough="2020-01-01", description="d", hiringOrganization={"name": "Fig"})
        with self.assertRaisesRegex(ValueError, "closed"):
            self.reading("https://jobs.lever.co/fig/x", expired)
        with self.assertRaisesRegex(ValueError, "unavailable"):
            self.reading("https://jobs.lever.co/fig/x", "<p>Gone</p>")

    def test_smartrecruiters_joins_the_sections(self):
        body = json.dumps({"company": {"name": "Fig"}, "name": "RevOps", "releasedDate": "2026-11-01",
                           "jobAd": {"sections": {"a": {"text": "One"}, "b": {}, "c": {"text": "Two"}}}})
        got, asked = self.reading("https://jobs.smartrecruiters.com/Fig/743999", body)
        self.assertEqual(got, ("Fig", "RevOps", "2026-11-01", "<div>One</div><div>Two</div>"))
        self.assertEqual(asked, ["https://api.smartrecruiters.com/v1/companies/Fig/postings/743999"])

    def test_workday_is_read_from_its_api_and_closed_ads_refused(self):
        url = "https://fig.wd5.myworkdayjobs.com/en-US/careers/job/Remote/RevOps_R-1"
        row = {"hiringOrganization": {"name": "Fig"}, "jobPostingInfo": {"title": "RevOps", "startDate": "2026-11-01", "jobDescription": "Own it"}}
        got, asked = self.reading(url, json.dumps(row))
        self.assertEqual(got, ("Fig", "RevOps", "2026-11-01", "Own it"))
        self.assertEqual(asked, ["https://fig.wd5.myworkdayjobs.com/wday/cxs/fig/careers/job/Remote/RevOps_R-1"])
        row["jobPostingInfo"]["canApply"] = False
        with self.assertRaisesRegex(ValueError, "closed"):
            self.reading(url, json.dumps(row))

    def test_an_oversized_response_is_refused(self):
        class Response(io.BytesIO):
            def read1(self, size):
                return self.read(size)

        opener = mock.Mock()
        opener.open.return_value = Response(b"x" * (1024 * 1024 + 10))
        with mock.patch.object(job_board, "build_opener", return_value=opener), self.assertRaisesRegex(ValueError, "too large"):
            job_board.fetch("https://job-boards.greenhouse.io/fig/jobs/1")


if __name__ == "__main__":
    unittest.main()
