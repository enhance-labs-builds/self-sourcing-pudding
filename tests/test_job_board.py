import sys
import unittest
from pathlib import Path

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


if __name__ == "__main__":
    unittest.main()
