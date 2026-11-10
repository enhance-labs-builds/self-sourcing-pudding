# Self-Sourcing Pudding

**Find the people already talking about the problem you solve.**

Give your coding agent your company URL. It searches LinkedIn, X and employer job ads for people describing that problem in their own words, checks who they are and where they work now, and hands you a shortlist. You say yes or no to each person.

Pudding is open source. Your agent supplies the judgment. Pudding does the lookups, holds the spend cap and refuses any quote that isn't in the source.

## What you get

Every row is a person, their current role, the sentence that earned them a place, and a link to where they said it.

| Fit | Person | Current role | Evidence |
| --- | --- | --- | --- |
| strong | Nia Alder | Head of Procurement, Juniper Vale Software | “Purchase approvals kept getting stuck between Slack and a spreadsheet, so we piloted one request form with finance and IT last week.” |
| worth a look · hiring signal | Idris Vale | Head of Procurement, Hollis Bay Health | “You will choose and roll out our first purchase-approvals system” |

These two are fictional, so no real person is named here. [See the full sample shortlist](examples/shortlist.md), or [the CSV](examples/shortlist.csv). The format is exactly what a real run writes.

## Run it

Paste this into a coding agent that can run commands on your computer, such as Claude Code, Codex or Cursor. Pudding runs on macOS and Linux.

> Clone https://github.com/enhance-labs-builds/self-sourcing-pudding (skip this if I already have it) and check I have Python 3.11 or later. Help me connect a Treg team. Then follow `docs/playbook.md` to find leads for `<my company URL>`. Our buyer is `<one sentence on who buys and why>`. Keep the run in a private folder outside the repository and stay under US$1. When the shortlist is ready, open the review page and tell me the funnel and the spend.

That is the whole setup. The agent fetches the project, asks you to approve the commands it runs, and comes back in 10 to 25 minutes with a page where you press **Y** for yes, **N** for no or **M** for maybe. Your answers save as you go.

Add the buyer sentence if you can. Your site says what you sell; you know who buys it.

### Which agent

Start with Claude Sonnet. On this version it returned 33 people in 20 minutes for US$0.44 in lookups, 13 of them from X. A second model, judging blind, would message 24 of the 33 and rejected 2. It said yes to all eight graded strong.

Codex runs the playbook too and is stricter: on an earlier version it returned 9 people, and the second model would message 6. Claude Opus costs more and, on an earlier version, found no more than Sonnet.

One run each, so read this as a direction.

### Connect Treg

