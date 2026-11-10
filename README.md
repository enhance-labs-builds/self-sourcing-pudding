# Self-Sourcing Pudding

**Find the people already talking about the problem you solve.**

Give your coding agent your company URL. It searches LinkedIn, X and job ads for people describing that problem in their own words, checks who they are and where they work now, and hands you a shortlist. You say yes or no to each person.

Pudding is open source. Your agent supplies the judgment. Pudding does the lookups, holds the spend cap and refuses any quote that isn't in the source.

## What you get

Every row is a person, their current role, the sentence that earned them a place, and a link to where they said it.

| Fit | Person | Current role | Evidence |
| --- | --- | --- | --- |
| strong | Nia Alder | Head of Procurement, Juniper Vale Software | “Purchase approvals kept getting stuck between Slack and a spreadsheet, so we piloted one request form with finance and IT last week.” |
| worth a look · hiring signal | Idris Vale | Head of Procurement, Hollis Bay Health | “You will choose and roll out our first purchase-approvals system” |

You go through them one at a time on a page on your own computer:

![The review page: one person, their role and employer, the quote, and Yes, No and Maybe buttons](docs/review-page.jpg)

The people shown here are fictional, so no real person is named. [See the full sample shortlist](examples/shortlist.md), or [the CSV](examples/shortlist.csv). The format is exactly what a real run writes.

## Run it

### Before you paste

You need four things:

