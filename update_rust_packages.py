# /// script
# dependencies = [
#   "click",
# ]
# ///
from __future__ import annotations

import subprocess
import tomllib
from pathlib import Path
import sys

import click

# Variables for the lazy
# You can add them manually here instead of passing via CLI
packages = []


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
    "--workdir",
    default=".",
    help="""
    Working directory where the package files will be updates
    """,
    type=click.Path(exists=True, file_okay=False, path_type=Path),
)
@click.option(
    "--bump-version",
    help="""
    Version to bump to
    """,
    default=None,
)
def main(packages_file, workdir: Path, bump_version: str | None):
    global packages

    if packages_file == "-":
        if not sys.stdin.isatty():
            packages = []
            for pkg in sys.stdin:
                packages.append(pkg.rstrip())
    else:
        with Path(packages_file).open("r") as f:
            packages = f.read().rstrip().split("\n")

    rust2rpm_args = ["-s"]
    if bump_version:
        rust2rpm_args.append(f"@{bump_version}")

    # First pass prepare the main packages
    for pkg in packages:
        pkg_rust2rpm_args = rust2rpm_args.copy()
        pkg_dir = workdir / pkg
        rust2rpm_toml = pkg_dir / "rust2rpm.toml"
        if rust2rpm_toml.exists():
            with rust2rpm_toml.open("rb") as f:
                rust2rpm_data = tomllib.load(f)
                if (
                    rust2rpm_package := rust2rpm_data.get("package")
                ) and "cargo-toml-patch-comments" in rust2rpm_package:
                    pkg_rust2rpm_args.append("-r")
        ret = subprocess.run(["rust2rpm", *pkg_rust2rpm_args], cwd=pkg_dir)
        if not ret.returncode:
            click.secho(f"rust2rpm update on {pkg}: Successful", fg="green")
        else:
            click.secho(f"rust2rpm update on {pkg}: failed", fg="red")


if __name__ == "__main__":
    main()
