# Self-Sourcing Pudding

**Find the people already talking about the problem you solve.**

Give your coding agent your company URL. It searches LinkedIn, X and employer job ads for people describing that problem in their own words, checks who they are and where they work now, and hands you a shortlist. You say yes or no to each person.

Pudding is open source and runs on your computer. Your agent supplies the judgment. Pudding does the lookups, holds the spend cap and refuses any quote that isn't in the source.

## What you get

Every row is a person, their current role, the sentence that earned them a place, and a link to where they said it.

| Fit | Person | Current role | Evidence |
| --- | --- | --- | --- |
| strong | Nia Alder | Head of Procurement, Juniper Vale Software | “Purchase approvals kept getting stuck between Slack and a spreadsheet, so we piloted one request form with finance and IT last week.” |
| look · hiring signal | Idris Vale | VP Finance, Hollis Bay Health | “You will choose and roll out our first purchase-approvals system” |

These two are fictional. [See the full sample shortlist](examples/shortlist.md), or [the CSV](examples/shortlist.csv).

## Run it

You need Python 3.11 or later, a coding agent that can run commands, and a [Treg](https://treg.to) team for the paid lookups. New Treg accounts can start with US$1 in credit, which covers a first run. [Treg pricing](https://treg.to/pricing)

Clone the repository, then paste this into your agent:

> In the Self-Sourcing Pudding checkout, follow `docs/playbook.md` to find leads for `<my company URL>`. Our buyer is `<one sentence on who buys and why>`. Keep the run in a private folder outside the repository and stay under US$1. When the shortlist is ready, open the review page and tell me the funnel and the spend.

Add the buyer sentence if you can. Your site says what you sell; you know who buys it.

## What a run looks like

1. **The agent writes a search plan.** It reads your site and writes 25 to 35 searches in your buyer's voice: a tool they already use, next to a first-person phrase such as "we switched".
2. **It searches and reads.** LinkedIn and X posts come back onto a reading sheet. The agent grades each author and copies the exact sentence that shows their own work.
3. **Pudding verifies each person.** It confirms the LinkedIn identity and current role. It ties an X account to LinkedIn only by a link on the profile or a matching name and company.
4. **It reads job ads.** An ad that assigns this work to a new hire points to the person who owns it today.
5. **You review.** A page on your computer shows one person at a time. Press Y, N or M.
6. **It finds work email** for the people you said yes to, and confirms each mailbox.

Next time, start with `--previous`. Pudding skips everyone you have seen and shows the agent what you said yes and no to.

## What to expect

Three full runs on real companies, each read and graded by an agent following the playbook:

| Company | Buyer | Worth contacting |
| --- | --- | --- |
| An AI-native CRM | Founders and revenue operations | 25 |
| AI customer-support agents | Heads of support and customer experience | 15 |
| A review tool for coding agents | Technical founders and engineering leads | 25 |

- Lookups cost under US$0.60 a run.
- A run takes 20 to 25 minutes.
- LinkedIn search and job ads find most of the people. X helps for founders and developers.
- Your agent's own usage is separate. A full run reads several hundred posts.
- A search can finish with few people. Some buyers don't write about their work in public.

## Why you can trust a row

- **The quote is real.** Pudding rejects a grade unless the quote appears word for word in the captured post or ad.
- **The role is current.** Each person is checked against LinkedIn on the day of the run, and the shortlist says how.
- **Doubt is written down.** An agency, a solo founder, a role outside your buyer list: these are labels on the row, so you decide.
- **Weak matches stand apart.** Low-fit people, existing customers and anyone who couldn't be identified each get their own section.
- **Spend is capped.** Every paid lookup goes through one cap and leaves a receipt. A finished lookup is never charged twice.
- **Names stay on your computer.** The run lives in a private folder that only you can read.

## Commands

Your agent runs these. You can too.

```sh
python3 pudding.py --project ~/pudding-runs/acme start https://acme.example --budget-usd 1.00
```

| Command | What it does |
| --- | --- |
| `start URL` | Reads the site and creates the run folder. `--previous DIR` carries over an earlier run. |
| `check` | Validates the plan and the grades. |
| `search` | Runs the LinkedIn and X searches. |
| `sheet` | Writes the next reading sheet. `--jobs` for job ads. |
| `show ID…` | Prints posts or ads in full. |
| `verify` | Confirms identity and current role. |
| `spider` | Optional. Opens threads under graded posts. |
| `jobs`, `contacts` | Finds job ads, then the person who owns the work. |
| `shortlist` | Writes `shortlist.md` and `shortlist.csv`. |
| `review` | Opens the yes/no page on your computer. |
| `enrich` | Finds and verifies work email. |
| `status` | Shows the funnel and the spend. |

[Read the playbook](docs/playbook.md) for how the agent uses them.

## Limits

- Pudding finds and verifies people. It sends nothing.
- Quote posts on X need a metered read-only X connection on your Treg team.
- Check contact history and suppression in your own CRM before you reach out. `profile_url` in the CSV is the key to match on.

## Develop

```sh
python3 -m unittest discover -s tests
```

Standard library only. MIT licence.
