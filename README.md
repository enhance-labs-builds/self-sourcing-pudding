<p align="center">
  <img src="docs/pudding.png" alt="A felt pudding holding a pair of binoculars" width="180">
</p>

<h1 align="center">Self-Sourcing Pudding</h1>

<p align="center"><strong>Find the people already talking about the problem you solve.</strong></p>

<p align="center">
  <a href="https://github.com/enhance-labs-builds/self-sourcing-pudding/actions/workflows/ci.yml"><img src="https://github.com/enhance-labs-builds/self-sourcing-pudding/actions/workflows/ci.yml/badge.svg" alt="CI status"></a>
  <img src="https://img.shields.io/badge/python-3.11%2B-blue" alt="Python 3.11 or later">
  <img src="https://img.shields.io/badge/dependencies-none-brightgreen" alt="No dependencies">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-lightgrey" alt="MIT licence"></a>
</p>

Pudding turns a company URL into a shortlist of people who have the problem you solve and have said so in public. Your coding agent searches LinkedIn, X and job ads, reads what people wrote and grades the evidence. Pudding confirms each person's identity and current role, enforces your spend cap, and rejects any quote that isn't in the original post. You finish on a page on your own computer, answering yes or no to each person.

Pudding runs locally on the Python standard library and costs about US$1 a run. It doesn't sign in as you and it sends nothing to anyone.

