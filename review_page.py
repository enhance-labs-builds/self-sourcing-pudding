"""Serve a local page for saying yes or no to each person on a shortlist.

The page runs on this computer only. Each answer is saved to review.json in the project folder,
keyed by LinkedIn profile, so the next run can learn from it.
"""

import contextlib
from datetime import datetime, timezone
import io
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading

import pudding
import treg as t

VOTES = {"yes", "no", "maybe"}
SAVING = threading.Lock()  # Answers given in quick succession must not overwrite each other.
CSP = ("default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; "
       "base-uri 'none'; form-action 'none'; frame-ancestors 'none'")
PAGE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Shortlist review</title>
<style>
:root { --bg:#fbfbfa; --card:#fff; --ink:#16171a; --soft:#62656d; --line:#e6e6e3; --chip:#f1f1ee;
        --yes:#1f8a4c; --no:#c2413a; --maybe:#a8720b; --focus:#3b6fe0; }
@media (prefers-color-scheme: dark) {
  :root { --bg:#111214; --card:#191b1e; --ink:#ececec; --soft:#9a9da5; --line:#2a2d32; --chip:#23262b;
          --yes:#4cc27e; --no:#ef7a72; --maybe:#e0a93b; --focus:#7da2ff; } }
* { box-sizing:border-box; }
body { margin:0; background:var(--bg); color:var(--ink); font:16px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif; }
main { max-width:760px; margin:0 auto; padding:20px 16px 96px; }
header { display:flex; flex-wrap:wrap; gap:8px 16px; align-items:baseline; justify-content:space-between; margin-bottom:12px; }
h1 { font-size:18px; margin:0; font-weight:600; }
.count { color:var(--soft); font-size:14px; }
.bar { display:flex; flex-wrap:wrap; gap:6px; margin:0 0 16px; }
.dot { width:26px; height:26px; border-radius:7px; border:1px solid var(--line); background:var(--card); color:var(--soft);
       font-size:12px; cursor:pointer; padding:0; }
.dot.low { border-style:dashed; }
.dot.yes { background:var(--yes); border-color:var(--yes); color:#fff; }
.dot.no { background:var(--no); border-color:var(--no); color:#fff; }
.dot.maybe { background:var(--maybe); border-color:var(--maybe); color:#fff; }
.dot.on { outline:2px solid var(--focus); outline-offset:2px; }
.card { background:var(--card); border:1px solid var(--line); border-radius:14px; padding:20px; }
.meta { color:var(--soft); font-size:13px; text-transform:uppercase; letter-spacing:.04em; margin-bottom:6px; }
.name { font-size:22px; font-weight:600; margin:0; overflow-wrap:anywhere; }
.name a { color:inherit; text-decoration:underline; text-decoration-color:var(--line); text-underline-offset:4px; }
.role { color:var(--soft); margin:2px 0 4px; overflow-wrap:anywhere; }
.employer { color:var(--soft); font-size:13px; margin:0 0 14px; overflow-wrap:anywhere; }
.role:not(:has(+ .employer)) { margin-bottom:14px; }
blockquote { margin:0 0 12px; padding:2px 0 2px 14px; border-left:3px solid var(--line); font-size:17px; overflow-wrap:anywhere; }
.why { margin:0 0 12px; }
.links { font-size:14px; color:var(--soft); margin:0 0 12px; }
.links a { color:var(--focus); margin-right:12px; }
.chips { display:flex; flex-wrap:wrap; gap:6px; margin:0 0 4px; }
.chip { background:var(--chip); border-radius:999px; padding:2px 10px; font-size:13px; color:var(--soft); }
textarea { width:100%; margin-top:14px; min-height:44px; padding:10px; border:1px solid var(--line); border-radius:10px;
           background:transparent; color:inherit; font:inherit; resize:vertical; }
.actions { position:fixed; left:0; right:0; bottom:0; background:var(--bg); border-top:1px solid var(--line); padding:12px 16px; }
.actions div { max-width:760px; margin:0 auto; display:grid; grid-template-columns:1fr 1fr 1fr auto auto; gap:8px; }
button.act { height:46px; border-radius:11px; border:1px solid var(--line); background:var(--card); color:var(--ink);
             font:600 15px system-ui,sans-serif; cursor:pointer; }
button.act kbd { font:12px ui-monospace,monospace; color:var(--soft); margin-left:6px; }
button.act.picked.yes { background:var(--yes); border-color:var(--yes); color:#fff; }
button.act.picked.no { background:var(--no); border-color:var(--no); color:#fff; }
button.act.picked.maybe { background:var(--maybe); border-color:var(--maybe); color:#fff; }
button.act.picked kbd { color:#fff; }
button.nav { width:46px; }
button:focus-visible, textarea:focus-visible, a:focus-visible { outline:2px solid var(--focus); outline-offset:2px; }
.done { text-align:center; padding:28px 0 8px; color:var(--soft); }
@media (max-width:480px) { button.act kbd { display:none; } .name { font-size:20px; } }
</style>
</head>
<body>
<main>
  <header><h1 id="title">Shortlist review</h1><span class="count" id="count"></span></header>
  <div class="bar" id="bar" aria-label="People"></div>
  <div class="card" id="card" aria-live="polite"></div>
  <p class="done" id="done" hidden></p>
</main>
<div class="actions"><div>
  <button class="act" data-vote="yes">Yes<kbd>Y</kbd></button>
  <button class="act" data-vote="no">No<kbd>N</kbd></button>
  <button class="act" data-vote="maybe">Maybe<kbd>M</kbd></button>
  <button class="act nav" id="prev" aria-label="Previous">←</button>
  <button class="act nav" id="next" aria-label="Next">→</button>
</div></div>
<script>
let rows = [], votes = {}, at = 0;
const $ = (id) => document.getElementById(id);
const el = (tag, cls, text) => { const n = document.createElement(tag); if (cls) n.className = cls; if (text != null) n.textContent = text; return n; };
const link = (text, url) => { const a = el("a", "", text); if (/^https:\/\//.test(url)) { a.href = url; a.target = "_blank"; a.rel = "noopener noreferrer"; } return a; };
function draw() {
  const row = rows[at], vote = (votes[row.profile_url] || {}).vote;
  const yes = rows.filter(r => (votes[r.profile_url] || {}).vote === "yes").length;
  const answered = rows.filter(r => (votes[r.profile_url] || {}).vote).length;
  $("count").textContent = `${at + 1} of ${rows.length} · ${answered} answered · ${yes} yes`;
  const bar = $("bar"); bar.replaceChildren();
  rows.forEach((r, i) => {
    const v = (votes[r.profile_url] || {}).vote || "";
    const dot = el("button", `dot ${v} ${r.fit === "low" ? "low" : ""} ${i === at ? "on" : ""}`, String(i + 1));
    dot.title = `${r.name} · ${r.fit}`; dot.onclick = () => { at = i; draw(); }; bar.append(dot);
  });
  const card = $("card"); card.replaceChildren();
  card.append(el("div", "meta", `${r_fit(row.fit)} · ${row.kind} · ${row.channel}${row.published_on ? " · " + row.published_on : ""}`));
  const name = el("h2", "name"); name.append(link(row.name, row.profile_url)); card.append(name);
  card.append(el("p", "role", row.company ? `${row.role}, ${row.company}` : row.role));
  const facts = [row.company_size ? `${Number(row.company_size).toLocaleString()} ${row.company_size == 1 ? "person" : "people"} on LinkedIn` : "", row.company_industry, row.company_about].filter(Boolean);
  if (facts.length) card.append(el("p", "employer", facts.join(" · ")));
  if (row.account) card.append(el("p", "employer", `${row.account} account${row.account_why ? ": " + row.account_why : ""}`));
  card.append(el("blockquote", "", row.quote));
  card.append(el("p", "why", row.why));
  const links = el("p", "links"); links.append(link("Source", row.source_url));
  (row.other_sources || []).forEach((u, i) => links.append(link(`Also ${i + 1}`, u)));
  links.append(document.createTextNode(row.identity_basis)); card.append(links);
  const chips = el("div", "chips"); (row.labels || []).forEach(l => chips.append(el("span", "chip", l))); card.append(chips);
  const note = el("textarea"); note.placeholder = "Why? (optional)"; note.value = (votes[row.profile_url] || {}).note || "";
  note.setAttribute("aria-label", "Note"); note.onchange = () => save(vote || null, note.value); card.append(note);
  document.querySelectorAll("button[data-vote]").forEach(b => b.className = `act ${b.dataset.vote} ${b.dataset.vote === vote ? "picked" : ""}`);
  const done = $("done"); done.hidden = answered < rows.length;
  done.textContent = `All ${rows.length} answered: ${yes} yes. Your answers are saved in review.json.`;
}
const r_fit = (fit) => ({strong: "Strong", look: "Worth a look", low: "Low fit"}[fit] || fit);
async function save(vote, note, advance) {
  const row = rows[at];
  const res = await fetch("/vote", {method: "POST", headers: {"Content-Type": "application/json"},
                                    body: JSON.stringify({profile_url: row.profile_url, vote, note: note ?? (votes[row.profile_url] || {}).note ?? ""})});
  if (!res.ok) { alert("Could not save. Is the review still running in the terminal?"); return; }
  votes = await res.json();
  if (advance) { const next = rows.findIndex((r, i) => i > at && !(votes[r.profile_url] || {}).vote); if (next >= 0) at = next; else if (at < rows.length - 1) at += 1; }
  draw();
}
function choose(vote) { const current = (votes[rows[at].profile_url] || {}).vote; const note = document.querySelector("textarea").value; save(current === vote ? null : vote, note, current !== vote); }
document.querySelectorAll("button[data-vote]").forEach(b => b.onclick = () => choose(b.dataset.vote));
$("prev").onclick = () => { at = Math.max(0, at - 1); draw(); };
$("next").onclick = () => { at = Math.min(rows.length - 1, at + 1); draw(); };
document.addEventListener("keydown", (e) => {
  if (e.target.tagName === "TEXTAREA" || e.metaKey || e.ctrlKey || e.altKey) return;
  const key = e.key.toLowerCase();
  if (key === "y") choose("yes"); else if (key === "n") choose("no"); else if (key === "m") choose("maybe");
  else if (key === "arrowleft" || key === "k") $("prev").click(); else if (key === "arrowright" || key === "j") $("next").click();
});
fetch("/data").then(r => r.json()).then(data => {
  rows = data.rows; votes = data.votes; $("title").textContent = data.title; document.title = data.title;
  if (!rows.length) { $("card").textContent = "Nobody on this shortlist yet."; return; }
  const first = rows.findIndex(r => !(votes[r.profile_url] || {}).vote); at = first >= 0 ? first : 0; draw();
});
</script>
</body>
</html>
"""


def load_votes(project):
    return pudding.read(project / "review.json", {})


def record(project, rows, payload):
    """Save one answer. Only people on the current shortlist can be answered."""
    profile, vote, note = payload.get("profile_url"), payload.get("vote"), payload.get("note", "")
    if profile not in {row["profile_url"] for row in rows} or vote not in VOTES | {None} or not isinstance(note, str):
        raise ValueError("Unknown person or answer.")
    with SAVING:
        votes = load_votes(project)
        if vote is None and not note.strip():
            votes.pop(profile, None)
        else:
            votes[profile] = {"vote": vote, "note": note.strip()[:1000], "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        t.atomic_json(project / "review.json", votes)
        try:  # The CSV and the markdown shortlist carry the answer too, so they are rewritten with it.
            with contextlib.redirect_stdout(io.StringIO()):
                pudding.shortlist(project)
        except (ValueError, OSError):
            pass
        return votes


def handler(project, rows, title):
    class Review(BaseHTTPRequestHandler):
        def send(self, status, body, kind):
            data = body.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", CSP)
            self.end_headers()
            self.wfile.write(data)

        def local(self):
            # Another site must not be able to reach this page through a hostname it controls.
            return self.headers.get("Host", "").rsplit(":", 1)[0] in {"127.0.0.1", "localhost"}

        def do_GET(self):
            if not self.local():
                return self.send(403, "Forbidden", "text/plain")
            if self.path == "/":
                return self.send(200, PAGE, "text/html; charset=utf-8")
            if self.path == "/data":
                return self.send(200, json.dumps({"title": title, "rows": rows, "votes": load_votes(project)}), "application/json")
            self.send(404, "Not found", "text/plain")

        def do_POST(self):
            origin = self.headers.get("Origin")
            if (not self.local() or self.path != "/vote" or self.headers.get("Content-Type") != "application/json"
                    or origin not in (None, f"http://{self.headers.get('Host')}")):
                return self.send(403, "Forbidden", "text/plain")
            try:
                length = int(self.headers.get("Content-Length", 0))
                if not 0 < length <= 10_000:
                    raise ValueError("Bad length.")
                payload = json.loads(self.rfile.read(length))
                votes = record(project, rows, payload if isinstance(payload, dict) else {})
            except (ValueError, TypeError):
                return self.send(400, "Bad request", "text/plain")
            self.send(200, json.dumps(votes), "application/json")

        def log_message(self, *_):
            pass

    return Review


def server(project, port):
    rows, *_ = pudding.shortlist_rows(project)
    title = "Review: " + pudding.read(project / "project.json")["url"].split("//")[-1].strip("/")
    return ThreadingHTTPServer(("127.0.0.1", port), handler(project, rows, title)), len(rows)


def serve(project, port):
    httpd, count = server(project, port)
    print(f"Review {count} people at http://127.0.0.1:{httpd.server_address[1]} — answers save to {project / 'review.json'}. "
          "Press Ctrl+C to stop.", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
        pudding.lock_down(project)
