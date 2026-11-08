"""Read a public company page for an editable first draft."""

import http.client
import ipaddress
import re
import socket
import ssl
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit, urlunsplit


def public_url(value):
    url = urlsplit(value if "://" in value else "https://" + value)
    if (url.scheme != "https" or not url.hostname or url.username is not None
            or url.port not in (None, 443) or not re.fullmatch(r"[a-z0-9.-]+\.[a-z0-9-]+", url.hostname)):
        raise ValueError("Enter a public HTTPS company URL.")
    return urlunsplit(("https", url.hostname, url.path or "/", "", ""))


class PublicConnection(http.client.HTTPSConnection):
    def connect(self):
        addresses = socket.getaddrinfo(self.host, 443, type=socket.SOCK_STREAM)
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
            conn.request("GET", parsed.path, headers={"Accept": "text/html", "User-Agent": "SourcingRig/1.0"})
            with conn.getresponse() as response:
                redirect = response.getheader("Location")
                if 300 <= response.status < 400 and redirect:
                    url = public_url(urljoin(url, redirect))
                    continue
                if response.status != 200 or "text/html" not in response.getheader("Content-Type", "").lower():
                    raise ValueError(f"Could not read the company page (HTTP {response.status}).")
                return url, response.read(512 * 1024).decode("utf-8", errors="replace")
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
        if tag in {"title", "h1"}:
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


def profile_channel(url):
    parts = urlsplit(url)
    host = parts.hostname.removeprefix("www.") if parts.hostname else ""
    if host == "linkedin.com" and re.fullmatch(r"/company/[\w-]+/?", parts.path):
        return "linkedin"
    if host in {"x.com", "twitter.com"} and re.fullmatch(r"/[\w]{1,15}/?", parts.path):
        if parts.path.strip("/").casefold() not in {"home", "share", "intent", "explore", "search", "settings"}:
            return "x"
    return None


def discover_seed(value, website=None, html=None):
    seed = public_url(value)
    site = public_url(website) if website else seed
    if profile_channel(site):
        raise ValueError("Add --website with the company’s public website for a LinkedIn or X starting URL.")
    final_url, html = fetch_page(site) if html is None else (site, html)
    page = Page(html)
    title = page.meta.get("og:title") or page.fields.get("title") or urlsplit(site).hostname
    description = page.meta.get("description") or page.meta.get("og:description") or page.fields.get("h1") or title
    links = {}
    comparisons = {}
    for href in page.links:
        try:
            url = public_url(urljoin(final_url, href))
        except ValueError:
            continue
        channel = profile_channel(url)
        if channel and channel not in links:
            links[channel] = url
        part = urlsplit(url)
        if part.hostname == urlsplit(final_url).hostname:
            comparison = re.fullmatch(r"/compare/[a-z0-9-]+-vs-([a-z0-9-]+)/?", part.path)
            if comparison and len(comparisons) < 8:
                comparisons[comparison[1].replace("-", " ")] = url
    return {"input": seed, "website": final_url, "title": title, "description": description,
            "linked_profiles": links, "comparisons": comparisons}