**On our own product: [60 people worth contacting, 19 minutes, US$0.89](#results).**

| Fit | Person | Current role | Evidence |
| --- | --- | --- | --- |
| strong | Priya Rowan | Procurement Operations Manager, Ashmere Hospitality | “Our approvals contract is up for renewal in March and we're evaluating alternatives.” |
| worth a look · hiring signal | Idris Vale | Head of Procurement, Hollis Bay Health | “You will choose and roll out our first purchase-approvals system” |

A hiring signal comes from a job ad that shows a team has the problem, and the row names whoever owns that work today. These people are fictional. The [sample shortlist](examples/shortlist.md) and [CSV](examples/shortlist.csv) come from the same code a real run uses.

![The review page: one person, their role and employer, the quote, and Yes, No and Maybe buttons](docs/review-page.jpg)

## Quick start

You need:

- **A Mac or Linux computer with a coding agent**, such as Claude Code, Codex or Cursor. Desktop apps work. A chat window alone can't run commands.
- **A new, empty folder called `pudding`**, opened as your agent's working folder. Your agent will read posts written by strangers, and the empty folder keeps your other files out of reach.
- **A [Treg](https://treg.to) account.** Treg sells Pudding its lookups. Your agent sets it up with you: you sign in through your browser and copy no keys.
- **About US$1 and half an hour.**

Replace the part in angle brackets and paste this into your agent:

```text
Clone https://github.com/enhance-labs-builds/self-sourcing-pudding (skip this if I already have it) and check I have Python 3.11 or later. Help me set up Treg. Then follow `docs/playbook.md` to find leads for `<my company URL>`. Keep each run in its own dated folder under `~/pudding-runs` and stay under US$1. When the shortlist is ready, open the review page and tell me the funnel and the spend.
```

If your site leaves the buyer unclear, name them in one more sentence: "Our buyer is the head of finance at a 50 to 500 person company who still approves purchases by email."

Keep your agent set to ask before each command. You will approve four things in order: the download, a Python check, the Treg install and sign-in, and commands starting `python3 pudding.py`. Stop and ask why if it requests anything else.

After 20 to 25 minutes your agent gives you a link to the review page. Press **Y**, **N** or **M** for each person, and each answer saves as you press. To get work email for your yes answers:

```text
Get work email for the people I said yes to in my latest Pudding run. It costs about US$0.03 a person, so raise that run's cap to cover it.
```

Pudding works best when your buyers write in public, in English, about their work, and name their tools. B2B software sold to founders, engineers, operators and team leads fits. Test runs found 60 people for a code review tool, 25 for an AI-native CRM and 15 for AI support agents. Buyers who rarely post produce shorter lists.

## Cost

| Item | Cost | Detail |
| --- | --- | --- |
| First run | about US$1 | Paid to Treg. Our first runs spent US$0.70 to US$0.95. |
| Weekly follow-up | about US$0.40 | Paid to Treg. |
| Work email | about US$0.03 a person | On top of the run. Thirty people cost about US$1. |
| Your agent | 250,000 to 410,000 tokens on Claude | Counts against your plan like any other long session. |

Treg is prepaid and advertises US$1 of starting credit for new accounts ([pricing](https://treg.to/pricing)). Your Treg balance is the outer limit on spend, so keep a few dollars in it and leave automatic top-ups off.

## Guarantees

Pudding's code enforces these. They hold whichever agent runs it.

| Guarantee | How Pudding enforces it |
| --- | --- |
| **Spend stays under the cap** | Pudding reserves each lookup's worst-case cost under a lock before sending it, and tells Treg the most it may charge. It looks up the strongest people first and reports anything the cap left out. A reported charge above the reservation stops the run. |
| **The cap never rises by itself** | Only the `budget` command raises it. Your agent can run that command, so the playbook forbids it unasked and your ask-before-each-command setting lets you refuse it. |
| **Each lookup bills once** | Every lookup carries an idempotency key and a saved receipt, so reruns and crash recovery reuse what you paid for. An unsettled charge blocks new spending until Pudding can account for it. |
| **Quotes are real** | `check` rejects any quote that doesn't appear word for word in the captured post or ad. |
| **Identity is checked** | LinkedIn confirms each person's current role on the day of the run. An X author needs a LinkedIn link on their profile, or two checkable ties to one LinkedIn profile, one of them about the person. Rows your agent placed by name alone say so. |
| **Email addresses are confirmed** | Pudding accepts one address at the employer's own domain, and a second provider must confirm the mailbox. |
| **Your token goes to Treg alone** | Pudding sends it only to `treg.to`, follows no redirects, and stores only a hash. |
| **Run data stays private** | Each run gets its own folder that only your account can read, with a `.gitignore` that excludes everything in it. Delete the folder to remove the data. |
| **Web requests stay on the public internet** | Pudding fetches HTTPS only, refuses private network addresses at connection time, and limits each page to 512 KB and 20 seconds. |
| **Strangers' text stays inert** | Pudding removes terminal escape codes and invisible characters before your agent reads anything, and labels every sheet as data. It neutralises spreadsheet formulas in the CSV and links and HTML in `shortlist.md`. |
| **The review page stays on your computer** | It listens on `127.0.0.1` only, refuses other hostnames and origins, and loads nothing from elsewhere. |

### What leaves your computer

| Recipient | What it receives |
| --- | --- |
| Treg and [its data providers](#treg-and-data-sources) | The searches, names and profile links Pudding looks up. |
| Your agent's model provider | The posts, names and quotes your agent reads. |
| Websites | A request from your computer for your own site, each job ad, and any site linked from an X author's profile. |
| Your LinkedIn and X accounts | Nothing. Pudding never signs in to them. |

### Risks you still own

**Prompt injection.** A stranger's post can contain text written to manipulate an AI. Pudding labels and cleans that text, and no filter can stop a model from being fooled. Three controls limit the damage: start your agent in an empty folder, approve each command yourself, and keep your Treg balance small.

**Outreach.** Pudding reads public posts and contacts nobody. Platform terms and the privacy law where you and your prospects live, such as GDPR, decide whether and how you may write to someone. Read the quote and follow the source link before you do. The reason on each row is your agent's own sentence.

See [SECURITY.md](SECURITY.md) to report a vulnerability.

## How a run works

1. **Plan.** Your agent writes searches in your buyer's words, pairing a tool they use with a phrase like "we switched" or "our renewal".
2. **Read.** It reads several hundred posts and keeps people describing their own team's work, dropping advice and sales pitches. It copies the sentence that shows it, and Pudding checks that sentence against the post.
3. **Verify.** Pudding confirms who each person is and where they work now.
4. **Profile the employer.** Pudding records each employer's size, industry and one-line description. Your agent drops direct competitors and labels agencies and large companies.
5. **Read job ads** from LinkedIn, Greenhouse, Ashby, Lever, Workday, SmartRecruiters and Workable. When an ad hands this work to a new hire, Pudding finds whoever owns it today and marks the row as a hiring signal.
6. **Review.** You answer yes, no or maybe. Low-fit people, existing customers and anyone Pudding couldn't identify sit in separate sections.
7. **Enrich.** Pudding finds work email for your yes answers.

Pudding reads posts from the last 45 days and job ads from the last 90. A job ad with no published date stays in and shows `no date` on your agent's sheet. On our reference run, the typical post was 11 days old and every job ad was under four weeks old.

## Weekly runs

The best people to write to posted this week. Paste this each Monday:

```text
Run Pudding again for `<my company URL>` as a follow-up to my latest run under `~/pudding-runs`, following "Following runs" in `docs/playbook.md`. Stay under US$1. Tell me who is new and open the review page.
```

A follow-up starts from last week's searches and your answers. It keeps the searches that found people, replaces the ones that didn't, reads everything posted since the last run (at least the past week), and leaves out everyone you've seen. In our test it found 31 new people, 4 of them strong, in 14 minutes for US$0.40. We ran that test the same day as the first run, so expect a real week to differ.

Claude Code and Codex can run this prompt on a schedule while your computer is on. A scheduled run executes Pudding's commands without asking you, so run it by hand for a few weeks first.

## Results

We make a review tool for coding agents and pointed Pudding at our own market. One run found 60 people worth contacting in 19 minutes for US$0.89: 43 from LinkedIn posts, 5 from X and 12 from job ads. It graded 11 of them strong, including:

- A founder whose reviewers can't run every change by hand, and whose agents' own checks miss regressions.
- A chief executive whose agents write more code each week than any human team can check.
- A co-founder whose open pull requests grow faster than the team can review them.
- A chief technology officer whose output went up while review time didn't, and who now calls review the team's biggest constraint.
- A founder hiring someone to orchestrate agents and review their work.

A second model then saw each person's role, employer and quote, with no grades. It would message 44 of the 60, including 9 of the 11 strong. We read the first few ourselves and agreed with the grades.

| Agent | Worth contacting | Second model would message | Time | Lookups |
| --- | --- | --- | --- | --- |
| Claude Sonnet 5.5 | 60 | 44 | 19 minutes | US$0.89 |
| Codex (GPT-6.1) | 75 | 48 | 25 minutes | US$0.94 |

## Reference

### Output

Each run writes `shortlist.md` and `shortlist.csv` to its folder. Each CSV row holds the person's name, role, company, company size, industry, web domain, location, LinkedIn link and X handle; the quote, its source and date; the search that found them; the run date; and your answer. The email step adds work email. Filter on `fit` and `your_answer`, and match against your CRM on `profile_url`.

### Suppression lists

Add `--suppress FILE` to the first run to leave out people you already know. The file can be a plain list or a CRM export, and weekly follow-ups keep using it.

| Entry | Leaves out |
| --- | --- |
| LinkedIn profile link | That person |
| Company name or LinkedIn company link | That company |
| Work email or web domain | The company whose website is on that domain |

### Treg and data sources

Pudding buys every lookup through Treg. Behind Treg, HarvestAPI supplies LinkedIn data, AnyAPI and the X API supply X data, Serper and Exa supply web search, and AnyAPI and Hunter supply work email.

Your agent installs Treg with its own installer (`curl -fsSL https://treg.to/install.sh | sh`) and signs you in with `treg login`. With a Treg team token, set `TREG_TOKEN` and `TREG_ORG` instead. Pudding refuses a team with its own provider keys connected, so every lookup counts against the cap. One read-only X connection is allowed.

### Commands

Your agent runs these from [the playbook](docs/playbook.md).

| Command | Purpose |
| --- | --- |
| `connect` | Check the Treg sign-in. Free. |
| `start URL` | Read the site and create the run folder. Options: `--budget-usd` (default 1.00), `--previous DIR`, `--suppress FILE`, `--window-days N` (default 45). |
| `check` | Validate the plan and grades. |
| `search` | Run the LinkedIn and X searches. |
| `sheet` | Write the next batch of posts to read. `--jobs` for job ads. |
| `show ID…` | Print posts or ads in full. |
| `verify` | Confirm identity and current role, and describe the employer. |
| `timeline @handle`, `web "query"` | Help place an X author: their recent posts, and a web search. |
| `spider` | Optional. Read replies under graded posts. |
| `jobs`, `contacts` | Find job ads, then the person who owns the work. `jobs --lookback-days N` (default 90). |
| `shortlist` | Write `shortlist.md` and `shortlist.csv`. |
| `review` | Start the review page and print its address. |
| `enrich` | Find work email for your yes answers. |
| `budget USD` | Raise this run's cap. |
| `status` | Show the counts and spend. |

## Development

```sh
python3 -m unittest discover -s tests
```

No dependencies, and the tests never touch the network. Read [CONTRIBUTING.md](CONTRIBUTING.md) before opening a pull request. MIT licence. Built by [Enhance Labs](https://enhancelabs.ai).
