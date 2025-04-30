# /// script
# dependencies = [
#   "click",
#   "copr",
#   "fedrq",
# ]
# ///
from __future__ import annotations

import contextlib
import io
import subprocess
from pathlib import Path
import sys

import click
from fedrq.cli import main as fedrq_cli
from copr.v3 import Client

# Variables for the lazy
# You can add them manually here instead of passing via CLI
packages = []
branch = "rawhide"
skip = []
project = None
background = True

client = Client.create_from_config_file()


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
    "--branch",
    help="""
    Working directory containing the `.packit.yaml`.
    """,
    default=branch,
)
@click.option(
    "--skip",
    help="""
    Skip the dependencies.
    """,
    multiple=True,
    default=skip,
)
@click.option(
    "--project",
    help="""
    Copr project as {owner}/{project} format.
    """,
    default=project,
)
@click.option(
    "--background/--not-background",
    help="""
    Whether to submit the builds as background builds.
    """,
    default=background,
)
def main(packages_file, branch: str, skip: list[str], project: str, background: bool):
    global packages, client

    if not project:
        raise ValueError("No project was provided")

    owner, project = project.split("/")

    if packages_file == "-":
        if not sys.stdin.isatty():
            packages = []
            for pkg in sys.stdin:
                packages.append(pkg.rstrip())
    else:
        with Path(packages_file).open("r") as f:
            packages = f.read().rstrip().split("\n")

    for pkg in packages:
        with contextlib.redirect_stdout(io.StringIO()) as f:
            fedrq_cli(["wrsrc", pkg, "-F=source", f"-b={branch}"])
        out = f.getvalue()
        out: str
        rev_deps = out.splitlines()
        for dep in rev_deps:
            if dep == pkg or dep in skip:
                continue
            client.build_proxy.create_from_distgit(
                ownername=owner,
                projectname=project,
                packagename=dep,
                buildopts={
                    "background": background,
                }
            )


if __name__ == "__main__":
    main()
