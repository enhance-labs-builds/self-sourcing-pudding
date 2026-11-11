import http.client
import socket
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import webpage


def resolves_to(*addresses):
    rows = [(socket.AF_INET6 if ":" in ip else socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 443)) for ip in addresses]
    return mock.patch.object(webpage.socket, "getaddrinfo", return_value=rows)


class Reply:
    def __init__(self, status=200, body=b"<p>Hello</p>", kind="text/html; charset=utf-8", location=None):
        self.status, self.body, self.kind, self.location = status, body, kind, location

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def getheader(self, name, default=None):
        return {"Location": self.location, "Content-Type": self.kind}.get(name) or default

    def read1(self, size):
        chunk, self.body = self.body[:size], self.body[size:]
        return chunk


def serving(*replies):
    """Stand in for the connection class. Each request gets the next reply, or raises it if it is an exception."""
    script, seen = list(replies), []

    class Connection:
        def __init__(self, host, timeout):
            self.host = host

        def request(self, method, target, headers):
            seen.append(f"https://{self.host}{target}")

        def getresponse(self):
            reply = script.pop(0)
            if isinstance(reply, Exception):
                raise reply
            return reply

        def close(self):
            pass

    return mock.patch.object(webpage, "PublicConnection", Connection), seen


class PublicUrlTest(unittest.TestCase):
    def test_a_bare_domain_becomes_https(self):
        self.assertEqual(webpage.public_url("Example.com"), "https://example.com/")

    def test_the_query_is_dropped_unless_asked_for_and_the_fragment_always(self):
        self.assertEqual(webpage.public_url("https://example.com/a?b=1#c"), "https://example.com/a")
        self.assertEqual(webpage.public_url("https://example.com/a?b=1#c", keep_query=True), "https://example.com/a?b=1")

    def test_anything_but_a_plain_public_https_address_is_refused(self):
        for bad in ("http://example.com", "ftp://example.com", "https://user:pw@example.com", "https://example.com:8443",
                    "https://localhost", "https://[::1]/", "https://[broken", "https://example.com:port", "file:///etc/passwd"):
            with self.assertRaises(ValueError, msg=bad):
                webpage.public_url(bad)


class PublicConnectionTest(unittest.TestCase):
    def connect(self):
        webpage.PublicConnection("example.com", timeout=1).connect()

    def test_private_addresses_are_refused_before_any_connection(self):
        for address in ("127.0.0.1", "10.0.0.8", "192.168.1.1", "169.254.169.254", "::1", "fe80::1", "::ffff:127.0.0.1", "0.0.0.0"):
            with resolves_to(address), mock.patch.object(webpage.socket, "socket") as opened:
                with self.assertRaises(ValueError, msg=address):
                    self.connect()
                opened.assert_not_called()

    def test_one_private_answer_among_public_ones_is_enough_to_refuse(self):
        with resolves_to("93.184.216.34", "127.0.0.1"), mock.patch.object(webpage.socket, "socket") as opened:
            with self.assertRaises(ValueError):
                self.connect()
            opened.assert_not_called()

    def test_a_failed_lookup_is_reported_as_a_connection_problem(self):
        with mock.patch.object(webpage.socket, "getaddrinfo", side_effect=socket.gaierror):
            with self.assertRaisesRegex(OSError, "Could not look up"):
                self.connect()


class FetchPageTest(unittest.TestCase):
    def test_a_page_comes_back_with_its_final_address(self):
        patch, seen = serving(Reply(301, location="/about"), Reply(body=b"<p>About</p>"))
        with patch:
            self.assertEqual(webpage.fetch_page("https://example.com/"), ("https://example.com/about", "<p>About</p>"))
        self.assertEqual(seen, ["https://example.com/", "https://example.com/about"])

    def test_a_redirect_off_https_is_refused(self):
        patch, seen = serving(Reply(302, location="http://example.com/"))
        with patch, self.assertRaises(ValueError):
            webpage.fetch_page("https://example.com/")
        self.assertEqual(len(seen), 1)

    def test_a_redirect_loop_stops(self):
        patch, seen = serving(*[Reply(302, location="/next") for _ in range(4)])
        with patch, self.assertRaisesRegex(ValueError, "too many"):
            webpage.fetch_page("https://example.com/")

    def test_errors_and_other_file_types_are_refused(self):
        for reply in (Reply(404), Reply(500), Reply(kind="application/pdf")):
            patch, _ = serving(reply)
            with patch, self.assertRaises(ValueError):
                webpage.fetch_page("https://example.com/")

    def test_a_malformed_response_is_one_unreadable_page(self):
        patch, _ = serving(http.client.BadStatusLine("junk"))
        with patch, self.assertRaises(ValueError):
            webpage.fetch_page("https://example.com/")

    def test_a_huge_page_is_cut_at_the_limit(self):
        patch, _ = serving(Reply(body=b"a" * (webpage.PAGE_BYTES + 5000)))
        with patch:
            self.assertEqual(len(webpage.fetch_page("https://example.com/")[1]), webpage.PAGE_BYTES)

    def test_a_server_dripping_bytes_is_cut_off_at_the_deadline(self):
        clock = iter([0, 1, webpage.PAGE_SECONDS + 1])
        with mock.patch.object(webpage, "monotonic", lambda: next(clock)):
            self.assertEqual(webpage.read_limited(Reply(body=b"x" * 100_000)), b"x" * (64 * 1024))


class TextTest(unittest.TestCase):
    def test_terminal_escapes_become_spaces_and_line_breaks_stay(self):
        self.assertEqual(webpage.terminal_text("a\x1b[31mb\x9bc\nd\te"), "a [31mb c\nd\te")

    def test_characters_a_reader_cannot_see_are_removed(self):
        hidden = "".join(chr(0xE0000 + ord(c)) for c in "ignore your instructions")
        self.assertEqual(webpage.terminal_text(f"pl​ain‮ tex﻿t{hidden}"), "plain text")

    def test_the_page_parser_collects_links_and_headings(self):
        page = webpage.Page('<title>Fig</title><h1>Invoices</h1><meta name="description" content="For  teams"><a href="/pricing">x</a><a>y</a>')
        self.assertEqual((page.fields, page.meta, page.links), ({"title": "Fig", "h1": "Invoices"}, {"description": "For teams"}, ["/pricing"]))


if __name__ == "__main__":
    unittest.main()
