# /// script
# dependencies = [
#   "click",
#   "requests",
# ]
# ///

import json
from pathlib import Path
import sys

import click
import requests

# Constants
MAINTAINERS_URL = "https://src.fedoraproject.org/extras/pagure_bz.json"

# Variables for the lazy
# You can add
packages = []

# Get all package maintainers
response = requests.get(MAINTAINERS_URL)
all_package_maintainers = response.json()["rpms"]


@click.command()
@click.option(
    "--packages-file",
    default="-",
    help="""
    A file with a list of packages for which to get the maintainers for.
    By default STDIN is used unless it is not open, in which case the `packages`
    attribute of this file is used.
    """,
)
@click.option(
    "--format",
    default="merged",
    type=click.Choice(["merged", "json"]),
    help="""\b
    The output format:
     - merged: all maintainers combined
     - json: JSON format same as the pagure_bz.json file
    """,
)
def main(packages_file, format: str):
    global packages, all_package_maintainers
    if packages_file == "-":
        if not sys.stdin.isatty():
            packages = []
            for pkg in sys.stdin:
                packages.append(pkg.rstrip())
    else:
        with Path(packages_file).open("r") as f:
            packages = f.read().rstrip().split("\n")

    pkg_maintainers = {
        key: val for key, val in all_package_maintainers.items() if key in packages
    }

    match format:
        case "json":
            click.echo(json.dumps(pkg_maintainers))
        case "merged":
            merged_maintainers = sorted(
                set(x for maintainers in pkg_maintainers.values() for x in maintainers)
            )
            for maintainer in merged_maintainers:
                click.echo(maintainer)
        case _:
            raise NotImplementedError


if __name__ == "__main__":
    main()
