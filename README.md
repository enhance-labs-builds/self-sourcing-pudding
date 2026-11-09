# Self-Sourcing Pudding

**Find leads already talking about the problem you solve.**

Self-Sourcing Pudding is an open-source lead discovery tool for teams that use AI to find their next customers. Start with your company website. Pudding drafts who to look for, what problem they’re working on, and what they might say about it. Edit or approve that brief, then search public posts on LinkedIn and X for people to review.

[See the sample CSV](examples/preview-environments/shortlist.csv) · [Try it with your URL](#try-it-with-your-own-url) · [Run a live search](#search-linkedin-and-x-for-real-leads)

## See why a lead made the list

Say you sell a tool that helps teams test changes before they ship. In the fictional demo, Nia Alder, a platform engineer, writes:

> I maintain the preview deploy for our app team. Builds fail after a database reset, and I spent Friday restoring previews so the team could review changes.

That gives you a reason to look up Nia and something specific to talk about. You decide who makes the shortlist. Each run saves a CSV with the person’s profile, the dated post, and the quote behind your decision. A later run can bring them back when there’s new evidence.

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

Paste your company URL when prompted. If the draft needs work, edit who owns the problem and add phrases they’d use in a post. After the review, Pudding prints the command for another pass with the same brief and votes.

You can also [download the tester ZIP](https://github.com/enhance-labs-builds/self-sourcing-pudding/releases/download/v0.1.0/self-sourcing-pudding-tester.zip), unzip it, and open `START HERE.txt`.

### Run the offline demo

Clone the repo as above and run `python3 rig.py demo` from the repository folder. This recreates the [sample CSV](examples/preview-environments/shortlist.csv) at `runs/demo/shortlist.csv` without any network access.

## Search LinkedIn and X for real leads

Run a live search whenever you want fresh leads. Pudding uses Treg for searches, role checks, and work email lookup. [Treg](https://treg.to/) offers **US$1 in starter credit** once per new verified account, with no card required. Usage draws from your Treg balance. [Set up Treg and run a live search](docs/guide.md#run-a-live-search).

Pudding starts with public posts about the workflow or a competitor in your brief. It reads the replies and comments, checks who wrote them and where they work, then looks for colleagues posting about the same work. A short reply from someone on a team already doing the work can move up for review. Shortlisting still takes evidence from that person. [How Pudding follows posts and employers](docs/guide.md#follow-posts-and-employers)

Choose the most you want to spend and use `--target` to set how many people you want to review. You may get fewer when the evidence is thin. Pudding can include verified work emails when available.

After your first live review, open `runs/my-company/runs/live-preview/shortlist.csv`. Pudding prints a command for another pass with the same brief and votes. The next pass skips people whose evidence you’ve already reviewed.

## Go further

- [Read the guide](docs/guide.md#start-from-a-company-url) to import an existing brief, match an X author to a LinkedIn profile, check spend, or run a larger batch.
- [Bring your own records](docs/guide.md#bring-your-own-offline-records) to build a shortlist offline.
- [Browse example briefs](examples/) to see how to search for a competitor alongside the workflow it’s used for.
- If you open an issue, include your command, Python version, and redacted output. Keep live run folders private.
- Run `python3 -m unittest discover -s tests` to check changes locally.

Pudding is an independent client of the [hosted Treg API](https://treg.to/docs). Live use is subject to the [Treg terms](https://treg.to/terms) and applicable provider terms. The project is [MIT licensed](LICENSE).
