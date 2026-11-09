# Self-Sourcing Pudding

**Find leads already talking about the problem you solve.**

Self-Sourcing Pudding is an open-source lead discovery tool for teams that use AI to find their next customers. Start with your company website. Pudding drafts who to look for, what problem they’re working on, and what they might say about it. Edit or approve that brief, then search public posts on LinkedIn and X. Review the evidence, current roles, and verified work emails when available.

[See the Ramp sample CSV](examples/ramp-demo/shortlist.csv) · [Try it with your URL](#try-it-with-your-own-url) · [Example briefs](#example-briefs) · [Work email lookup](#find-and-verify-work-emails)

## See why a lead made the list

The demo uses Ramp Procurement as the product in the brief. It looks for teams trying to fix how they request and approve purchases. One fictional candidate, procurement lead Nia Alder, writes:

> I run procurement intake at Juniper Vale. Purchase approvals kept getting stuck between Slack and a spreadsheet, so we piloted one request form with finance and IT last week.

Nia owns the workflow and is actively changing it. The sample shortlist shows the profile, dated post, and quote behind that decision, plus her fictional work email marked `example`. All people, employers, posts, and addresses in the sample CSV are fictional.

## Try it with your own URL

The free walkthrough reads your public website to draft the brief. You’ll practise reviewing fictional candidates for **US$0**, without a Treg account. You’ll need **Python 3.11+** on **macOS or Linux**.

### With an AI agent

Paste this into an AI agent that can run commands on your computer. Replace `<my company URL>` with your website.

> Open https://github.com/enhance-labs-builds/self-sourcing-pudding and check that I have Python 3.11 or newer. Set up Pudding and start the free walkthrough with `<my company URL>`. Show me the draft brief and let me edit or approve it. Walk me through reviewing two fictional candidates and show me where the shortlist CSV is saved. Keep the run free.

### In Terminal

```sh
git clone https://github.com/enhance-labs-builds/self-sourcing-pudding.git
cd self-sourcing-pudding
bash install.sh --project runs/my-company
```

Paste your company URL when prompted. When the site leaves gaps, Pudding asks who owns the work, how they talk about it, and which companies or alternatives matter. Review the queries before approving. After the review, Pudding prints the command for another pass with the same brief and votes.

You can also download `self-sourcing-pudding-tester.zip` from [GitHub Releases](https://github.com/enhance-labs-builds/self-sourcing-pudding/releases), unzip it, and open `START HERE.txt`.

### Run the offline demo

Clone the repo as above and run `python3 rig.py demo` from the repository folder. This uses the Ramp brief and recreates the [sample CSV](examples/ramp-demo/shortlist.csv) at `runs/demo/shortlist.csv` without any network access.

## Example briefs

These examples use public product information. Open a brief to see who you might look for and what evidence would make someone a fit.

| Brief | What to look for |
| --- | --- |
| [Ramp](examples/company-briefs/ramp.toml) | Finance and procurement teams fixing purchase intake and approvals |
| [Stripe](examples/company-briefs/stripe.toml) | Software teams implementing usage metering and billing |
| [Harvey](examples/company-briefs/harvey.toml) | Legal teams standardizing contract reviews and redlines |

## Search LinkedIn and X for real leads

Run a live search whenever you want fresh leads. Pudding uses Treg for searches, role checks, and work email lookup. New Treg accounts can start with **US$1 in credit**. Usage draws from your Treg balance. [Treg pricing](https://treg.to/pricing) · [Set up Treg and run a live search](docs/guide.md#run-a-live-search)

Pudding starts with public posts about the workflow or a competitor in your brief. It checks a promising LinkedIn thread for comments and a promising X thread for replies, then looks for coworkers when a post connects the work to a verified employer. A short reply can move up for review when the person's company fits your brief. Shortlisting still takes evidence from that person. [How Pudding follows posts and employers](docs/guide.md#follow-posts-and-employers)

Choose your spend limit and use `--target` to set the maximum number of candidates to review. A candidate makes the shortlist after you confirm firsthand evidence. When a search turns up few good fits, tune the brief with words practitioners use to describe their work and run it again.

After your first live review, open `runs/my-company/runs/live-preview/shortlist.csv`. Pudding prints a command for another pass with the same brief and votes. The next pass skips people whose evidence you’ve already reviewed.

## Find and verify work emails

The live walkthrough looks up eligible candidates’ work emails through Treg before you review them. Pudding matches each address to the person’s current employer domain and checks it with an independent email verifier. It shows verified addresses on review cards and adds them to `work_email` in the shortlist CSV. When a lookup fails or the spend limit is reached, the address stays blank and `work_email_status` records the reason. [Live setup and email options](docs/guide.md#work-email-lookup) · [Lookup code](work_email.py)

## Go further

- [Read the guide](docs/guide.md#start-from-a-company-url) to import an existing brief, match an X author to a LinkedIn profile, check spend, or run a larger batch.
- [Bring your own records](docs/guide.md#bring-your-own-offline-records) to build a shortlist offline.
- If you open an issue, include your command, Python version, and redacted output. Keep live run folders private.
- Run `python3 -m unittest discover -s tests` to check changes locally.

Pudding is an independent client of the [hosted Treg API](https://treg.to/docs). Live use is subject to the [Treg terms](https://treg.to/terms) and applicable provider terms. The project is [MIT licensed](LICENSE).
