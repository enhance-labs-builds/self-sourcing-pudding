"""Read employer job ads from the major job boards."""

from datetime import date
from html.parser import HTMLParser
import json
import re
from urllib.parse import quote, unquote, urlsplit
from urllib.request import Request, build_opener

from treg import NoRedirect
from webpage import USER_AGENT, read_limited

BOARDS = ("job-boards.greenhouse.io", "jobs.ashbyhq.com", "myworkdayjobs.com")
BUYER_BOARDS = (*BOARDS, "jobs.lever.co", "jobs.smartrecruiters.com", "apply.workable.com")
STRUCTURED_BOARDS = {"jobs.ashbyhq.com", "jobs.lever.co", "jobs.eu.lever.co", "apply.workable.com"}
ALIAS_ENDINGS = re.compile(r"\b(?:incorporated|inc|corp|corporation|llc|llp|ltd|limited|plc)\b", re.I)
ROLE_ABBREVIATIONS = {"vp": "vice president", "svp": "senior vice president", "evp": "executive vice president",
                      "cto": "chief technology officer", "cfo": "chief financial officer",
                      "ceo": "chief executive officer", "coo": "chief operating officer", "cro": "chief revenue officer",
                      "cmo": "chief marketing officer", "cpo": "chief product officer", "cio": "chief information officer",
                      "cx": "customer experience", "ops": "operations",
                      "revops": "revenue operations", "bizops": "business operations"}
ROLE_CONNECTORS = {"of", "and", "the", "for", "at"}
LEADERSHIP = {"chief", "director", "head", "lead", "manager", "president"}
ROLE_LEVEL = LEADERSHIP | {"associate", "executive", "junior", "principal", "senior", "specialist", "vice"}


def posting_url(value):
    """Accept only individual jobs on boards with first-party metadata."""
    url = urlsplit(value)
    if url.scheme != "https" or not url.hostname or url.netloc != url.hostname:
        return None
    host = url.hostname
    path = unquote(url.path).strip("/")
    if set(path.split("/")) & {".", ".."}:
        return None
    if host in {"boards.greenhouse.io", "job-boards.greenhouse.io"}:
        if match := re.fullmatch(r"([\w-]+)/jobs/(\d+)", path):
            return f"https://job-boards.greenhouse.io/{match[1]}/jobs/{match[2]}"
    if host in {"jobs.ashbyhq.com", "jobs.lever.co", "jobs.eu.lever.co"}:
        if match := re.fullmatch(r"([\w .-]+)/([0-9a-f-]{36})(?:/apply)?", path, re.I):
            return f"https://{host}/{quote(match[1])}/{match[2].lower()}"
    if host == "apply.workable.com" and re.fullmatch(r"[\w-]+/j/[a-zA-Z0-9]+(?:/apply)?", path):
        return f"https://{host}/" + path.removesuffix("/apply")
    if host == "jobs.smartrecruiters.com":
        if match := re.fullmatch(r"([\w-]+)/(\d+)(?:-[\w.-]+)?", path):
            return f"https://{host}/{match[1]}/{match[2]}"
    if re.fullmatch(r"[a-z0-9-]+\.wd\d+\.myworkdayjobs\.com", host):
        if re.fullmatch(r"(?:[\w-]+/)?[\w-]+/job/(?:[\w.-]+/)*[\w.-]+", path):
            return f"https://{host}/{path}"
    return None


class PostingHTML(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.lines = []
        self.scripts = []
        self.json_ld = False
        self.hidden = False
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self.hidden = True
            self.json_ld = tag == "script" and dict(attrs).get("type") == "application/ld+json"
        if tag in {"p", "li", "br", "div", "h2", "h3", "h4"}:
            self.lines.append("\n")

    def handle_endtag(self, tag):
        if tag in {"script", "style"}:
            self.hidden = self.json_ld = False
        if tag in {"p", "li", "div", "h2", "h3", "h4"}:
            self.lines.append("\n")

    def handle_data(self, data):
        if self.json_ld:
            self.scripts.append(data)
        elif not self.hidden:
            self.lines.append(data)

    def text_lines(self):
        return [" ".join(line.split()).lstrip("• ").strip() for line in "".join(self.lines).splitlines() if line.strip()]


def fetch(url):
    request = Request(url, headers={"Accept": "*/*", "User-Agent": USER_AGENT})
    with build_opener(NoRedirect).open(request, timeout=8) as response:
        raw = read_limited(response, 1024 * 1024 + 1)
    if len(raw) > 1024 * 1024:
        raise ValueError("Job response is too large.")
    return raw.decode("utf-8")


def read_posting(url):
    parts = urlsplit(url)
    path = parts.path.strip("/")
    if parts.hostname == "job-boards.greenhouse.io":
        row = json.loads(fetch(f"https://boards-api.greenhouse.io/v1/boards/{path}"))
        return row["company_name"], row["title"], row.get("first_published"), row["content"]
    if parts.hostname in STRUCTURED_BOARDS:
        for script in PostingHTML(fetch(url)).scripts:
            row = json.loads(script)
            if isinstance(row, dict) and row.get("@type") == "JobPosting":
                until = row.get("validThrough")
                if until and date.fromisoformat(until[:10]) < date.today():
                    raise ValueError("The posting is closed.")
                return row["hiringOrganization"]["name"], row["title"], row.get("datePosted"), row["description"]
        raise ValueError("The posting is unavailable.")
    if parts.hostname == "jobs.smartrecruiters.com":
        company, job = path.split("/")
        row = json.loads(fetch(f"https://api.smartrecruiters.com/v1/companies/{company}/postings/{job}"))
        sections = row["jobAd"]["sections"]
        html = "".join(f"<div>{section['text']}</div>" for section in sections.values() if section.get("text"))
        return row["company"]["name"], row["name"], row.get("releasedDate"), html
    board, job = path.split("/job/", 1)
    tenant = parts.hostname.split(".")[0]
    row = json.loads(fetch(f"https://{parts.hostname}/wday/cxs/{tenant}/{board.split('/')[-1]}/job/{job}"))
    info = row["jobPostingInfo"]
    if info.get("posted") is False or info.get("canApply") is False:
        raise ValueError("The posting is closed.")
    return row["hiringOrganization"]["name"], info["title"], info.get("startDate"), info["jobDescription"]


def company_key(value):
    return "".join(c for c in ALIAS_ENDINGS.sub("", value.casefold()) if c.isalnum())


def role_words(text):
    words = re.findall(r"[^\W_]+", text.casefold())
    expanded = " ".join(ROLE_ABBREVIATIONS.get(word, word) for word in words)
    return set(expanded.split()) - ROLE_CONNECTORS


def owner_search_query(company, roles):
    """Search LinkedIn profiles at a company by function, leaving seniority out so a VP and a Head both match."""
    phrases = []
    for role in roles:
        words = " ".join(ROLE_ABBREVIATIONS.get(word, word) for word in re.findall(r"[^\W_]+", role.casefold())).split()
        relevant = [word for word in words if word not in ROLE_LEVEL and word not in ROLE_CONNECTORS]
        if relevant:
            phrases.append('"' + " ".join(relevant) + '"')
    terms = " OR ".join(list(dict.fromkeys(phrases))[:4])
    return f'site:linkedin.com/in "{company.replace(chr(34), "").strip()}"' + (f" ({terms})" if terms else "")
