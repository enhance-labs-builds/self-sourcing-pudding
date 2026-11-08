# Self-Sourcing Pudding

**Turn a company URL into a shortlist backed by real posts.**

Pudding drafts an editable sourcing brief from a company site. Approve who you want to find and what they'd be talking about, then search LinkedIn and X for people doing that work. Review the evidence and save your votes for the next run.

| Start with | Get back |
| --- | --- |
| A public company URL | A draft brief with the target roles, workflow, and search phrases |
| An approved brief | Up to 20 people to review, with dated posts, LinkedIn profiles, and verified work emails when available |
| A yay or nay | A saved decision. Future runs skip evidence you've already reviewed and can surface someone again when there's new evidence. |

## Quick start

You need **Python 3.11+** on **macOS or Linux**. Clone the repo or download the [tester ZIP](https://github.com/enhance-labs-builds/self-sourcing-pudding/releases/download/v0.1.0/self-sourcing-pudding-tester.zip).

```sh
git clone https://github.com/enhance-labs-builds/self-sourcing-pudding.git
cd self-sourcing-pudding
python3 rig.py demo
```

The demo runs offline and produces a two-person fictional shortlist at `runs/demo/shortlist.csv`. One person describes a deployment failure in their own words and shows up in both the LinkedIn and X fixtures. The shortlist keeps the evidence with their profile.

## Use your own URL

From the checkout, run the guided setup and paste your company URL. In the tester ZIP, follow `START HERE.txt`.

```sh
bash install.sh --project runs/my-company
```

Edit or approve the brief and vote on a few fictional candidates. The walkthrough reads your public site to draft the brief and costs **US$0**. If the draft needs more context, fill in the workflow, who owns it, and the phrases they use. Pudding prints the command for another pass with the same project. The brief and votes stay in that project folder.

## Live LinkedIn and X

Use your own [Treg team and token](https://treg.to/docs) with prepaid balance and no connected provider keys or custom tools. In the terminal where you installed Pudding, set:

```sh
export TREG_ORG='your-team-slug'
printf 'Treg API token: '
read -rs TREG_TOKEN
printf '\n'
export TREG_TOKEN

.pudding/bin/pudding walk --project runs/my-company --live --budget-usd 0.50
```

The cap covers searches, role checks, and work email lookups. Preview size depends on the evidence, budget, and available provider results. X authors go into the research queue until you can link them to a verified LinkedIn profile. Keep live run folders private.

After review, use the printed command for a new pass, or add `--run live-pass-2` to the command above. Each new run has its own cap.

If the run is interrupted, repeat the continuation command with the same project, run name, cap, and token. Pudding reuses settled calls and can recover a pending response using [Treg's replay contract](https://treg.to/skill.md#retrying-without-paying-twice). If it can't safely recover the result, it pauses the run.

Pudding is an independent client of the hosted Treg API. Treg provides access to upstream services, and live use is subject to the [Treg terms](https://treg.to/terms) and the applicable provider terms.

## Go further

- [Guide](docs/guide.md) covers editing a brief, qualifying candidates, running a larger batch, and using your own offline records.
- [Example briefs](examples/) show how to search for a problem, a competitor plus a workflow, or evidence in customer stories.
- For bug reports, include the command, Python version, and any redacted error output. Use fictional records to share a reproducible example.
- Run `python3 -m unittest discover -s tests` to check changes locally.

MIT licensed. See [LICENSE](LICENSE).
