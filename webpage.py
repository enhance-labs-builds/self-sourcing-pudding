"""Read a public web page."""

import http.client
import ipaddress
import re
import socket
import ssl
from html.parser import HTMLParser
from time import monotonic
from urllib.parse import urljoin, urlsplit, urlunsplit


USER_AGENT = "SelfSourcingPudding/0.3 (+https://github.com/enhance-labs-builds/self-sourcing-pudding)"
PAGE_BYTES = 512 * 1024
PAGE_SECONDS = 20
# Characters a reader can't see but a model reads: zero-width and direction marks, and the Unicode tag block.
INVISIBLE = re.compile("[­​-‏‪-‮⁠-⁤⁦-⁯﻿\U000e0000-\U000e007f]")


def terminal_text(value):
    """Text from the web, safe to print or hand to an agent: no terminal escapes, nothing hidden."""
    return re.sub(r"[\x00-\x08\x0b-\x1f\x7f-\x9f]", " ", INVISIBLE.sub("", value))


def read_limited(response, limit=PAGE_BYTES):
    """Stop at the size limit or the deadline, so a server dripping bytes can't hold a run open."""
    deadline, body = monotonic() + PAGE_SECONDS, bytearray()
    while len(body) < limit and monotonic() < deadline:
        chunk = response.read1(min(64 * 1024, limit - len(body)))
        if not chunk:
            break
        body += chunk
    return bytes(body)


def public_url(value, *, keep_query=False):
    url = urlsplit(value if "://" in value else "https://" + value)
    if (url.scheme != "https" or not url.hostname or url.username is not None
            or url.port not in (None, 443) or not re.fullmatch(r"[a-z0-9.-]+\.[a-z0-9-]+", url.hostname)):
        raise ValueError("Enter a public HTTPS company URL.")
    return urlunsplit(("https", url.hostname, url.path or "/", url.query if keep_query else "", ""))


class PublicConnection(http.client.HTTPSConnection):
    def connect(self):
        try:
            addresses = socket.getaddrinfo(self.host, 443, type=socket.SOCK_STREAM)
        except socket.gaierror as error:
            raise OSError(f"Could not look up {self.host}.") from error
        if not addresses or any(not ipaddress.ip_address(row[4][0]).is_global for row in addresses):
            raise ValueError("The company URL must resolve to a public address.")
        with_error = None
        for family, kind, proto, _, address in addresses:
            conn = socket.socket(family, kind, proto)
            try:
                conn.settimeout(self.timeout)
                conn.connect(address)
                self.sock = ssl.create_default_context().wrap_socket(conn, server_hostname=self.host)
                return
            except OSError as error:
                conn.close()
                with_error = error
        raise OSError(f"Could not connect to {self.host}.") from with_error


def fetch_page(url):
    for _ in range(4):
        parsed = urlsplit(url)
        conn = PublicConnection(parsed.hostname, timeout=5)
        try:
            target = urlunsplit(("", "", parsed.path, parsed.query, ""))
            conn.request("GET", target, headers={"Accept": "text/html", "User-Agent": USER_AGENT})
            with conn.getresponse() as response:
                redirect = response.getheader("Location")
                if 300 <= response.status < 400 and redirect:
                    url = public_url(urljoin(url, redirect), keep_query=True)
                    continue
                if response.status != 200 or "text/html" not in response.getheader("Content-Type", "").lower():
                    raise ValueError(f"Could not read the company page (HTTP {response.status}).")
                return url, read_limited(response).decode("utf-8", errors="replace")
        except http.client.HTTPException as error:  # A malformed link or reply is one unreadable page, not a failed run.
            raise ValueError(f"Could not read the page ({type(error).__name__}).") from error
        finally:
            conn.close()
    raise ValueError("The company page redirected too many times.")


class Page(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.field = None
        self.meta = {}
        self.fields = {}
        self.links = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in {"title", "h1", "h2", "h3"}:
            self.field = tag
        if tag == "meta" and attrs.get("content"):
            key = attrs.get("property") or attrs.get("name")
            self.meta[key] = " ".join(attrs["content"].split())[:500]
        if tag == "a" and attrs.get("href"):
            self.links.append(attrs["href"])

    def handle_endtag(self, tag):
        if tag == self.field:
            self.field = None

    def handle_data(self, data):
        if self.field and data.strip():
            self.fields[self.field] = (self.fields.get(self.field, "") + " " + data.strip()).strip()[:300]
