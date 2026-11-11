# Contributing

You need Python 3.11 or later. Pudding has no dependencies, so there is nothing to install.

```sh
git clone https://github.com/enhance-labs-builds/self-sourcing-pudding
cd self-sourcing-pudding
python3 -m unittest discover -s tests
```

## Rules for a pull request

- **Standard library only.** A third-party package needs a strong case, because every Pudding user runs this code beside their Treg sign-in.
- **Tests stay offline and free.** Replace the network with a stand-in, as the existing tests do. A test must never reach Treg or a live website.
- **Add a test for each behaviour you change.** Check that it fails without your change.
- **Fictional people only.** Fixtures, examples and screenshots use invented people and `.example` domains. Open a pull request with a real name or a real post and we will ask you to remove it from the history.
- **Keep the cap intact.** A new paid lookup goes through `ledger` in `pudding.py`, with a worst-case price in `treg.PER_CALL`.
- **Clean text from the web.** Anything printed or written for an agent passes through `terminal_text`, and sheets carry `DATA_NOTE`.
- **Regenerate the sample** with `python3 examples/make_sample.py` if you change the shortlist format. A test compares it to the committed copy.
- **Update `docs/playbook.md`** if you change a command. Agents follow it to the letter.

Report security problems through [SECURITY.md](SECURITY.md), not in an issue.
