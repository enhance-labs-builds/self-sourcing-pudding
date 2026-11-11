# Security

## Report a vulnerability

Use [private vulnerability reporting](https://github.com/enhance-labs-builds/self-sourcing-pudding/security/advisories/new). Please keep the details out of public issues until we have shipped a fix. Include the commit you tested, the steps to reproduce it, and what an attacker gains.

We support the latest commit on `main`.

## In scope

Pudding's agent reads text written by strangers and spends real money, so these reports matter most:

- A way to spend past a run's cap, or to charge a lookup twice.
- A way for web content to reach a private network address, or to reach the Treg token.
- A quote that passes `check` without appearing in its source.
- Text from a post, profile, job ad or website that survives into an agent sheet, `shortlist.md`, `shortlist.csv` or the review page in an executable or hidden form.
- A way for another website or local page to read or change the review page.
- Run data readable by another account on the same computer.

## Out of scope

- A model obeying an instruction it read in a post, when Pudding delivered that text labelled as data with hidden characters removed. No filter can rule this out. [docs/safety.md](docs/safety.md) lists the controls that limit the damage. A new way to get past Pudding's labelling or filtering is in scope.
- Bugs in Treg or its data providers. Report those to Treg.
- Anything that needs an attacker to already control your user account.
