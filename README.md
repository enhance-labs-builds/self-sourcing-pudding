<p align="center">
  <img src="docs/pudding.webp" alt="Self-Sourcing Pudding: a felt pudding holding a pair of binoculars" width="200">
</p>

<p align="center"><strong>Find the people already talking about the problem you solve.</strong></p>

Give your coding agent your company URL and a sentence about who buys from you. It searches LinkedIn, X and job ads for people describing that problem in their own words, checks who they are and where they work now, and brings back a shortlist. You go through it and say yes or no to each person.

Pudding is open source and runs on your own computer. Your agent does the reading and judging. Pudding does the lookups, keeps to the spend cap you set, and refuses any quote that isn't in the original post.

## You get a shortlist of people, in their own words

Each person comes with their current role, the sentence that earned them a place, and a link to where they said it.

| Fit | Person | Current role | Evidence |
| --- | --- | --- | --- |
| strong | Priya Rowan | Procurement Operations Manager, Ashmere Hospitality | “Our approvals contract is up for renewal in March and we're evaluating alternatives.” |
| worth a look · hiring signal | Idris Vale | Head of Procurement, Hollis Bay Health | “You will choose and roll out our first purchase-approvals system” |

A hiring signal comes from a job ad that shows the team has the problem. The person on the row is whoever owns that work there today.

Everything on the list is recent. Pudding reads posts from the last 45 days and job ads from the last 90, and checks each person's current role on LinkedIn on the day it runs. On our own run, the typical post was 11 days old and every job ad was under four weeks old.

You review them one at a time on a page on your own computer, pressing **Y**, **N** or **M** for yes, no or maybe:

![The review page: one person, their role and employer, the quote, and Yes, No and Maybe buttons](docs/review-page.jpg)

These people are fictional, so no one real is named here. The [sample shortlist](examples/shortlist.md) and [its CSV](examples/shortlist.csv) are in exactly the format a real run writes.

