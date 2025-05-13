# /// script
# dependencies = [
#   "ruamel.yaml",
#   "fedrq",
#   "click",
# ]
# ///
from __future__ import annotations

import contextlib
import dataclasses
import io
import re
import subprocess
from pathlib import Path
import sys

import click
from fedrq.cli import main as fedrq_cli
from ruamel.yaml import YAML

# Constants
PACKIT_YAML_REGEX = re.compile(r"\.?packit.ya?ml")

# Variables for the lazy
# You can add them manually here instead of passing via CLI
packages = []
branch = "rawhide"
skip = []


@dataclasses.dataclass
class PkgTemplate:
    _name: str
    paths: list[str] = dataclasses.field(default_factory=list, init=False)
    specfile_path: str = dataclasses.field(init=False)
    downstream_package_name: str = dataclasses.field(init=False)

    def __post_init__(self):
        self.paths = [self._name]
        self.specfile_path = f"{self._name}.spec"
        self.downstream_package_name = self._name

    def to_dict(self) -> dict:
        return {
            field.name: getattr(self, field.name)
            for field in dataclasses.fields(self)
            if not field.name.startswith("_")
        }


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
    Working directory containing the `.packit.yaml`.
    """,
    type=click.Path(exists=True, file_okay=False, path_type=Path),
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
def main(packages_file, workdir: Path, branch: str, skip: list[str]):
    global packages

    for packit_file in workdir.iterdir():
        if PACKIT_YAML_REGEX.match(packit_file.name):
            break
    else:
        raise FileNotFoundError("There is no .packit.yaml found")

    if packages_file == "-":
        if not sys.stdin.isatty():
            packages = []
            for pkg in sys.stdin:
                packages.append(pkg.rstrip())
    else:
        with Path(packages_file).open("r") as f:
            packages = f.read().rstrip().split("\n")

    packit_yaml = YAML(typ="rt")
    packit_data = packit_yaml.load(packit_file)

    for pkg in packages:
        with contextlib.redirect_stdout(io.StringIO()) as f:
            fedrq_cli(["wrsrc", pkg, "-F=source", f"-b={branch}"])
        out = f.getvalue()
        out: str
        rev_deps = out.splitlines()
        for dep in rev_deps:
            if dep == pkg or dep in skip:
                continue
            # Add the appropriate `packages` field if missing
            if dep not in packit_data["packages"]:
                packit_data["packages"][dep] = PkgTemplate(dep).to_dict()
            # Add the source from rawhide if not already present
            dep_data = packit_data["packages"][dep]
            dep_root = workdir / dep_data["paths"][0]
            specfile_path = dep_root / dep_data["specfile_path"]
            if not specfile_path.exists():
                subprocess.call(["fedpkg", "clone", dep], cwd=workdir)
                subprocess.call(["rm", "-rf", f"{dep}/.git"], cwd=workdir)

    packit_yaml.dump(packit_data, packit_file)


if __name__ == "__main__":
    main()
