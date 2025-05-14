# /// script
# dependencies = [
#   "click",
# ]
# ///
from __future__ import annotations

import re
import subprocess
from pathlib import Path
import sys

import click

SOURCE_RE = re.compile(r"Source\d+: (.*#/)?(?P<file>.+)")

# Variables for the lazy
# You can add them manually here instead of passing via CLI
packages = []
workdir = "."
downstream_dir = None
rsync_filters = []
rsync_flags = ("-a",)
branch = "update-{pkg}-{version}"
commit_msg = "Update to version {version}{rhbz_msg}"
rhbz_msg = "; Fixes RHBZ#{bug}"
fas_id = None


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
    default=workdir,
    help="""
    Working directory where the updated pacakges are
    """,
    type=click.Path(exists=True, file_okay=False, path_type=Path),
)
@click.option(
    "--downstream-dir",
    default=downstream_dir,
    help="""
    Downstream directory where the packages are fedpkg cloned to
    """,
    type=click.Path(exists=True, file_okay=False, path_type=Path),
)
@click.option(
    "--filter",
    default=rsync_filters,
    help="""
    Rsync filters used when copying the files
    """,
    multiple=True,
)
@click.option(
    "--rsync-flags",
    default=rsync_flags,
    help="""
    Additional rsync flags to pass
    """,
    type=str,
    multiple=True,
)
@click.option(
    "--branch",
    default=branch,
    help="""
    Branch where to upload the updates to.
    """,
)
@click.option(
    "--commit-msg",
    default=commit_msg,
    help="""
    Commit and changelog message to use.
    """,
)
@click.option(
    "--fas-id",
    default=fas_id,
    help="""
    FAS_ID, using `whoami` if not defined
    """,
)
def main(
    packages_file,
    workdir: Path,
    downstream_dir: Path,
    filter: list[str],
    rsync_flags: list[str],
    branch: str,
    commit_msg: str,
    fas_id: str | None,
):
    global packages

    pacakges_from_stdin = False
    if packages_file == "-":
        if not sys.stdin.isatty():
            click.secho("BEWARE: All new sources are uploaded.", fg="red")
            pacakges_from_stdin = True
            packages = []
            for pkg in sys.stdin:
                packages.append(pkg.rstrip())
    else:
        with Path(packages_file).open("r") as f:
            packages = f.read().rstrip().split("\n")

    if not downstream_dir:
        click.secho("Please specify the downstream-dir", err=True, fg="red")
        raise SystemExit(1)

    filter_args = []
    for f in filter:
        filter_args.append("--filter")
        filter_args.append(f)
    if "-a" not in rsync_flags:
        raise ValueError("-a must be passed to the rsync-flags")
    rsync_args = [*rsync_flags, *filter_args]

    if not fas_id:
        res = subprocess.run(
            ["whoami"],
            capture_output=True,
            text=True,
            check=True,
        )
        fas_id = res.stdout.rstrip()

    def process_pkg(pkg: str):
        pkg_dir = workdir / pkg
        if not pkg_dir.exists():
            click.secho(f"{pkg_dir} does not exist", fg="orange")
            return
        click.echo(f"Processing {pkg}.")
        pkg_spec = f"{pkg}.spec"
        downstream_pkg_dir = downstream_dir / pkg
        if not downstream_pkg_dir.exists():
            subprocess.run(
                ["fedpkg", "clone", pkg],
                cwd=downstream_dir,
                check=True,
            )
        subprocess.run(
            ["fedpkg", "fork"],
            cwd=downstream_pkg_dir,
            check=True,
        )
        subprocess.run(
            ["fedpkg", "switch-branch", "rawhide"],
            cwd=downstream_pkg_dir,
            check=True,
        )
        subprocess.run(
            ["fedpkg", "pull"],
            cwd=downstream_pkg_dir,
            check=True,
        )
        subprocess.run(
            ["rsync", *rsync_args, f"{pkg_dir}/", f"{downstream_pkg_dir}/"],
            check=True,
        )
        res = subprocess.run(
            ["rpmspec", "--srpm", "-q", r"--queryformat=%{version}", pkg_spec],
            capture_output=True,
            text=True,
            cwd=downstream_pkg_dir,
            check=True,
        )
        version = res.stdout.rstrip()
        pkg_rhbz_msg = ""
        pkg_commit_msg = commit_msg.format(
            pkg=pkg,
            version=version,
            rhbz_msg=pkg_rhbz_msg,
        )
        pkg_branch = branch.format(
            pkg=pkg,
            version=version,
        )
        subprocess.run(
            ["rpmdev-bumpspec", pkg_spec, "-c", commit_msg],
            cwd=downstream_pkg_dir,
            check=True,
        )
        subprocess.run(
            ["spectool", "-S", "-g", pkg_spec],
            cwd=downstream_pkg_dir,
            check=True,
        )
        res = subprocess.run(
            ["spectool", "-S", "-l", pkg_spec],
            capture_output=True,
            text=True,
            cwd=downstream_pkg_dir,
            check=True,
        )
        new_sources = []
        for src_txt in res.stdout.rstrip().splitlines():
            match = SOURCE_RE.match(src_txt)
            if not match:
                click.secho(f"Unexpected source url format: {src_txt}", fg="red")
                new_sources = None
                break
            file_name = match.group("file")
            source_file = downstream_pkg_dir / file_name
            if not source_file.exists() or not source_file.is_file():
                click.secho(f"Source file is not available: {file_name}")
                new_sources = None
                break
            new_sources.append(file_name)

        if not new_sources:
            click.secho(f"Skipping {pkg}", fg="grey")
            return

        new_sources_msg = (
            f"Uploading the following sources for {pkg} to fedora:\n"
            + "\n".join(new_sources)
        )
        # Cannot make a prompt when using the stdin to read the packages
        # https://github.com/pallets/click/issues/1370
        if not pacakges_from_stdin and not click.confirm(new_sources_msg):
            click.secho(f"Skipping {pkg}", fg="grey")
            return

        subprocess.run(
            ["fedpkg", "new-sources", *new_sources],
            cwd=downstream_pkg_dir,
            check=True,
        )
        subprocess.run(
            ["git", "add", "-A"],
            cwd=downstream_pkg_dir,
            check=True,
        )
        subprocess.run(
            ["git", "checkout", "-b", pkg_branch],
            cwd=downstream_pkg_dir,
            check=True,
        )
        res = subprocess.run(
            ["git", "commit", "-m", pkg_commit_msg],
            cwd=downstream_pkg_dir,
        )
        if res.returncode:
            click.secho("Nothing commited", fg="gray")
            return
        subprocess.run(["git", "push", fas_id], cwd=downstream_pkg_dir, check=True)

    for pkg in packages:
        try:
            process_pkg(pkg)
        except (SystemExit, subprocess.CalledProcessError):
            click.secho(f"Failed to process {pkg}", fg="red")


if __name__ == "__main__":
    main()
