import contextlib
import http.client
import io
import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "examples")]

import make_sample
import pudding
import review_page


class ReviewPageTest(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.project = Path(folder.name)
        with contextlib.redirect_stdout(io.StringIO()):
            make_sample.build(folder.name)
        (self.project / "review.json").write_text("{}")
        self.rows = pudding.shortlist_rows(self.project)[0]
        self.first = self.rows[0]["profile_url"]
        self.httpd, _ = review_page.server(self.project, 0)
        self.addCleanup(self.httpd.server_close)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.addCleanup(self.httpd.shutdown)
        self.port = self.httpd.server_address[1]
        self.own = f"127.0.0.1:{self.port}"

    def send(self, method, path, body=None, **headers):
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        self.addCleanup(connection.close)
        names = {name.replace("_", "-"): value for name, value in headers.items()}
        connection.putrequest(method, path, skip_host=True, skip_accept_encoding=True)
        connection.putheader("Host", names.pop("Host", self.own))
        for name, value in names.items():
            connection.putheader(name, value)
        connection.endheaders(body)
        response = connection.getresponse()
        return response.status, dict(response.getheaders()), response.read()

    def vote(self, payload, **headers):
        body = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
        return self.send("POST", "/vote", body, **{"Content_Type": "application/json", "Content_Length": str(len(body)), **headers})

    def saved(self):
        return json.loads((self.project / "review.json").read_text())

    def test_the_server_listens_on_this_computer_only(self):
        self.assertEqual(self.httpd.server_address[0], "127.0.0.1")

    def test_responses_carry_the_browser_protections(self):
        for path in ("/", "/data", "/missing"):
            headers = self.send("GET", path)[1]
            self.assertIn("frame-ancestors 'none'", headers["Content-Security-Policy"])
            self.assertIn("default-src 'none'", headers["Content-Security-Policy"])
            self.assertEqual((headers["X-Content-Type-Options"], headers["Referrer-Policy"], headers["Cache-Control"]),
                             ("nosniff", "no-referrer", "no-store"))

    def test_the_page_loads_nothing_from_elsewhere(self):
        page = self.send("GET", "/")[2].decode()
        self.assertNotIn("<script src", page)
        self.assertNotIn("<link", page)
        self.assertNotIn("innerHTML", page)

    def test_a_hostname_controlled_by_another_site_is_refused(self):
        self.assertEqual(self.send("GET", "/data", Host="attacker.example:8765")[0], 403)
        self.assertEqual(self.vote({"profile_url": self.first, "vote": "yes"}, Host="attacker.example")[0], 403)
        self.assertEqual(self.saved(), {})

    def test_localhost_works_as_well_as_the_address(self):
        self.assertEqual(self.send("GET", "/data", Host=f"localhost:{self.port}")[0], 200)

    def test_a_post_from_another_origin_is_refused(self):
        self.assertEqual(self.vote({"profile_url": self.first, "vote": "yes"}, Origin="https://attacker.example")[0], 403)
        self.assertEqual(self.saved(), {})

    def test_a_post_from_the_page_itself_is_accepted(self):
        self.assertEqual(self.vote({"profile_url": self.first, "vote": "yes"}, Origin=f"http://{self.own}")[0], 200)
        self.assertEqual(self.saved()[self.first]["vote"], "yes")

    def test_only_json_posts_to_the_vote_address_are_accepted(self):
        body = json.dumps({"profile_url": self.first, "vote": "yes"}).encode()
        self.assertEqual(self.send("POST", "/vote", body, Content_Type="text/plain", Content_Length=str(len(body)))[0], 403)
        self.assertEqual(self.send("POST", "/other", body, Content_Type="application/json", Content_Length=str(len(body)))[0], 403)
        self.assertEqual(self.saved(), {})

    def test_bad_requests_change_nothing(self):
        for payload in (b"not json", b"[1, 2]", {"profile_url": "https://www.linkedin.com/in/stranger", "vote": "yes"},
                        {"profile_url": self.first, "vote": "definitely"}, {"profile_url": self.first, "vote": "yes", "note": 5},
                        {"profile_url": ["list"], "vote": "yes"}):
            self.assertEqual(self.vote(payload)[0], 400, payload)
        self.assertEqual(self.saved(), {})

    def test_impossible_and_oversized_lengths_are_refused(self):
        for length in ("-1", "0", "10001", "many"):
            status = self.send("POST", "/vote", b"", Content_Type="application/json", Content_Length=length)[0]
            self.assertEqual(status, 400, length)

    def test_an_answer_can_be_changed_and_cleared(self):
        self.vote({"profile_url": self.first, "vote": "yes", "note": " Good fit. "})
        self.assertEqual(self.saved()[self.first]["note"], "Good fit.")
        self.vote({"profile_url": self.first, "vote": "no"})
        self.assertEqual(self.saved()[self.first]["vote"], "no")
        self.vote({"profile_url": self.first, "vote": None})
        self.assertEqual(self.saved(), {})

    def test_a_note_is_kept_short_and_the_file_private(self):
        record = review_page.record(self.project, self.rows, {"profile_url": self.first, "vote": "maybe", "note": "x" * 5000})
        self.assertEqual(len(record[self.first]["note"]), 1000)
        self.assertEqual(oct((self.project / "review.json").stat().st_mode & 0o777), "0o600")

    def test_answers_reach_the_csv(self):
        self.vote({"profile_url": self.first, "vote": "yes"})
        self.assertIn(",yes,", (self.project / "shortlist.csv").read_text(encoding="utf-8"))

    def test_answers_given_at_the_same_moment_all_survive(self):
        urls = [row["profile_url"] for row in self.rows]
        for _ in range(10):
            (self.project / "review.json").write_text("{}")
            start = threading.Barrier(len(urls))

            def answer(url):
                start.wait()
                review_page.record(self.project, self.rows, {"profile_url": url, "vote": "yes"})

            threads = [threading.Thread(target=answer, args=(url,)) for url in urls]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
            self.assertEqual(set(self.saved()), set(urls))


if __name__ == "__main__":
    unittest.main()
