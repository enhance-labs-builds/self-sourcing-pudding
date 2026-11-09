# Self-Sourcing Pudding guide

[Quick start](../README.md)

## Edit the brief and review a run

```sh
python3 rig.py init --example
python3 rig.py plan
python3 rig.py source --out runs/first
python3 rig.py review --run runs/first
```

The example uses the Ramp Procurement brief and fictional posts. Between `init` and `plan`, open `brief.toml` and edit it. For a quick experiment, keep only `"Zip"` under `alternatives` and replace `signals` with `["security review"]`. The general purchasing thread drops out of the queue and the discussion about evaluating Zip stays in.

Run `init` without `--example` for guided setup. The questions cover your product, target roles, problem language, competitors and workarounds, and what a good fit and a near miss look like. `plan` shows the terms and evidence rules before discovery. To reuse a previous review on the same queue, pass its `review.json` to `review --decisions`.

Discovery looks for your phrases in local LinkedIn and X records. It also opens comments, replies, and quotes attached to matching posts. It groups sightings by the corpus's verified person ID and puts current candidates with a matching role higher in the queue. A role, keyword, or competitor match helps find people to review. You make the fit decision from the original text and current role.

Choose firsthand problem, explicit work, hold, or pass. To qualify someone, pick a current source attributed to that person, keep an exact excerpt, and record why it fits your brief. An unresolved identity, an old role check, or a lack of current evidence holds the candidate. Contact history is marked `unchecked`.

## Start from a company URL

The pilot commands keep an editable brief and feedback in one local project.

```sh
python3 rig.py pilot start https://ramp.com/procurement --project runs/ramp \
  --starter examples/company-briefs/ramp.toml
python3 rig.py pilot approve --project runs/ramp
python3 rig.py pilot status --project runs/ramp
```

`start` reads the site's public copy, social links and comparison links. It proposes roles and search phrases when the copy supports a starting hypothesis. The guided `walk` asks for the workflow, roles and search phrases when the draft needs them. You can also add competitors and phrases that describe companies you want to prioritize. Use `--starter` with `pilot start` to import a researched brief, or `--website` when your starting LinkedIn or X URL needs a public company site. Review or edit the draft before approval. Any later edit to the brief's settings needs a new approval.

The preview defaults to at most 20 people with a current LinkedIn role and dated source. Use `--target` to choose your own review limit. `holds.json` contains candidates with an identity or freshness gap. Follow-up search can resolve some X authors automatically. You can also supply a reviewed match with `--identities` or add it to an offline corpus. An identities file is a JSON array with `source_url`, `author`, `profile_url`, `name`, `role`, `company`, `role_checked_on`, `binding_source`, and `role_source` on each row. Use the exact post URL and author from the corpus. `binding_source` and `role_source` should point to the public evidence for the identity match and the current role. You can replay a paid run locally with `--corpus path/to/corpus.json`.

Review saves yay/nay with evidence or a reason. A yay can keep someone for follow-up, or add them to the shortlist if you select firsthand evidence. The next run skips evidence you've already voted on and can surface a person again when they publish new evidence. A wrong role or wrong account vote also suppresses further results for that same role or account. `preview.json` records spend and whether each channel completed. For a recurring batch size, set `limits.batch_target` in the brief and use `pilot run --batch`. Tune query count with `--searches`, role lookups with `--profiles`, and search depth with `--pages` and `--results-per-search`. The target and spend limit are ceilings. The pilot is run on demand.

### Draft a brief with a browsing-enabled agent

In a browsing-enabled coding agent, open this repository and ask:

> Use `<company URL>` to draft an editable sourcing brief. Read the official site and relevant public posts. Show who does the work, how they talk about it, alternatives they use, and what makes their company a fit. Ask me to approve or edit the brief and choose a spend limit. Then search LinkedIn and X. Shortlist people only when you can verify their current role and evidence of the work in their own words.

Start with the company's public LinkedIn page, X (Twitter) profile, or website. Use the official site to check that the profiles belong to the right company. Search the company name for customer examples, then search the problem language and alternatives for people outside the company's audience. Treat customer segments as hypotheses and use candidate evidence to decide who qualifies. The agent drafts the brief and reviews candidates. The CLI runs discovery and records evidence, spend, and decisions. Live discovery uses the Treg setup below.

