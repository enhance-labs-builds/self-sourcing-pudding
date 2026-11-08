# Self-Sourcing Pudding guide

[Quick start](../README.md)

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

## Start from a company URL

The pilot commands keep an editable brief and feedback in one local project.

```sh
python3 rig.py pilot start boat.dev --project runs/boat
python3 rig.py pilot approve --project runs/boat
python3 rig.py pilot run --project runs/boat --run preview --budget-usd 0.10
python3 rig.py pilot review --project runs/boat --run preview
python3 rig.py pilot status --project runs/boat
```

`start` reads the site's public copy, social links and comparison links. It proposes roles and search phrases when the copy supports a starting hypothesis. For other sites, fill in the buyer and workflow in `brief.toml`. Use `--starter` to import a researched brief, or `--website` when your starting LinkedIn or X URL needs a public company site. Review or edit the draft before approval. Any later edit to the brief's settings needs a new approval.

The preview shows up to 20 people with a current LinkedIn role and dated source. `holds.json` contains candidates with an identity or freshness gap. To include an X author in the preview, supply a reviewed identity match with `--identities` or add it to an offline corpus. An identities file is a JSON array with `source_url`, `author`, `profile_url`, `name`, `role`, `company`, `role_checked_on`, `binding_source`, and `role_source` on each row. Use the exact post URL and author from the corpus. `binding_source` and `role_source` should point to the public evidence for the identity match and the current role. You can replay a paid run locally with `--corpus path/to/corpus.json`.

Review saves yay/nay with evidence or a reason. A yay can keep someone for follow-up, or add them to the shortlist if you select firsthand evidence. The next run skips evidence you've already voted on and can surface a person again when they publish new evidence. A wrong role or wrong account vote also suppresses further results for that same role or account. `preview.json` records spend and whether each channel completed. `pilot run --batch` uses `limits.batch_target` from the approved brief, starting at 100. Tune query count with `--searches`, role lookups with `--profiles`, and search depth with `--pages` and `--results-per-search`. The approved target and spend cap bound the run. The pilot is run on demand.

Live pilot runs also look up work emails for review candidates whose current roles match the brief. The rig checks the website listed on the person's current LinkedIn company page, then independently verifies any address that matches that domain. Review shows verified emails as soon as the run finishes and carries them into the shortlist. The same spend cap covers discovery, role checks, and email. Use `--no-email` to spend the cap on discovery and role checks alone. For a reviewed X identity, include the current employer's LinkedIn `company_url` in `--identities` to make it eligible for email lookup. Keep run folders private.

### Draft a brief with a browsing-enabled agent

In a browsing-enabled coding agent, open this repository and ask:

> Use this public company URL as the seed for a sourcing run: `<company URL>`. Follow the link to its official site, read the product copy and public posts, and draft an editable brief for prospective users. Show the inferred customer profile, public search signals, and qualification criteria. Search LinkedIn and X with the rig under a US$0.10 cap. Shortlist people only when you can verify their current role and first-person evidence of the work.

Start with the company's public LinkedIn page, X (Twitter) profile, or website. Use the official site to check that the profiles belong to the right company. Search the company name for customer examples, then search the problem language and alternatives for people outside the company's audience. Treat customer segments as hypotheses and use candidate evidence to decide who qualifies. The agent drafts the brief and reviews candidates. The CLI runs discovery and records evidence, spend, and decisions. Live discovery uses the Treg setup below.

The [Boat brief](../examples/boat-sandboxes/brief.toml) shows how the public company profile and product site translate into an editable sourcing brief. Edit its target roles and qualification criteria to steer who makes the shortlist. Edit the ordered `[[searches]]` entries to steer what the rig looks for: `problem`, `brand`, `alternative`, or `account`. For example, Boat lists Daytona as an alternative and searches the more specific phrase `Daytona sandbox`.

Run `live --dry-run` with your brief, output path, and budget to see the exact queries before spending. The rig runs the first four explicit queries on both channels by default, keeps posts containing the relevant phrase, and records what found each post. `--searches` lets you run fewer. Briefs without an explicit search plan still use the keyword defaults.

## Find people working with alternatives

Pair an alternative with the workflow people actually talk about. The rig asks for the name and at least one workflow phrase on both channels, then checks both against the same post. LinkedIn requests recent posts first for these searches. Use `[[customer_stories]]` to find case studies in the competitor's own customer story directory. Both routes use the same run budget.

```toml
[[searches]]
lane = "alternative"
phrase = "Abridge"
workflow = ["clinical documentation", "ambient scribe", "AI scribe"]

[[customer_stories]]
competitor = "Abridge"
site = "https://www.abridge.com/case-study"
workflow = "clinical documentation"
```

