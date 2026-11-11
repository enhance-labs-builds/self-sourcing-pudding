# Reference

## Output

Each run writes `shortlist.md` and `shortlist.csv` to its folder. Each CSV row holds the person's name, role, company, company size, industry, web domain, location, LinkedIn link and X handle; the quote, its source and date; the search that found them; the run date; and your answer. The email step adds work email. Filter on `fit` and `your_answer`, and match against your CRM on `profile_url`.

## Suppression lists

Add `--suppress FILE` to the first run to leave out people you already know. The file can be a plain list or a CRM export, and weekly follow-ups keep using it.

| Entry | Leaves out |
| --- | --- |
| LinkedIn profile link | That person |
| Company name or LinkedIn company link | That company |
| Work email or web domain | The company whose website is on that domain |

## Treg and data sources

Pudding buys every lookup through Treg. Behind Treg, HarvestAPI supplies LinkedIn data, AnyAPI and the X API supply X data, Serper and Exa supply web search, and AnyAPI and Hunter supply work email.

Your agent installs Treg with its own installer (`curl -fsSL https://treg.to/install.sh | sh`) and signs you in with `treg login`. With a Treg team token, set `TREG_TOKEN` and `TREG_ORG` instead. Pudding refuses a team with its own provider keys connected, so every lookup counts against the cap. One read-only X connection is allowed.

## Commands

Your agent runs these from [the playbook](playbook.md).

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