The [Ramp brief](../examples/company-briefs/ramp.toml) shows how to turn a public product page into an editable sourcing brief. Edit its target roles and qualification criteria to steer who makes the shortlist. Use `[[searches]]` to set the query order and choose what to look for. Search by `problem`, `brand`, `alternative`, or `account`.

In a URL draft, edit `signals` and `alternatives` to regenerate queries. Alternatives are paired with workflow phrases from the same brief. Add explicit `[[searches]]` entries to take control of the query order and wording. Run `live --dry-run` with your brief, output path and budget to see the queries before spending. The direct `live` command runs the first four planned queries by default. `--searches` lets you run fewer.

## Find people working with alternatives

Pair an alternative with the workflow people actually talk about. The rig asks for the name and at least one workflow phrase on both channels, then checks both against the same post. LinkedIn requests recent posts first for these searches. Use `[[customer_stories]]` to find case studies in the competitor's own customer story directory. Both routes use the same run budget.

```toml
[[searches]]
lane = "alternative"
phrase = "Zip"
workflow = ["procurement intake", "purchase approvals", "purchase order"]

[[customer_stories]]
competitor = "Zip"
site = "https://ziphq.com/customers"
workflow = "procurement intake"
```

Customer stories land in `customer-story-queue.json` for review. Open the original and look for the named customer who describes doing the work. Check their current role independently and record the team, the quote, and when the work happened if known. A dated post describing a live evaluation or unresolved problem is a timing signal. A vendor case study can show installed use and surface a workflow owner. Keep the person's current buying intent unknown unless they give you separate evidence of it.

Use a verified story to improve the next social query. With `lane = "account"`, set `phrase` to the customer name and `workflow` to the phrases from the story. Set `seed_url` to keep the original story linked to posts found by that query. You can also search those phrases on their own with `lane = "problem"` to find teams describing the same pain without naming a tool. For an ambiguous name, add narrow `exclude_phrases` to that query, such as `["Tata Sierra"]`; the rig filters those phrases from returned posts. Evaluate the original author and workflow each time, even when someone quotes a strong customer story. Use `--profiles 0` if you want to review the evidence before paying to check anyone's current role.

The [Stripe](../examples/company-briefs/stripe.toml) and [Harvey](../examples/company-briefs/harvey.toml) briefs show how the workflow and alternatives change in other markets.

## Run a live search

