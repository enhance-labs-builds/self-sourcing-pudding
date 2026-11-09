"""The first run, from a pasted URL to saved review feedback."""

import os
import shlex
import shutil
import subprocess
import sys
from argparse import BooleanOptionalAction, Namespace
from datetime import date
from pathlib import Path
from uuid import uuid4

import pilot
from treg_adapter import PendingCall, dollars, micro_dollars
from url_seed import profile_channel, public_url


def setup_command(commands):
    walk = commands.add_parser("walk", help="start a guided run from a company URL")
    walk.add_argument("url", nargs="?", help="company website or social profile")
    walk.add_argument("--website", help="company website for a social-profile URL")
    walk.add_argument("--project", type=Path, help="folder to save or continue the walkthrough")
    walk.add_argument("--run", help="choose a new run name to try a revised brief in the same project")
    walk.add_argument("--live", action="store_true", help="use Treg for a real preview")
    walk.add_argument("--spider", action=BooleanOptionalAction, help="follow threads and employers (on for live runs)")
    walk.add_argument("--budget-usd", help="total cap for a live run")
    walk.add_argument("--target", type=int, metavar="1–500", help="maximum people to review (default 20)")


def example_corpus(brief):
    today = date.today().isoformat()
    term = brief["signals"][0]
    people = [
        {"id": "example-nia", "name": "Nia Alder", "role": brief["target_roles"][0], "company": "Siltglass Studio",
         "profile_url": "https://profiles.example/nia-alder", "role_checked_on": today,
         "example_email": "nia@siltglass.example"},
        {"id": "example-devon", "name": "Devon Flint", "role": brief["target_roles"][-1], "company": "Mothsignal Software",
         "profile_url": "https://profiles.example/devon-flint", "role_checked_on": today},
        {"id": "example-val", "name": "Val Quill", "role": "Product Marketing Lead", "company": "BranchDock",
         "profile_url": "https://profiles.example/val-quill", "role_checked_on": today},
    ]
    examples = [
        ("linkedin", "nia", "Nia Alder", f"We run {term} for new accounts. The handoff still takes our team two calls per account, so we're testing a guided setup for the next cohort."),
        ("x", "nia", "@nia-example", f"Our team is measuring how long {term} takes before and after our guided setup pilot."),
        ("linkedin", "devon", "Devon Flint", f"I own {term} at Mothsignal. We've shipped a self-serve path and are comparing completion rates with the previous manual process."),
        ("x", "val", "@val-example", f"We just launched a product for {term}. Try our new feature."),
        ("x", None, "@unknown-example", f"Has anyone tried changing how they do {term}?"),
    ]
    posts = []
    for i, (channel, person, author, text) in enumerate(examples, 1):
        row = {"id": f"example-{i}", "channel": channel, "kind": "post", "author": author,
               "url": f"https://{channel}.example/posts/{i}", "published_on": today, "text": text}
        if person:
            row["person_id"] = "example-" + person
        posts.append(row)
    return {"schema_version": 1, "as_of": today, "people": people, "observations": posts}


def open_editor(path):
    command = os.environ.get("VISUAL") or os.environ.get("EDITOR") or shutil.which("nano") or shutil.which("vi")
    if not command:
        print(f"Edit {path} in your editor, then return here.")
        input("Press Enter after saving the brief. ")
        return
    if subprocess.run([*shlex.split(command), str(path)], check=False).returncode:
        print(f"The editor exited with an error. You can also edit {path} directly.")


def review_brief(project, state, rig):
    path = project / "brief.toml"
    while True:
        brief = None
        try:
            brief = rig.read_brief(path)
            rig.show_plan(brief)
        except ValueError as error:
            print(f"Brief needs an edit: {error}")
        choice = input("\n[a] Approve brief   [e] Edit brief   [q] Save and exit: ").strip().lower()
        if choice == "q":
            return False
        if choice == "e":
            open_editor(path)
        elif choice == "a" and brief is not None:
            try:
                pilot.approve(Namespace(project=project, yes=True), state, rig, show=False)
            except ValueError as error:
                print(error)
                continue
            return True


def walk_command(project, name, budget, *, live=False, spider=None, target=None):
    root = Path(__file__).resolve().parent
    installed = root / ".pudding/bin/pudding"
    command = [str(installed)] if installed.is_file() else [sys.executable, str(root / "rig.py")]
    command += ["walk", "--project", str(project.resolve()), "--run", name]
    if live:
        command.append("--live")
        if budget:
            command += ["--budget-usd", budget]
        if spider is not None:
            command.append("--spider" if spider else "--no-spider")
    if target is not None:
        command += ["--target", str(target)]
    return shlex.join(command)