- **A Mac or Linux computer** with a coding agent that can run commands on it, such as Claude Code, Codex or Cursor. Their desktop apps count. A chat window alone can't do this, and Windows isn't supported yet.
- **A new, empty folder**, opened in that agent. Make one called `pudding` and start the agent there, so it has nothing else of yours within reach.
- **A Treg account.** [Treg](https://treg.to) is the service that sells the lookups. Your agent sets it up with you: you sign in through your browser, and there is no key to copy.
- **About US$1 and half an hour.** Our first runs took 19 to 25 minutes once Treg was connected.

Then paste this into your agent, with your own details in place of the two parts in angle brackets:

> Clone https://github.com/enhance-labs-builds/self-sourcing-pudding (skip this if I already have it) and check I have Python 3.11 or later. Help me connect a Treg team. Then follow `docs/playbook.md` to find leads for `<my company URL>`. Our buyer is `<one sentence on who buys and why>`. Keep each run in its own dated folder under `~/pudding-runs` and stay under US$1. When the shortlist is ready, open the review page and tell me the funnel and the spend.

For example: "…find leads for `https://acme.example`. Our buyer is `the head of finance at a 50 to 500 person company who still approves purchases by email`."

The agent asks before it runs each command. Expect, in order: downloading the project, checking for Python (it will tell you how to install it if it is missing), installing Treg and signing you in, then Pudding's own commands, which all start `python3 pudding.py`. Stop and ask if it wants to do anything else.

It comes back with a page where you press **Y** for yes, **N** for no or **M** for maybe. Your answers save as you go. When you want email addresses for your yeses, paste:

> Get work email for the people I said yes to in my latest Pudding run. Raise that run's cap by US$0.03 a person to cover it.

Add the buyer sentence if you can. Your site says what you sell; you know who buys it.

### Which agent

Claude Sonnet and Codex both do it well. We gave each the same brief and had a second model judge the lists blind.

| Agent | Worth contacting | Second model would message | Second model rejected | Time | Lookup spend |
| --- | --- | --- | --- | --- | --- |
| Claude Sonnet 5.5 | 60 | 44 | 0 | 19 minutes | US$0.89 |
| Codex (GPT-6.1) | 75 | 48 | 0 | 25 minutes | US$0.94 |

The rest were maybes. The second model is lenient, so read "would message" as the useful column, and one run each as a direction.

## Run it every week

The people worth writing to are the ones who posted this week.

After your first run, paste this:

> Run Pudding again for `<my company URL>` as a follow-up to my latest run under `~/pudding-runs`, following "Following runs" in `docs/playbook.md`. Stay under US$1. Tell me who is new and open the review page.

A follow-up starts from last time's plan and your yes and no answers. The agent keeps the searches that found people and replaces the ones that didn't. Pudding reads only what was posted since, and skips every post it has read and everyone it has shown you. Anyone you haven't answered stays on that week's list. Your suppression list carries over.

- **A first run** reads 45 days back. Ours returned 60 to 75 people, on a topic people post about every day. Two quieter topics returned 25 and 15.
- **A weekly run** reads what is new. We have tested one, not a month of them: over a nine-day window it found 31 new people, 4 of them strong, in 14 minutes for US$0.40. That test ran the same day as the first run, so some of the 31 were people the first run never reached. Our guess from it is a third to a half of your first run each week. We will know after a month of real ones.
- **Daily is too thin** for most topics. Weekly gives you a list you can write to personally and finish.

To make it a habit, ask your agent to schedule it:

> Every Monday at 8am, run Pudding from the folder you cloned it into, for `<my company URL>`, as a follow-up to the latest run under `~/pudding-runs`, following "Following runs" in `docs/playbook.md`. Stay under US$1. Stop when the shortlist is written and tell me how many people are new.

Claude Code and Codex can both run a prompt on a schedule, and a cron job that starts your agent with this prompt works anywhere. Your computer has to be on. A scheduled run needs your agent to be allowed to run Pudding's commands without asking, which removes the approval step, so read "Keep it safe" first and run it by hand for a few weeks before you schedule it. Pasting the follow-up prompt each Monday works just as well.

## What it costs

- **Treg lookups: about US$1 for a first run.** Ours spent US$0.70 to US$0.95 against a US$1 cap, and a weekly follow-up US$0.40. You pay Treg, not us. Treg advertises US$1 in starting credit for new accounts. [Treg pricing](https://treg.to/pricing)
- **The cap is hard.** Pudding reserves each lookup's worst-case cost before sending it and refuses any that would not fit. Runs often spend close to the cap. Within each step it looks up the strongest people first, and it says how many lookups the cap refused.
- **Work email is extra: about US$0.03 a person.** Thirty people is about US$1. When you get there, raise the run's cap with `budget` and run the email step.
- **Your agent's usage is separate.** A run reads several hundred posts: our Claude runs used roughly 250,000 to 410,000 tokens each. On a Claude or ChatGPT subscription that comes out of your plan's usage.
- **Your Treg balance is the outer limit.** Treg is prepaid: it spends only what you have loaded, unless you turn on automatic top-ups. The cap belongs to one run folder, and nothing stops an agent starting another run, so keep only a few dollars in the account and leave top-ups off.

## What it touches

- **Your LinkedIn and X accounts: never.** Pudding does not sign in to either, and it sends nothing. The one exception is yours to choose: reading quote posts on X needs a read-only X connection on your Treg team.
- **Treg: every paid lookup.** Treg is a hosted service that sells data lookups by the call, and Pudding is an independent client of it. Behind Treg, LinkedIn data (posts, profiles, companies and job ads) comes from HarvestAPI, X data from AnyAPI and the X API, search from Serper and Exa, and email from AnyAPI and Hunter. The names and profile links Pudding looks up go to Treg and those providers.
- **Websites: read directly from your computer**, under Pudding's own name: your company site, the job ads, and the website linked on an X author's profile when it is working out who they are.
- **Your computer: one private folder.** The run's files stay there, readable only by you, until you delete them. The posts are read by your agent's model.
- **Other people's data.** Pudding reads public posts and finds work email. Whether and how you may contact someone depends on your own obligations, including the platforms' terms and privacy law where you and they are.

### Connect Treg

Your agent does this with you the first time:

1. It installs Treg's command-line tool with Treg's own installer (`curl -fsSL https://treg.to/install.sh | sh`) and runs `treg login`. Your browser opens, and you sign in with Google, GitHub or an emailed code. A new account starts with one team.
2. It runs `python3 pudding.py connect` to confirm it works. That check costs nothing.

If you already have a Treg team token, set `TREG_TOKEN` and `TREG_ORG` in the terminal your agent uses instead. Use a team with no connected provider keys or custom tools, so every lookup is billed through Treg and counted against your cap. Pudding sends the token only to `treg.to`, and before each paid step it checks that the team has no other connections.

### Keep it safe

Your agent reads hundreds of posts written by strangers, and a post can contain text written to trick an AI into doing something else. The playbook tells the agent to treat every post as data, and every sheet Pudding writes repeats it, but no instruction makes that impossible. So give the agent little to reach:

- **Start it in a new, empty folder**, not inside a project that holds passwords or keys.
- **Approve only what "Before you paste" lists**: fetching the project, the Python check, the Treg install and sign-in, and commands that start `python3 pudding.py`. Stop and ask if it wants to run anything else, or if it runs `budget` when you haven't asked for more spend.
- **Keep the Treg balance small.** It is the most a mistake can spend.

## What a run looks like

1. **The agent writes a search plan.** It reads your site and writes 25 to 35 LinkedIn searches in your buyer's voice, a dozen or more for X and a handful for job ads. Each pairs a tool they already use with a phrase such as "we switched" or "our renewal".
2. **It searches and reads.** Posts come back onto a reading sheet with teams describing their own work first, and job ads, job seekers and launch posts last. The agent reads several hundred, grades each author and copies the exact sentence that shows their own work.
3. **Pudding verifies each person.** It confirms the LinkedIn identity and current role, and looks up the employer's size and industry. It follows an X author to LinkedIn the way you would: the link on their profile, their website, a search on their name and the company in their bio. A link on their own X profile is taken as given. A profile found by searching needs two checkable ties to the account, and a matching name counts once. One the agent works out by name alone is kept with a label saying so.
4. **The agent regrades from the employer.** It drops direct competitors and labels agencies, nearby sellers and giants.
5. **It reads job ads.** It searches LinkedIn's job listings and the employer job boards, one ad per employer. An ad that hands this work to a new hire, or describes a team working the way your buyer does, points to whoever holds that job at the employer today. Pudding looks for them in the ad's hiring team, LinkedIn's list of people at that employer, and the web.
6. **You review.** A page on your computer shows one person at a time.
7. **It finds work email** for the people you said yes to, and confirms each mailbox with a second provider.

The shortlist is `shortlist.csv` in the run folder. Each row has the person's name, role, company, the company's size, industry and web domain, location, LinkedIn link, X handle, quote, source, the search that found them, the run date and your answer. Filter on `fit` and `your_answer` before you import it. The email step adds their address.

Add `--suppress` with a list or a CRM export to leave out people already in your pipeline. A LinkedIn profile link leaves out that person. A company name or LinkedIn company link leaves out that company. A work email or web domain leaves out the company whose website is on that domain.

## We ran it on ourselves

We make a review tool for coding agents. One run found 60 people worth contacting in 19 minutes for US$0.89: 43 from LinkedIn posts, 5 from X and 12 from job ads. It graded 11 strong and set another 16 aside as low fit.

Five of the strong ones:

- A founder whose reviewers can't run every change by hand, and whose agents' own checks miss regressions.
- A chief executive whose agents write more code each week than any human team can check.
- A co-founder whose open pull requests grow faster than the team can review them.
- A chief technology officer whose output went up while review time didn't, and who now calls review the team's biggest constraint.
- A founder hiring someone to orchestrate agents and review their work.

**Then we checked it.** A second model, Claude, saw only each person's role, employer and quote, with no grades. It would message 44 of the 60, including 9 of the 11 strong, and was unsure about the rest. It would also message 5 of the people set aside as low fit, so the grades are a guide, not a verdict.

**Then we read the first few ourselves.** They were right.

## What to expect

Two other companies, each read and graded by Claude on an earlier version:

| Company | Buyer | Worth contacting |
| --- | --- | --- |
| An AI-native CRM | Founders and revenue operations | 25 |
| AI customer-support agents | Heads of support and customer experience | 15 |

- "Worth contacting" is the agent's grade. Your yes is the one that counts, which is why the review page exists.
- LinkedIn posts find most of the people. X added 5 of our 60 and job ads 12.
- Job ads depend on the buyer. Run on its own for the CRM company, the job-ad step read 96 ads and found the owner behind 15, six of them strong.
- This is a list for writing to people personally, with the evidence on every row. It is not a volume source.

## Where it works

Pudding works when your buyers write about their work in public, in English, and name the tools they use. Every run above was B2B software sold to people who post on LinkedIn and X.

Expect less when your buyers rarely post or your market isn't English-speaking. Job ads come from LinkedIn and from Greenhouse, Ashby, Lever, Workday, SmartRecruiters and Workable. A search can finish with few people.

## Why you can trust a row

- **The quote is real.** Pudding rejects a grade unless the quote appears word for word in the captured post or ad.
- **The role is current.** Each person is checked against LinkedIn when the run looks them up, and the shortlist says what the check rested on.
- **The employer is described.** Its size on LinkedIn, its industry and its own one-line description sit on the row, so an agency or a bank with 80,000 staff is obvious.
- **A hiring signal is labelled as one.** Its quote is from the employer's job ad, and the person is whoever holds that job there today.
- **Doubt is written down.** A possible seller, an agency, a solo founder, an identity the agent worked out by name: these are labels on the row, so you decide.
- **Weak matches stand apart.** Low-fit people, existing customers and anyone who couldn't be identified each get their own section.
- **Spend is capped.** Every paid lookup goes through one cap and leaves a receipt. A finished lookup is never charged twice in a run.

The reason on each row is the agent's own sentence. Read the quote and follow the link before you write to anyone.

## Commands

Your agent runs these for you. [The playbook](docs/playbook.md) is its manual; you don't need to read it.

```sh
python3 pudding.py --project ~/pudding-runs/acme/2026-11-10 start https://acme.example --budget-usd 1.00
```

| Command | What it does |
| --- | --- |
| `connect` | Checks the Treg sign-in. Costs nothing. |
| `start URL` | Reads the site and creates the run folder. `--previous DIR` makes it a follow-up to an earlier run. `--suppress FILE` leaves out people and companies you already have. |
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
| `budget USD` | Raises this run's spend cap. It never rises by itself. |
| `status` | Shows the funnel and the spend. |

## Limits

- Pudding finds and verifies people. It sends nothing.
- We have no reply or meeting numbers yet, and no measured hit rate for work email. The email check is strict: a company whose mail server accepts every address gets none.
- A first run reads posts from the last 45 days and a follow-up reads what was posted since the last run. LinkedIn returns the newest posts first, about 40 a search, so a busy search reaches back days, not weeks. Job ads go back 90 days. Change the windows with `start --window-days` and `jobs --lookback-days`.
- Quote posts on X are off by default. `spider --quote-pages 2` reads them if your Treg team has a read-only X connection.
- Each run writes its own CSV in its own folder. Check contact history in your own CRM before you reach out: `profile_url` is the key to match on.
- Names and posts stay in the run folders until you delete them. There is no command to remove one person.

## Develop

```sh
python3 -m unittest discover -s tests
```

Standard library only. MIT licence. Built by [Enhance Labs](https://enhancelabs.ai).
