"""Build the tester bundle from a fixed list of public project files."""

import argparse
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo


ROOT = Path(__file__).resolve().parent
FOLDER = "Self-Sourcing-Pudding"
FILES = (
    "rig.py", "pilot.py", "treg_adapter.py", "url_seed.py", "work_email.py",
    "walkthrough.py", "README.md", "LICENSE", "docs/guide.md", "START HERE.txt", "install.sh",
    "examples/company-briefs/ramp.toml", "examples/company-briefs/stripe.toml", "examples/company-briefs/harvey.toml",
    "examples/preview-environments/brief.toml", "examples/preview-environments/corpus.json",
    "examples/preview-environments/decisions.json", "examples/preview-environments/shortlist.csv",
)


def package(output):
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        for name in FILES:
            archive.write(ROOT / name, f"{FOLDER}/{name}")
        launcher = ZipInfo(f"{FOLDER}/Start Pudding.command")
        launcher.create_system = 3
        launcher.external_attr = 0o100755 << 16
        archive.writestr(launcher, (ROOT / "install.sh").read_bytes(), ZIP_DEFLATED)


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("output", type=Path, help="path to the tester ZIP")
    package(cli.parse_args().output)