Customer stories land in `customer-story-queue.json` for review. Open the original and look for the named customer who describes doing the work. Check their current role independently and record the team, the quote, and when the work happened if known. A dated post describing a live evaluation or unresolved problem is a timing signal. A vendor case study can show installed use and surface a workflow owner. Keep the person's current buying intent unknown unless they give you separate evidence of it.

Use a verified story to improve the next social query. With `lane = "account"`, set `phrase` to the customer name and `workflow` to the phrases from the story. Set `seed_url` to keep the original story linked to posts found by that query. You can also search those phrases on their own with `lane = "problem"` to find teams describing the same pain without naming a tool. For an ambiguous name, add narrow `exclude_phrases` to that query, such as `["Tata Sierra"]`; the rig filters those phrases from returned posts. Evaluate the original author and workflow each time, even when someone quotes a strong customer story. Use `--profiles 0` if you want to review the evidence before paying to check anyone's current role.

The [Heidi](../examples/blackbird/heidi.toml), [Dovetail](../examples/blackbird/dovetail.toml), and [Lorikeet](../examples/blackbird/lorikeet.toml) briefs show the same approach across three markets.

## Run a live search

Sign in to the [Treg dashboard](https://treg.to/app?ref=docs). Use a team with prepaid balance and no connected provider keys or custom tools. Copy the team slug and create an API key for that team. Pudding uses that key as its token. Keep it out of the brief and repository.

Set these in the terminal where you’ll run Pudding. Paste your token at the prompt and press Enter.

```sh
export TREG_ORG='your-team-slug'
printf 'Treg API token: '
read -rs TREG_TOKEN
printf '\n'
export TREG_TOKEN
```

From the repository folder, start a live search with your walkthrough project. Replace `YOUR_LIMIT` with the most you want this run to use in US dollars. Searches, role checks, and work email lookup share that budget.

```sh
.pudding/bin/pudding walk --project runs/my-company --live --budget-usd YOUR_LIMIT
```

To run the example brief directly from the command line, use the following commands:

```sh
python3 rig.py live --brief examples/typescript-boundaries/brief.toml \
  --out runs/first-live --budget-usd 0.10 --dry-run
python3 rig.py live --brief examples/typescript-boundaries/brief.toml \
  --out runs/first-live --budget-usd 0.10
python3 rig.py review --run runs/first-live
```

The `live --dry-run` command prints the search plan without credentials or network access. A live run checks current endpoint prices, searches LinkedIn and X, and looks up at most four LinkedIn profiles by default. Use `--profiles` to adjust that limit. A LinkedIn result needs a separate profile lookup with one clear current role. X results are research leads and stay on hold until an author is independently linked to a professional profile. This version searches posts and leaves comment and reply expansion to a future adapter update.

The run saves settled charges and Treg call IDs in `treg-run.json`. After an interruption, rerun the same walkthrough command with the same project, run name, cap and token. For `live` or `pilot run`, repeat the original command with `--resume`. Pudding reuses completed calls and follows [Treg's replay contract](https://treg.to/skill.md#retrying-without-paying-twice) for a pending request: it sends the original key and counts the original charge once, with no extra charge for a replay. If Treg is still processing, wait briefly and resume again. If Pudding cannot safely replay the result (for example, the run is more than 23 hours old or Treg didn't retain the result), it keeps the reservation and stops sending paid requests for that run. Check Treg Activity for the receipt. Keep live run folders private and use the fictional demo when sharing example outputs.

Self-Sourcing Pudding is an independent client of Treg. Treg provides the upstream access. See the [Treg terms](https://treg.to/terms) and the applicable upstream terms for use of live data.

## Bring your own offline records

Use `source --corpus path/to/corpus.json --out runs/custom` with your own brief. The [example corpus](../examples/preview-environments/corpus.json) defines the format. Set `as_of` to the snapshot date so a repeat run uses the same freshness checks, or override it with `--as-of YYYY-MM-DD`. Keep dates in `YYYY-MM-DD` format.

- A person needs a stable ID, name, role, employer, canonical HTTPS profile URL, and the date the role was last checked.
- Each observation has a stable ID, channel, kind, author, URL, publication date, and original text. Use the same `person_id` across both channels only after checking the author-to-profile link. Leave it absent when the identity is uncertain.
- Set `parent_id` on a comment, reply, or quote to bring it into review when the original post matches. The original post must be in the corpus. A parent's evidence stays with its own author.

The run folder contains the queue and a snapshot of the brief in `queue.json`, the review in `review.json`, and the shortlist in CSV and JSON. Create a fresh run folder after editing the brief so its review stays tied to the evidence and rules it used.

Run `python3 -m unittest discover -s tests` to check the demo, review, feedback and timeout recovery. Build a clean tester ZIP with `python3 package_tester.py /path/to/self-sourcing-pudding-tester.zip`.
