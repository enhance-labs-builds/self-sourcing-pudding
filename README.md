# Self-Sourcing Pudding

**Find leads who are talking about the problem you solve.**

When someone posts that their team needs two calls to get every new customer set up, you have a reason to look them up. We built Pudding for teams that use AI to find their next customers.

Start with your company website. Pudding drafts a brief you can edit. It describes who you want to find, what problem they’re working on, and what they might say about it. Once you approve the brief, you can run a search of public posts on LinkedIn and X whenever you want new leads. Each preview shows up to 20 people to review. An X author becomes eligible for the shortlist once you match them to a verified LinkedIn profile.

You decide who makes the shortlist. Each run writes its own CSV with the person’s current LinkedIn profile, the dated post, and the quote that made them a fit. Live runs can add a verified work email when one is available. On the next pass, Pudding skips people whose evidence you’ve already reviewed and can bring someone back when there’s new evidence.

## Try it with your own URL

The free walkthrough reads your public website to draft the brief. You’ll practise reviewing fictional candidates for **US$0**, without a Treg account. You’ll need **Python 3.11+** on **macOS or Linux**. If you want to see the CSV first, [run the offline demo](#see-a-sample-shortlist).

### With an AI agent

Paste this into an AI agent that can run commands on your computer. Replace `<my company URL>` with your website.

> Open https://github.com/enhance-labs-builds/self-sourcing-pudding and check that I have Python 3.11 or newer. Set up Pudding and start the free walkthrough with `<my company URL>`. Show me the draft brief and let me edit or approve it. Walk me through reviewing two fictional candidates and show me where the shortlist CSV is saved. Keep the run free.

### In Terminal

```sh
git clone https://github.com/enhance-labs-builds/self-sourcing-pudding.git
cd self-sourcing-pudding
bash install.sh --project runs/my-company
```

Paste your company URL when prompted. If the draft needs work, edit who owns the problem and add phrases they’d use in a post. After the review, Pudding prints the command for another pass with the same brief and votes.

You can also [download the tester ZIP](https://github.com/enhance-labs-builds/self-sourcing-pudding/releases/download/v0.1.0/self-sourcing-pudding-tester.zip), unzip it, and open `START HERE.txt`.

### See a sample shortlist

Clone the repo as above and run `python3 rig.py demo` from the repository folder. This runs offline and puts two fictional leads in `runs/demo/shortlist.csv`, with their profiles, source links, dates, quotes, and reasons for making the shortlist.

## Search LinkedIn and X for real leads

Use a live run to see what turns up in your market. Pudding uses Treg for search, role checks, and work email lookup. [Set up a Treg team with prepaid balance and an API token](docs/guide.md#try-a-capped-live-run), then run this from the repository folder where you installed Pudding:

```sh
.pudding/bin/pudding walk --project runs/my-company --live --budget-usd 0.50
```

This command caps total Treg spend for the run at **US$0.50**, shared across searches, role checks, and work email lookup. How many people you get to review depends on what they’ve posted, whose role you can verify, and the budget left.

After your first live review, open `runs/my-company/runs/live-preview/shortlist.csv`. Use the printed command for another pass with the same brief and votes. If a run is interrupted, use its continuation command to resume under the original cap.

## Go further

- [Read the guide](docs/guide.md#start-from-a-company-url) to import an existing brief, match an X author to a LinkedIn profile, check spend, or run a larger batch.
- [Bring your own records](docs/guide.md#bring-your-own-offline-records) to build a shortlist offline.
- [Browse example briefs](examples/) to see how to search for a competitor alongside the workflow it’s used for.
- If you open an issue, include your command, Python version, and redacted output. Keep live run folders private.
- Run `python3 -m unittest discover -s tests` to check changes locally.

Pudding is an independent client of the [hosted Treg API](https://treg.to/docs). Live use is subject to the [Treg terms](https://treg.to/terms) and applicable provider terms. The project is [MIT licensed](LICENSE).