Sign in to the [Treg dashboard](https://treg.to/app?ref=docs). Use a team with prepaid balance and no custom provider keys or tools. You can add one [Treg-managed read-only X connection](#include-x-quote-posts). Copy the team slug and create an API key for that team. Pudding uses that key as its token. Keep it out of the brief and repository.

Set these in the terminal where you’ll run Pudding. Paste your token at the prompt and press Enter.

```sh
export TREG_ORG='your-team-slug'
printf 'Treg API token: '
read -rs TREG_TOKEN
printf '\n'
export TREG_TOKEN
```

From the repository folder, start a live search with your walkthrough project. Pudding asks how much to spend before it runs paid searches. You can also supply `--budget-usd` up front. Use `--target` to pick the maximum number of people to review.

```sh
.pudding/bin/pudding walk --project runs/my-company --live
```

To inspect the Ramp example's search plan and then run the project you approved earlier, use:

```sh
python3 rig.py live --brief examples/company-briefs/ramp.toml \
  --out runs/first-live --budget-usd 0.10 --dry-run
python3 rig.py pilot run --project runs/ramp --run preview --budget-usd 0.50 --spider
python3 rig.py pilot review --project runs/ramp --run preview
```

The `live --dry-run` command prints the search plan without credentials or network access. The standalone `live` command checks current endpoint prices, searches LinkedIn and X, and looks up at most four LinkedIn profiles by default. Use `--profiles` to adjust that limit. Use the live walkthrough or `pilot run` when you want work email lookup. A LinkedIn result needs a separate profile lookup with one clear current role. X results are research leads and stay on hold until an author is independently linked to a professional profile.

If the first preview is thin, check `preview.json` for LinkedIn and X coverage and `holds.json` for evidence or identity gaps. When the searches completed and the results are still off, edit the brief before the next run. Use phrases you saw practitioners use in their own posts, pair an alternative with a concrete workflow, and describe the kinds of companies you want to find. Review and approve the revised brief, then use a new run name in the same project to keep your votes.

The run saves settled charges and Treg call IDs in `treg-run.json`. After an interruption, rerun the same walkthrough command with the same project, run name, cap and token. For `live` or `pilot run`, repeat the original command with `--resume`. Pudding reuses completed calls and follows [Treg's replay contract](https://treg.to/skill.md#retrying-without-paying-twice) for a pending request: it sends the original key and counts the original charge once, with no extra charge for a replay. If Treg is still processing, wait briefly and resume again. If Pudding cannot safely replay the result (for example, the run is more than 23 hours old or Treg didn't retain the result), it keeps the reservation and stops sending paid requests for that run. Check Treg Activity for the receipt. Keep live run folders private and use the fictional demo when sharing example outputs.

Self-Sourcing Pudding is an independent client of Treg. Treg provides the upstream access. See the [Treg terms](https://treg.to/terms) and the applicable upstream terms for use of live data.

### Work email lookup

`walk --live` and `pilot run` look up work emails for review candidates whose current roles match the brief. With follow-up search enabled, people with strong firsthand evidence are also eligible. Pudding uses the website on the current employer’s LinkedIn company page to check the address domain. A separate verifier must mark the mailbox valid and confirm that the domain isn’t catch-all.

Review cards display verified addresses. For each shortlisted candidate, the CSV carries `work_email`, `work_email_status`, and `work_email_checked_on`. Statuses include `employer_unconfirmed`, `no_matching_work_email`, `unverified`, and `budget_limit`. The same spend limit covers discovery, role checks, and email. Use `pilot run --no-email` to skip lookup and verification. If you supply a reviewed X identity through `--identities`, include its current employer’s LinkedIn `company_url` to make it eligible. Keep live run folders private.

### Follow posts and employers

The live walkthrough follows promising threads and employers by default. Use `--no-spider` to run the initial search alone. With `pilot run` or `live`, add `--spider` to include follow-up searches.

```sh
.pudding/bin/pudding walk --project runs/my-company --live --target 12
```

Pudding reads one page of comments on a selected LinkedIn post and one page of replies on a selected X post. It checks promising authors' current roles. To search for coworkers, it looks for firsthand wording that names the confirmed employer in the passage describing the work. Clear client and side-project wording leaves the employer search on hold. Pudding follows up to two employers and retains the source link and the passage that led there.

Set `company_signals` in the brief to describe companies that deserve a closer look, for example `["municipal fleet", "fleet maintenance"]`. Pudding can check up to three verified employers' public LinkedIn descriptions. It records the matching passage and link. This can lift someone who left a short reply even when nobody else at their company has posted about the work. The shortlist still needs current evidence from that person's own words.

For a few promising X authors, Pudding checks whether their public profile links directly to LinkedIn, then compares the names and verifies the LinkedIn role. Unresolved identities stay on hold. Follow-ups share the run's budget and role lookup limit. Pudding skips a follow-up if it can't reserve enough for the call. Use the printed continuation command after an interruption.

#### Include X quote posts

Treg already provides X search and replies through AnyAPI. To include quote posts, connect X on the same Treg team and choose **Read** access. If you use the Treg CLI, run:

```sh
treg connections connect --provider x --capability read
```

Approve access in X and start a new `--spider` run. Pudding checks that Treg meters the connection to your team balance before requesting up to one page of quote posts for the selected X post. It verifies that each result quotes the original post and keeps the original link for review.

## Bring your own offline records

Use `source --corpus path/to/corpus.json --out runs/custom` with your own brief. The [fictional Ramp demo corpus](../examples/ramp-demo/corpus.json) shows the format. Set `as_of` to the snapshot date so a repeat run uses the same freshness checks, or override it with `--as-of YYYY-MM-DD`. Keep dates in `YYYY-MM-DD` format.

- A person needs a stable ID, name, role, employer, canonical HTTPS profile URL, and the date the role was last checked.
- Each observation has a stable ID, channel, kind, author, URL, publication date, and original text. Use the same `person_id` across both channels only after checking the author-to-profile link. Leave it absent when the identity is uncertain.
- Set `parent_id` on a comment, reply, or quote to bring it into review when the original post matches. The original post must be in the corpus. A parent's evidence stays with its own author.

The run folder contains the queue and a snapshot of the brief in `queue.json`, the review in `review.json`, and the shortlist in CSV and JSON. Create a fresh run folder after editing the brief so its review stays tied to the evidence and rules it used.

Run `python3 -m unittest discover -s tests` to check the demo, review, feedback and timeout recovery. Build a clean tester ZIP with `python3 package_tester.py /path/to/self-sourcing-pudding-tester.zip`.
