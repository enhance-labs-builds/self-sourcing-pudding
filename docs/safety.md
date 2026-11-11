# Safety

Your agent reads posts written by strangers and spends real money through Pudding.

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

## What leaves your computer

| Recipient | What it receives |
| --- | --- |
| Treg and [its data providers](reference.md#treg-and-data-sources) | The searches, names and profile links Pudding looks up. |
| Your agent's model provider | The posts, names and quotes your agent reads. |
| Websites | A request from your computer for your own site, each job ad, and any site linked from an X author's profile. |
| Your LinkedIn and X accounts | Nothing. Pudding never signs in to them. |

## Risks you still own

**Prompt injection.** A stranger's post can contain text written to manipulate an AI. Pudding labels and cleans that text, and no filter can stop a model from being fooled. Three controls limit the damage: start your agent in an empty folder, approve each command yourself, and keep your Treg balance small.

**Outreach.** Pudding reads public posts and contacts nobody. Platform terms and the privacy law where you and your prospects live, such as GDPR, decide whether and how you may write to someone. Read the quote and follow the source link before you do. The reason on each row is your agent's own sentence.

See [SECURITY.md](../SECURITY.md) to report a vulnerability.
