# Sourcing Rig

Describe a problem, find people who talk about the work, and produce a shortlist that shows the evidence behind each decision.

This first pass runs offline with Python 3.11 or newer. It reads local records and exports a research shortlist. The example uses fictional people, companies, posts, and profile links.

## Try it in one command

```sh
python3 rig.py demo
```

Open `runs/demo/shortlist.csv`. The demo finds eight candidates and shortlists two. One person appears on LinkedIn and X and gets one shortlist row with both sightings. A competitor announcement and a short comment lead to review. The people who qualify provide their own evidence of doing the work.

The demo replays supplied review decisions. See `runs/demo/review.json` for why the other candidates were passed over or held. Use `--out runs/demo-2` for another run.

## Edit the brief and review a run

```sh
python3 rig.py init --example
python3 rig.py plan
python3 rig.py source --out runs/first
python3 rig.py review --run runs/first
```

Between `init` and `plan`, open `brief.toml` and edit it. For a quick experiment, keep only `"BranchDock"` under `alternatives` and replace `signals` with `["pull request"]`. The preview deploy thread drops out of the queue and the competitor discussion stays in.

Run `init` without `--example` for guided setup. The questions cover your product, target roles, problem language, competitors and workarounds, and what a good fit and a near miss look like. `plan` shows the terms and evidence rules before discovery. To reuse a previous review on the same queue, pass its `review.json` to `review --decisions`.

Discovery looks for your phrases in local LinkedIn and X records. It also opens comments, replies, and quotes attached to matching posts. It groups sightings by the corpus's verified person ID and puts current candidates with a matching role higher in the queue. A role, keyword, or competitor match helps find people to review. You make the fit decision from the original text and current role.

Choose firsthand problem, explicit work, hold, or pass. To qualify someone, pick a current source attributed to that person, keep an exact excerpt, and record why it fits your brief. An unresolved identity, an old role check, or a lack of current evidence holds the candidate. Contact history is marked `unchecked`.

## Bring your own offline records

Use `source --corpus path/to/corpus.json --out runs/custom` with your own brief. The [example corpus](examples/preview-environments/corpus.json) defines the format. Set `as_of` to the snapshot date so a repeat run uses the same freshness checks, or override it with `--as-of YYYY-MM-DD`. Keep dates in `YYYY-MM-DD` format.

- A person needs a stable ID, name, role, employer, canonical HTTPS profile URL, and the date the role was last checked.
- Each observation has a stable ID, channel, kind, author, URL, publication date, and original text. Use the same `person_id` across both channels only after checking the author-to-profile link. Leave it absent when the identity is uncertain.
- Set `parent_id` on a comment, reply, or quote to bring it into review when the original post matches. The original post must be in the corpus. A parent's evidence stays with its own author.

The run folder contains the queue and a snapshot of the brief in `queue.json`, the review in `review.json`, and the shortlist in CSV and JSON. Create a fresh run folder after editing the brief so its review stays tied to the evidence and rules it used.

Run `python3 -m unittest discover -s tests` to check the demo, the editable brief and manual review, and rejection of unsupported qualifications.