1. Create a Treg account and a team. Use a team with no connected provider keys or custom tools, so every lookup is billed through Treg and counted against your cap. One read-only X connection is allowed.
2. Give your agent access: set `TREG_TOKEN` and `TREG_ORG` in the terminal it uses, or sign in with the Treg CLI. [Treg docs](https://treg.to/docs)
3. Your agent runs `python3 pudding.py connect` to confirm it works. That check costs nothing.

Pudding reads those two values, or the Treg CLI's sign-in if they aren't set. It sends the token only to `treg.to`, and before each paid step it checks that the team has no other connections.

**Run your agent without other secrets in reach.** It reads hundreds of posts written by strangers. Start it in an empty folder, not inside a project that holds keys. The playbook tells it to treat posts as data, and a careful setup doesn't rely on that alone.

## What a run looks like

1. **The agent writes a search plan.** It reads your site and writes 25 to 35 LinkedIn searches in your buyer's voice, plus a dozen or more for X and a handful for job ads. Each pairs a tool they already use with a phrase such as "we switched" or "our renewal".
2. **It searches and reads.** LinkedIn and X posts come back onto a reading sheet, roughly ordered so first-person posts about your topic come first. The agent reads several hundred, grades each author and copies the exact sentence that shows their own work.
3. **Pudding verifies each person.** It confirms the LinkedIn identity and current role. It follows an X author to LinkedIn the way you would: the link on their profile, their website, a search on their name and the company in their bio. It accepts a profile only when two checkable things tie it to the account, and the agent works out the ones it can't. It also looks up each employer, flags anyone whose own company sells in your category, and the agent drops direct competitors and labels agencies, nearby sellers and giants.
4. **It reads job ads.** An ad that assigns this work to a new hire points to the person who owns it today.
5. **You review.** A page on your computer shows one person at a time.
6. **It finds work email** for the people you said yes to, and confirms each mailbox with a second provider.

The shortlist is `shortlist.csv` in the run folder. It has each person's name, role, company, the company's size and industry, location, LinkedIn link, quote and source, plus your answer. The email step adds their address and the company's domain.

Next time, start with `--previous`. Pudding leaves out everyone you have seen and shows the agent what you said yes and no to. Add `--suppress` with a list or a CRM export to leave out people already in your pipeline. A LinkedIn profile link leaves out that person; a work email, domain, company link or company name leaves out the whole company.

## We ran it on ourselves

We make a review tool for coding agents. Across two runs, Pudding found 52 people worth contacting for US$0.65: 17 graded strong and 35 worth a look. It set another 32 aside as low fit.

Five of the strong ones:

- A co-founder whose open pull requests were growing faster than the team could review them.
- A CTO who measured how many changes still needed a fix after passing every check.
- A founder who stopped reading code line by line and now verifies by using the product.
- An engineering manager who rebuilt review because agents open pull requests all day.
- A CEO with under ten engineers and more changed code each week than anyone could read.

**Then we checked it.** A second model saw only each person's role, employer and quote, with no grades. It would message 14 of the 17 strong and 15 of the 35 worth a look, and 1 of the 32 set aside. Sixteen of the 52 were already on our own prospect list.

**Then we read the first few ourselves.** They were right.

## What to expect

Two more full runs, on other companies, each read and graded by Claude following the playbook:

| Company | Buyer | Worth contacting |
| --- | --- | --- |
| An AI-native CRM | Founders and revenue operations | 25 |
| AI customer-support agents | Heads of support and customer experience | 15 |

- "Worth contacting" is the agent's grade. Your yes is the one that counts, which is why the review page exists.
- LinkedIn and X find most of the people: in our latest run 13 of 33 came from X. Job ads add a few when employers hire through the boards Pudding reads.
- This is a short list for writing to people personally, with the evidence on every row. It is not a volume source.

## Where it works

Pudding works when your buyers write about their work in public, in English, and name the tools they use. All three runs above were B2B software sold to people who post on LinkedIn and X.

Expect less when your buyers rarely post, when your market isn't English-speaking, or when employers don't hire through the job boards Pudding reads: Greenhouse, Ashby, Lever, Workday, SmartRecruiters and Workable. A search can finish with few people.

## Why you can trust a row

- **The quote is real.** Pudding rejects a grade unless the quote appears word for word in the captured post or ad.
- **The role is current.** Each person is checked against LinkedIn when the run looks them up, and the shortlist says what the check rested on.
- **The employer is described.** Its size on LinkedIn, its industry and its own one-line description sit on the row, so an agency or a bank with 80,000 staff is obvious.
- **A hiring signal is labelled as one.** Its quote is from the employer's job ad, and the person is whoever owns that work today.
- **Doubt is written down.** A possible seller, an agency, a solo founder, a role outside your buyer list: these are labels on the row, so you decide.
- **Weak matches stand apart.** Low-fit people, existing customers and anyone who couldn't be identified each get their own section.
- **Spend is capped.** Every paid lookup goes through one cap and leaves a receipt. A finished lookup is never charged twice.

The reason on each row is the agent's own sentence. Read the quote and follow the link before you write to anyone.

## Commands

Your agent runs these for you. [The playbook](docs/playbook.md) is its manual; you don't need to read it.

```sh
python3 pudding.py --project ~/pudding-runs/acme start https://acme.example --budget-usd 1.00
```

| Command | What it does |
| --- | --- |
| `connect` | Checks the Treg sign-in. Costs nothing. |
| `start URL` | Reads the site and creates the run folder. `--previous DIR` carries over an earlier run. `--suppress FILE` leaves out people and companies you already have. |
| `check` | Validates the plan and the grades. |
| `search` | Runs the LinkedIn and X searches. |
| `sheet` | Writes the next reading sheet. `--jobs` for job ads. |
| `show ID…` | Prints posts or ads in full. |
| `verify` | Confirms identity and current role, and looks up the employer. |
| `timeline @handle`, `web "query"` | Evidence for placing an X author `verify` could not: their recent posts, and a web search. |
| `spider` | Optional. Opens threads under graded posts. |
| `jobs`, `contacts` | Finds job ads, then the person who owns the work. |
| `shortlist` | Writes `shortlist.md` and `shortlist.csv`. |
| `review` | Opens the yes/no page on your computer. |
| `enrich` | Finds and verifies work email for your yes answers. |
| `status` | Shows the funnel and the spend. |

## Limits

- Pudding finds and verifies people. It sends nothing.
- Posts from the last 45 days and job ads from the last 90 are the defaults. Change them with `start --window-days` and `jobs --lookback-days`.
- Quote posts on X are off by default. `spider --quote-pages 2` reads them if your Treg team has a read-only X connection.
- Check contact history in your own CRM before you reach out. `profile_url` in the CSV is the key to match on. `company_domain` is filled in once `enrich` has run.

## Develop

```sh
python3 -m unittest discover -s tests
```

Standard library only. MIT licence. Built by [Enhance Labs](https://enhancelabs.ai).
