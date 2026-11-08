"""The first run, from a pasted URL to saved review feedback."""

import os
import shlex
import shutil
import subprocess
from argparse import Namespace
from datetime import date
from pathlib import Path
from uuid import uuid4

import pilot
from treg_adapter import dollars, micro_dollars
from url_seed import profile_channel, public_url


def setup_command(commands):
    walk = commands.add_parser("walk", help="start a guided run from a company URL")
    walk.add_argument("url", nargs="?", help="company website or social profile")
    walk.add_argument("--website", help="company website for a social-profile URL")
    walk.add_argument("--project", type=Path, help="folder to save or continue the walkthrough")
    walk.add_argument("--run", help="choose a new run name to try a revised brief in the same project")
    walk.add_argument("--live", action="store_true", help="use Treg for a real preview")
    walk.add_argument("--budget-usd", help="total cap for a live run")


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


def run(args, rig):
    if args.live and not args.budget_usd:
        raise ValueError("Give the live preview a cap with --budget-usd.")
    if args.budget_usd and not args.live:
        raise ValueError("Use --live with --budget-usd, or omit the cap for the example.")
    budget = dollars(micro_dollars(args.budget_usd)) if args.live else None
    mode = "live" if args.live else "example"
    name = args.run or f"{mode}-preview"
    project = args.project or Path("runs") / f"pudding-{uuid4().hex[:8]}"
    print("\nSelf-Sourcing Pudding")
    print(f"Live preview · LinkedIn, X and work email · maximum US${budget}" if args.live
          else "Example preview · public site for the brief · fictional candidates · US$0")
    print(f"Project: {project.resolve()}")
    if not (project / "state.json").exists():
        url = public_url(args.url or input("\nCompany URL: ").strip())
        website = args.website
        if profile_channel(url) and not website:
            website = input("Company website: ").strip()
        pilot.start_project(Namespace(url=url, website=website, project=project, starter=None, target=100), rig, show=False)
    elif args.url or args.website:
        raise ValueError("This project already has a URL. Use a new project to start from another company.")

    with pilot.locked_project(project, rig) as state:
        out = pilot.run_path(project, name)
        if (out / "preview.json").exists() and rig.read_json(out / "preview.json")["mode"] != mode:
            raise ValueError("Choose a different --run name when switching between example and live previews.")
        if not (out / "preview.json").exists():
            print("\n1. Review your sourcing brief")
            if not review_brief(project, state, rig):
                print(f"Draft saved. Continue with pudding walk --project {shlex.quote(str(project))}." if not args.live
                      else f"Draft saved. Continue with pudding walk --live --budget-usd {budget} --project {shlex.quote(str(project))}.")
                return
            print("\n2. Build the preview")
            preview = Namespace(project=project, run=name, budget_usd=budget, corpus=None, identities=None,
                                batch=False, resume=out.exists(), searches=None, profiles=None, pages=1,
                                results_per_search=None, no_email=False)
            example = None if args.live else example_corpus(rig.read_brief(project / "brief.toml"))
            pilot.run_preview(preview, state, rig, example=example)
        print("\n3. Review candidates")
        pilot.review(Namespace(project=project, run=name, votes=None), state, rig)
        print(f"\nYour shortlist is ready at {out.resolve() / 'shortlist.csv'}")