When we ran it on our own product, it found 60 people worth contacting in 19 minutes for US$0.89. [Here's what they looked like and how we checked them.](#we-ran-it-on-ourselves)

## It works when your buyers post about their work

Pudding finds people who write in public, in English, about the work your product changes, and who name the tools they use. B2B software sold to founders, engineers, operators and team leads is a good fit. Our own topic, coding agents, is one people post about every day. For an AI-native CRM it found 25 people, and for AI support agents 15. If your buyers rarely post, expect a shorter list.

## Your coding agent runs it for you

### What you need

- **A Mac or Linux computer with a coding agent**, such as Claude Code, Codex or Cursor. Their desktop apps work. A chat window on its own can't run it.
- **A new, empty folder.** Make one called `pudding`, and choose it as the folder when you start a new session in your agent. Your agent will read posts written by strangers, and one could contain text meant to trick an AI, so it's best if nothing else of yours is within reach.
- **A Treg account.** [Treg](https://treg.to) is the service Pudding buys its lookups from. Your agent sets it up with you: you sign in through your browser, and there is no key to copy.
- **About US$1 and half an hour.**

### Paste this

Replace the two parts in angle brackets with your own details:

> Clone https://github.com/enhance-labs-builds/self-sourcing-pudding (skip this if I already have it) and check I have Python 3.11 or later. Help me set up Treg. Then follow `docs/playbook.md` to find leads for `<my company URL>`. Our buyer is `<one sentence on who buys and why>`. Keep each run in its own dated folder under `~/pudding-runs` and stay under US$1. When the shortlist is ready, open the review page and tell me the funnel and the spend.

For example: "…find leads for `https://acme.example`. Our buyer is `the head of finance at a 50 to 500 person company who still approves purchases by email`." The buyer sentence matters more than anything else you type: your site says what you sell, but you know who buys it.

### What happens next

Leave your agent set to ask before it runs each command. You will see, in order: downloading the project, a check for Python (it will help you install it if it's missing), installing Treg and signing you in, and then Pudding's own commands, which all start `python3 pudding.py`. If it asks to run anything else, stop and ask why.

About 20 to 25 minutes later it gives you a link to the review page on your computer. Your answers save as you click. When you want email addresses for the people you said yes to, paste:

> Get work email for the people I said yes to in my latest Pudding run. It costs about US$0.03 a person, so raise that run's cap to cover it.

## A run costs about a dollar in lookups

- **Lookups: about US$1 for a first run**, paid to Treg. Our first runs spent US$0.70 to US$0.95, and a weekly follow-up US$0.40. Treg advertises US$1 of starting credit for new accounts. [Treg pricing](https://treg.to/pricing)
- **The cap is hard.** Pudding checks each lookup against what's left of the cap before sending it, and Treg can't charge a lookup more than Pudding allowed. It looks up the strongest people first, tells you if the cap left anything out, and never raises the cap by itself.
- **Work email: about US$0.03 a person**, on top. Thirty people is about US$1.
- **Your agent's usage is separate.** A run is one long session with your agent while it reads several hundred posts: about 250,000 to 410,000 tokens on Claude. On a Claude or ChatGPT subscription, that counts against your plan like any other session.
- **Your Treg balance is the outer limit.** Treg is prepaid and spends only what you've loaded. Keep a few dollars in it and leave automatic top-ups off.

## What it touches, and how to keep it safe

- **Your LinkedIn and X accounts: never.** Pudding doesn't sign in as you and sends nothing to anyone.
- **Treg and the data providers behind it** receive the searches, names and profile links Pudding looks up. [Which providers](#treg-and-where-the-data-comes-from).
- **Websites** are read directly from your computer: your own site, the job ads, and any website on an X author's profile when Pudding is working out who they are.
- **One private folder per run** holds the posts, names and your answers, readable only by you. Delete the folder to remove them.
- **Contacting people is your call.** Pudding reads public posts. Whether and how you may write to someone depends on the platforms' terms and the privacy law where you and they are.

The playbook tells your agent to treat every post as data, never as instructions. You make it safer still by starting it in an empty folder, approving only the commands listed above, and keeping the Treg balance small.

## Run it every week, while the problem is fresh

The best people to write to are the ones who posted this week. After your first run, paste this each Monday:

> Run Pudding again for `<my company URL>` as a follow-up to my latest run under `~/pudding-runs`, following "Following runs" in `docs/playbook.md`. Stay under US$1. Tell me who is new and open the review page.

A follow-up starts from last week's searches and your yes and no answers. It keeps the searches that found people, replaces the ones that didn't, reads what's been posted since the last run (at least the past week), and leaves out everyone it has already shown you. In our test it found 31 new people, 4 of them strong, in 14 minutes for US$0.40. We ran that test the same day as the first run, so a real week will differ.

Once you trust it, ask your agent to run that same prompt every Monday morning. Claude Code and Codex can both run a prompt on a schedule while your computer is on. A scheduled run has to be allowed to run Pudding's commands without asking you first, so run it by hand for a few weeks before you schedule it.

## We ran it on ourselves

We make a review tool for coding agents. One run found 60 people worth contacting in 19 minutes for US$0.89: 43 from LinkedIn posts, 5 from X and 12 from job ads. It graded 11 of them strong.

Five of the strong ones:

- A founder whose reviewers can't run every change by hand, and whose agents' own checks miss regressions.
- A chief executive whose agents write more code each week than any human team can check.
- A co-founder whose open pull requests grow faster than the team can review them.
- A chief technology officer whose output went up while review time didn't, and who now calls review the team's biggest constraint.
- A founder hiring someone to orchestrate agents and review their work.

**Then we checked it.** A second model saw only each person's role, employer and quote, with no grades. It would message 44 of the 60, including 9 of the 11 strong.

**Then we read the first few ourselves.** They were right.

**It works with more than one agent.** We gave Claude Sonnet and Codex the same brief:

| Agent | Worth contacting | Second model would message | Time | Lookups |
| --- | --- | --- | --- | --- |
| Claude Sonnet 5.5 | 60 | 44 | 19 minutes | US$0.89 |
| Codex (GPT-6.1) | 75 | 48 | 25 minutes | US$0.94 |

## How it finds and checks each person

1. **Your agent plans the searches** in your buyer's words, pairing a tool they already use with a phrase like "we switched" or "our renewal".
2. **It reads several hundred posts** and picks the people describing their own team's work, not giving advice or selling. It copies the exact sentence that shows it, and Pudding rejects any quote that isn't word for word in the post.
3. **Pudding confirms who they are and where they work now** against LinkedIn. An X author is matched to LinkedIn through the link on their profile, or through two things that tie the two accounts together. If your agent had to work someone out by name alone, the row says so.
4. **Pudding describes each employer**, with its size, industry and one-line description, so agencies and large companies are easy to spot. Your agent drops direct competitors and labels the rest.
5. **It reads job ads** from LinkedIn, Greenhouse, Ashby, Lever, Workday, SmartRecruiters and Workable. An ad that hands this work to a new hire tells you the team has the problem, so Pudding finds whoever owns that work there today. Those rows are marked as hiring signals.
6. **You decide.** Low-fit people, existing customers and anyone Pudding couldn't identify sit in their own sections, apart from the main list.
7. **It finds work email** for the people you said yes to, and only returns an address a second provider has confirmed.

The reason on each row is your agent's own sentence. Read the quote and follow the link before you write to anyone.

## Reference

### The shortlist file

Each run writes `shortlist.csv` in its folder. Every row has the person's name, role and company; the company's size, industry and web domain; their location, LinkedIn link and X handle; the quote, its source and date; the search that found them; the run date; and your answer. Filter on `fit` and `your_answer` before you import it, and match against your CRM on `profile_url`. After the email step, rows also carry the work email.

### Leaving out people you already know

Add `--suppress FILE` to the first run, with a plain list or a CRM export. A LinkedIn profile link leaves out that person. A company name or LinkedIn company link leaves out that company. A work email or web domain leaves out the company whose website is on that domain. Weekly follow-ups keep using the same list.

### Treg and where the data comes from

Pudding buys every lookup through Treg. Behind Treg, LinkedIn data comes from HarvestAPI, X data from AnyAPI and the X API, web search from Serper and Exa, and work email from AnyAPI and Hunter.

Your agent installs Treg with its own installer (`curl -fsSL https://treg.to/install.sh | sh`) and signs you in with `treg login`. If you already have a Treg team token, set `TREG_TOKEN` and `TREG_ORG` instead. Pudding sends the token only to `treg.to`, and it uses only a team with no provider keys of its own connected, so every lookup counts against the cap.

### Commands

Your agent runs these. [The playbook](docs/playbook.md) is its manual; you don't need to read it.

| Command | What it does |
| --- | --- |
| `connect` | Checks the Treg sign-in. Costs nothing. |
| `start URL` | Reads the site and creates the run folder. `--budget-usd` sets the spend cap, US$1 by default. `--previous DIR` makes it a follow-up. `--suppress FILE` leaves out people you already know. `--window-days N` changes how far back it reads, 45 days by default. |
| `check` | Validates the plan and the grades. |
| `search` | Runs the LinkedIn and X searches. |
| `sheet` | Writes the next batch of posts to read. `--jobs` for job ads. |
| `show ID…` | Prints posts or ads in full. |
| `verify` | Confirms identity and current role, and describes the employer. |
| `timeline @handle`, `web "query"` | Helps your agent place an X author: their recent posts, and a web search. |
| `spider` | Optional. Reads the replies under posts your agent has graded. |
| `jobs`, `contacts` | Finds job ads, then the person who owns the work. `--lookback-days N` changes how far back `jobs` reads, 90 days by default. |
| `shortlist` | Writes `shortlist.md` and `shortlist.csv`. |
| `review` | Starts the review page on your computer and prints its address. |
| `enrich` | Finds work email for your yes answers. |
| `budget USD` | Raises this run's spend cap. |
| `status` | Shows the counts and the spend. |

### Develop

```sh
python3 -m unittest discover -s tests
```

Standard library only. MIT licence. Built by [Enhance Labs](https://enhancelabs.ai).
