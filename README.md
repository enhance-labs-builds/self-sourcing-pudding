# Self-Sourcing Pudding

**Find leads already talking about the problem you solve.**

Self-Sourcing Pudding is an open-source tool for finding sales leads from public LinkedIn and X posts. Start with the page that explains the product you sell. Define who you want to find and what evidence would make them a fit, then review the results. Pudding saves a CSV with the people you approve, their current roles, a dated quote from each person, and verified work emails when available.

[See 10 fictional Ramp leads](examples/ramp-demo/shortlist.csv) · [Try your URL for free](#try-it-with-your-own-url) · [Find real leads with Treg](#search-linkedin-and-x-for-real-leads)

## See why a lead made the list

The demo uses Ramp Procurement as the product in the brief. It looks for teams trying to fix how they request and approve purchases. One fictional candidate, procurement lead Nia Alder, writes:

> I run procurement intake at Juniper Vale. Purchase approvals kept getting stuck between Slack and a spreadsheet, so we piloted one request form with finance and IT last week.

Nia owns the workflow and is actively changing it. The sample contains ten approved leads, five with a work email marked `example`. All people, employers, posts, and addresses in the sample CSV are fictional.

## Try it with your own URL

The free walkthrough reads your product page and lets you practice reviewing fictional candidates for **US$0**. It needs internet access to read the page. Use **Python 3.11+** on **macOS or Linux**. The offline Ramp demo works without internet access.

### With an AI agent

Paste this into an AI agent that can run commands on your computer in an interactive terminal. Replace `<my product URL>` with your website.

> Open https://github.com/enhance-labs-builds/self-sourcing-pudding and check that I have macOS or Linux and Python 3.11 or newer. In the checkout, run `bash install.sh --project runs/my-company` and enter `<my product URL>`. If Pudding asks who owns the work or what they say about it, suggest answers from the product page and check them with me. Let me edit or approve the brief. Help me shortlist one fictional candidate and show me their role, quote, and reason in the CSV. If you can’t reach the product page, run `python3 rig.py demo` and show me the Ramp shortlist. Keep the run free.

### In Terminal

Download `self-sourcing-pudding-tester.zip`, unzip it, and open `START HERE.txt`. If you use Git, the commands below start the same walkthrough. [GitHub Releases](https://github.com/enhance-labs-builds/self-sourcing-pudding/releases)

```sh
git clone https://github.com/enhance-labs-builds/self-sourcing-pudding.git
cd self-sourcing-pudding
bash install.sh --project runs/my-company
```

Paste your product URL when prompted. Pudding reads the page title and description. For most products, you’ll answer who owns the work, how they talk about it, and which companies or alternatives matter. An AI agent can suggest answers from the page. Review the queries before approving.

To put someone in the CSV, vote yay and answer yes when asked whether to add them to the shortlist. Keep the quote that shows what they are working on and write one line about why it fits. Finish the review or press `q` to save and quit. Open `runs/my-company/runs/example-preview/shortlist.csv`. Pudding prints the command for another pass with the same brief and votes.

### Run the offline demo

From the repository or extracted ZIP, run `python3 rig.py demo`. It recreates the ten sample rows at `runs/demo/shortlist.csv`. To run it again, choose a new folder with `--out runs/demo-2`.

## Example briefs

These examples use public product information. Open a brief to see who you might look for and what evidence would make someone a fit.

| Brief | What to look for |
| --- | --- |
| [Ramp](examples/company-briefs/ramp.toml) | Finance and procurement teams fixing purchase intake and approvals |
| [Stripe](examples/company-briefs/stripe.toml) | Software teams implementing usage metering and billing |
| [Harvey](examples/company-briefs/harvey.toml) | Legal teams standardizing contract reviews and redlines |

## Search LinkedIn and X for real leads

Run a live search whenever you want fresh leads. Pudding uses Treg for searches, role checks, and work email lookup. New Treg accounts can start with **US$1 in credit**. Usage draws from your Treg balance. [Treg pricing](https://treg.to/pricing) · [Set up Treg and run a live search](docs/guide.md#run-a-live-search)

If you’re working with an AI agent, use this after the free walkthrough:

> Reuse my brief in `runs/my-company`. Help me set up Treg and enter the API key in my terminal. Show me the search plan and wait for me to choose a spend limit before running it. Show me each candidate’s evidence and ask who I want to shortlist.

Pudding starts with public posts about the workflow or a competitor in your brief. It checks a promising LinkedIn thread for comments and a promising X thread for replies, then looks for coworkers when a post connects the work to a verified employer. A short reply can move up for review when the person's company fits your brief. Shortlisting still takes evidence from that person. [How Pudding follows posts and employers](docs/guide.md#follow-posts-and-employers)

Choose your spend limit and use `--target` to set the maximum number of candidates to review. The limit covers searches, role checks, and email verification. Some calls use credit even if nobody qualifies. When a search turns up few good fits, tune the brief with words practitioners use to describe their work and run it again.

After your first live review, open `runs/my-company/runs/live-preview/shortlist.csv`. Pudding prints a command for another pass with the same brief and votes. Someone can return with new evidence. The next review shows only the sources you haven’t seen.

When you use the CSV for outreach, check the date and quote for signs of active work. Use `profile_url` to match people against your CRM and check contact history and suppression there. For an email import, filter to `work_email_status=verified`.

## Find and verify work emails

The live walkthrough looks up eligible candidates’ work emails through Treg before you review them. Pudding matches each address to the person’s current employer domain and checks it with an independent email verifier. It shows verified addresses on review cards and adds them to `work_email` in the shortlist CSV. When a lookup fails or the spend limit is reached, the address stays blank and `work_email_status` records the reason. [Live setup and email options](docs/guide.md#work-email-lookup) · [Lookup code](work_email.py)

## Go further

- [Read the guide](docs/guide.md#start-from-a-company-url) to import an existing brief, match an X author to a LinkedIn profile, check spend, or run a larger batch.
- [Bring your own records](docs/guide.md#bring-your-own-offline-records) to build a shortlist offline.
- If you open an issue, include your command, Python version, and redacted output. Keep live run folders private.
- Run `python3 -m unittest discover -s tests` to check changes locally.

Pudding is an independent client of the [hosted Treg API](https://treg.to/docs). Live use is subject to the [Treg terms](https://treg.to/terms) and applicable provider terms. The project is [MIT licensed](LICENSE).