def run(args, rig):
    if args.budget_usd and not args.live:
        raise ValueError("Use --live with --budget-usd, or omit the cap for the example.")
    if args.spider and not args.live:
        raise ValueError("Use --spider with --live.")
    if args.target is not None and not 1 <= args.target <= 500:
        raise ValueError("Use --target from 1 to 500.")
    budget = dollars(micro_dollars(args.budget_usd)) if args.budget_usd else None
    mode = "live" if args.live else "example"
    name = args.run or f"{mode}-preview"
    project = args.project or Path("runs") / f"pudding-{uuid4().hex[:8]}"
    print("\nSelf-Sourcing Pudding")
    print("Live preview · LinkedIn, X and work email" if args.live
          else "Example preview · public site for the brief · fictional candidates · US$0")
    print(f"Project: {project.resolve()}")
    if not (project / "state.json").exists():
        url = public_url(args.url or input("\nCompany URL: ").strip())
        website = args.website
        if profile_channel(url) and not website:
            website = input("Company website: ").strip()
        pilot.start_project(Namespace(url=url, website=website, project=project, starter=None,
                                      target=args.target or 20), rig, show=False)
    elif args.url or args.website:
        raise ValueError("This project already has a URL. Use a new project to start from another company.")

    with pilot.locked_project(project, rig) as state:
        out = pilot.run_path(project, name)
        summary_path = out / "preview.json"
        summary = rig.read_json(summary_path) if summary_path.exists() else None
        if summary and summary["mode"] != mode:
            raise ValueError("Choose a different --run name when switching between example and live previews.")
        spider = args.spider if args.spider is not None else args.live
        target = args.target
        ledger_path = out / "treg-run.json"
        if args.live and ledger_path.exists():
            saved = rig.read_json(ledger_path)["plan"]
            budget = budget or dollars(saved["budget_micro"])
            if target is None:
                target = saved["brief"]["limits"]["shortlist_size"]
            if args.spider is None:
                spider = bool(saved.get("spider"))
        if not out.exists():
            print("\n1. Review your sourcing brief")
            if not review_brief(project, state, rig):
                continue_command = walk_command(project, name, budget, live=args.live, spider=spider, target=target)
                print(f"Draft saved. Continue with:\n  {continue_command}")
                return
        if args.live and budget is None:
            budget = dollars(micro_dollars(input("Maximum spend for this run in USD › ").strip()))
        continue_command = walk_command(project, name, budget, live=args.live, spider=spider, target=target)
        if not summary or summary.get("pending_spend_usd"):
            if out.exists() and not args.live:
                raise ValueError("This run name already exists. Choose a fresh --run name.")
            if out.exists() and not ledger_path.exists():
                raise ValueError("This run has no Treg record to resume. Choose a fresh --run name.")
            print("\n2. Resume the preview" if out.exists() else "\n2. Build the preview")
            if args.live:
                print(f"If the run is interrupted, continue with:\n  {continue_command}", flush=True)
            preview = Namespace(project=project, run=name, budget_usd=budget, corpus=None, identities=None,
                                batch=False, resume=out.exists(), searches=None, profiles=None, pages=1,
                                results_per_search=None, no_email=False, spider=spider, target=target)
            example = None if args.live else example_corpus(rig.read_brief(project / "brief.toml"))
            try:
                pilot.run_preview(preview, state, rig, example=example)
            except PendingCall:
                print(f"Resume this run with:\n  {continue_command}", flush=True)
                raise
            summary = rig.read_json(summary_path)
        print("\n3. Review candidates")
        pilot.review(Namespace(project=project, run=name, votes=None), state, rig)
        print(f"\nYour shortlist is ready at {out.resolve() / 'shortlist.csv'}")
        if summary.get("pending_spend_usd"):
            print(f"Resume the pending work email in this run with:\n  {continue_command}")
        else:
            next_index = 2
            while pilot.run_path(project, f"{mode}-pass-{next_index}").exists():
                next_index += 1
            next_command = walk_command(project, f"{mode}-pass-{next_index}", budget, live=args.live,
                                        spider=spider, target=target)
            print(f"Run this URL again with your saved brief and feedback:\n  {next_command}")
