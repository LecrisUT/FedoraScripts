# /// script
# dependencies = [
#   "copr",
#   "bugzilla",
#   "specfile",
#   "requests",
# ]
# ///

"""
Create bugzilla bugs for failing copr project builds.

This is primarily built to help create blocking bugs for a change proposal.
"""

from __future__ import annotations

import functools
import json
import os
import subprocess
from configparser import ConfigParser
from json import JSONDecodeError
from pathlib import Path

from copr.v3 import Client
import bugzilla
import requests
import requests.auth
from specfile import Specfile
from specfile.tags import Tag, Comments, Comment

# User defined variables
update_cahed_bugs: bool = True
branch: str = "rawhide"
packages: list[str] = []
change_slug: str | None = "CMake_ninja_default"
copr_project: str | None = "lecris/cmake-ninja"
change_proposal: str | None = "CMake: Use ninja generator by default"

title: str = r"{package}: FTBFS with change proposal {change_proposal}"
body: str = r"""
Dear package maintainer,

This is an automated bug created due to a FTBFS when rebuilding this package for the change proposal {change_proposal}.

The rebuild is being tracked in https://copr.fedorainfracloud.org/coprs/{copr_owner}/{copr_project}/package/{package}.

See https://fedoraproject.org/wiki/Changes/{change_slug} for more information on how to make the package compatible.

More specifically, make sure you are using standard %cmake_* macros. If you find that there are hard dependencies on
the generator even after such transition, please ping me for closer investigation.

You can check the build locally following the instructions in the change proposal, or submit your build to the tracking
copr project.

Let me know if you encounter any issues, or need any other help.
"""
PR_title: str | None = r"{branch}: Fix FTBFS for CMake ninja generator"
PR_message: str | None = r"""
This is an automated PR trying to unblock {change_proposal}

For a long-term solution see about upstreaming the necessary changes as recommended in
https://fedoraproject.org/wiki/Changes/{change_slug}.

This PR is rebuilt with the change proposal at:
https://copr.fedorainfracloud.org/coprs/{copr_owner}/{copr_project}/build/{copr_build.id}.
Please check the status of that build before considering to merge this PR.

More up-to-date builds may be available at:
https://copr.fedorainfracloud.org/coprs/{copr_owner}/{copr_project}/package/{package}
"""
blocks_bgz: int | None = 2376112

copr_client = Client.create_from_config_file()
bzapi = bugzilla.Bugzilla("bugzilla.redhat.com")

ftbfs_title = r"{package}: FTBFS in Fedora rawhide/f43"

distgit_workdir: Path = Path() / "dist-git"
distgit_branch: str | None = "cmake/ninja"
delete_retired: bool = True
try_fix: bool = True
submit_pr: bool = True
commit_msg: str | None = "Allow to build with ninja generator"

RETIRED_URL = "https://src.fedoraproject.org/rpms/{pkg}/raw/{branch}/f/dead.package"

assert title
assert body

if not bzapi.logged_in:
    raise ValueError("Invalid API key in ~/.config/python-bugzilla/bugzillarc ?")

copr_owner, copr_project = copr_project.split("/")

if not packages:
    if not copr_project:
        raise ValueError("No packages specified")

    for pkg in copr_client.package_proxy.get_list(
        ownername=copr_owner,
        projectname=copr_project,
        with_latest_build=True,
    ):
        if pkg.builds["latest"]["state"] != "failed":
            continue
        packages.append(pkg.name)

# Read/Write cache of the presence of the bugzilla bugs
cache_file = Path("create_bugzilla_bugs_cache.json")
cache_file.touch()
with cache_file.open("r") as f:
    try:
        cache_file_data = json.load(f)
    except JSONDecodeError:
        cache_file_data = None
if not cache_file_data:
    cache_file_data = {}
assert isinstance(cache_file_data, dict)
cache_data = cache_file_data.setdefault(
    title.format(
        package="{package}",
        change_proposal=change_proposal,
    ),
    {},
)

bug_state = {
    "NEW": [],
    "ASSIGNED": [],
    "CLOSED": [],
}


def cache_bug(pkg: str, bug: bugzilla.base.Bug) -> None:
    global cache_data, cache_file_data, cache_file

    cache_data.setdefault(pkg, {})
    cache_data[pkg].update(
        {
            "id": bug.id,
            "status": bug.status if hasattr(bug, "status") else None,
            "depends": bug.depends_on if hasattr(bug, "depends_on") else [],
            "assigned_to": bug.assigned_to if hasattr(bug, "assigned_to") else None,
        }
    )

    # Refine status
    if cache_data[pkg]["status"] == "NEW":
        ftbfs_bugs = bzapi.query(
            bzapi.build_query(
                product="Fedora",
                component=pkg,
                short_desc=ftbfs_title.format(package=pkg),
            )
        )
        if cache_data[pkg]["depends"]:
            cache_data[pkg]["status"] = "NEW (blocked)"
        elif ftbfs_bugs:
            cache_data[pkg]["status"] = "NEW (FTBFS)"
        elif cache_data[pkg]["assigned_to"] == "extras-orphan@fedoraproject.org":
            cache_data[pkg]["status"] = "NEW (Orphan)"
        elif cache_data[pkg].get("PR_link"):
            cache_data[pkg]["status"] = "NEW (PR submitted)"

    if cache_data[pkg]["status"] == "CLOSED":
        response = requests.get(RETIRED_URL.format(pkg=pkg, branch=branch))
        if response.status_code == 200:
            cache_data[pkg]["status"] = "CLOSED (Retired)"
            if delete_retired:
                copr_client.package_proxy.delete(
                    ownername=copr_owner,
                    projectname=copr_project,
                    packagename=pkg,
                )

    with cache_file.open("w") as f:
        json.dump(cache_file_data, f)


def check_bug_state(pkg: str) -> None:
    global cache_data, bug_state

    # Record the current package to the bug_state dict
    bug_state.setdefault(cache_data[pkg]["status"], []).append(pkg)

    # Rebuild if issue was closed. The initial filter should not be adding
    # the package to the list if the package was not failing.
    if cache_data[pkg]["status"] == "CLOSED":
        copr_client.build_proxy.create_from_distgit(
            ownername=copr_owner,
            projectname=copr_project,
            packagename=pkg,
            committish=branch,
            buildopts={
                "background": True,
            },
        )
    elif try_fix and cache_data[pkg]["status"] == "NEW":
        try:
            prepare_distgit(pkg)
        except Exception as exc:
            print(f"Warn: Could not prepare distgit for package '{pkg}':\n{exc}")
            return
        if cache_data[pkg].get("failed_fix"):
            print(f"Warn: Package '{pkg}' failed the auto-fix")
            return
        if not cache_data[pkg].get("fixed"):
            try:
                try_rebase(pkg)
                specfile = get_specfile(pkg)
                patch_pkg(pkg, specfile)
                commit_patch(pkg)
            except Exception as exc:
                print(f"Warn: Could not fix specfile for package '{pkg}':\n{exc}")
                cache_data[pkg]["failed_fix"] = True
                with cache_file.open("w") as f:
                    json.dump(cache_file_data, f)
                return
        cache_data[pkg]["fixed"] = True
        with cache_file.open("w") as f:
            json.dump(cache_file_data, f)
        if submit_pr and pagure_token():
            try:
                pr_link = submit_patch(pkg)
            except Exception as exc:
                print(f"Failed to submit patch for package '{pkg}':\n{exc}")
                return
            cache_data[pkg]["PR_link"] = pr_link
            cache_data[pkg]["status"] = "NEW (PR submitted)"
            with cache_file.open("w") as f:
                json.dump(cache_file_data, f)


@functools.cache
def fasid() -> str:
    if (fedora_upn := Path.home() / ".fedora.upn").exists():
        return fedora_upn.read_text().strip()
    return os.getlogin()

@functools.cache
def pagure_token() -> str | None:
    fedpkg_conf = Path.home() / ".config/rpkg/fedpkg.conf"
    if not fedpkg_conf.exists():
        return None
    config = ConfigParser()
    config.read(fedpkg_conf)
    return config["fedpkg.distgit"]["token"]


def prepare_distgit(pkg: str) -> None:
    distgit_path = distgit_workdir / pkg
    remote_branch = f"{fasid()}/{distgit_branch}"
    if not distgit_path.exists():
        distgit_workdir.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["fedpkg", "clone", pkg],
            check=True,
            cwd=distgit_workdir,
        )
    has_fork = subprocess.run(
        ["git", "ls-remote", "-q", fasid()],
        check=False,
        cwd=distgit_path,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if has_fork.returncode != 0:
        subprocess.run(
            ["fedpkg", "fork"],
            check=True,
            cwd=distgit_path,
        )
    subprocess.run(
        ["git", "fetch", "origin"],
        check=True,
        cwd=distgit_path,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    subprocess.run(
        ["git", "fetch", fasid()],
        check=True,
        cwd=distgit_path,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    local_branch_exists = subprocess.run(
        ["git", "rev-parse", "--verify", distgit_branch],
        check=False,
        cwd=distgit_path,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if local_branch_exists.returncode == 0:
        subprocess.run(
            ["git", "checkout", distgit_branch],
            check=True,
            cwd=distgit_path,
        )
    else:
        remote_branch_exists = subprocess.run(
            ["git", "rev-parse", "--verify", remote_branch],
            check=False,
            cwd=distgit_path,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if remote_branch_exists.returncode == 0:
            subprocess.run(
                ["git", "switch", "-c", distgit_branch, remote_branch],
                check=True,
                cwd=distgit_path,
            )
        else:
            subprocess.run(
                ["git", "switch", "-c", distgit_branch, f"origin/{branch}"],
                check=True,
                cwd=distgit_path,
            )

def try_rebase(pkg: str) -> None:
    distgit_path = distgit_workdir / pkg
    rebase = subprocess.run(
        ["git", "rebase", f"origin/{branch}"],
        check=False,
        cwd=distgit_path,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if rebase.returncode != 0:
        subprocess.run(
            ["git", "rebase", "--abort"],
            check=True,
            cwd=distgit_path,
        )
        raise RuntimeError(f"Failed to rebase '{pkg}'")

def commit_patch(pkg: str) -> None:
    global cache_data

    bug_id = cache_data[pkg]["id"]

    distgit_path = distgit_workdir / pkg
    subprocess.run(
        ["git", "commit", "-a", "-m", f"{commit_msg} (rhbz#{bug_id})"],
        check=True,
        cwd=distgit_path,
    )


def submit_patch(pkg: str) -> str:
    distgit_path = distgit_workdir / pkg

    subprocess.run(
        ["git", "checkout", distgit_branch],
        check=True,
        cwd=distgit_path,
    )
    subprocess.run(
        ["git", "push", fasid()],
        check=True,
        cwd=distgit_path,
    )
    copr_build = copr_client.build_proxy.create_from_distgit(
        ownername=copr_owner,
        projectname=copr_project,
        packagename=pkg,
        namespace=f"forks/{fasid()}",
        committish=distgit_branch,
        buildopts={
            "background": True,
        },
    )
    response = requests.post(
        f"https://src.fedoraproject.org/api/0/rpms/{pkg}/pull-request/new",
        headers={
            "Authorization": f"token {pagure_token()}"
        },
        json={
            "title": PR_title.format(
                package=pkg,
                branch=branch,
                change_proposal=change_proposal,
            ),
            "branch_from": distgit_branch,
            "branch_to": branch,
            "repo_from": pkg,
            "repo_from_username": fasid(),
            "repo_from_namespace": "rpms",
            "initial_comment": PR_message.format(
                package=pkg,
                change_proposal=change_proposal,
                copr_owner=copr_owner,
                copr_project=copr_project,
                change_slug=change_slug,
                branch=branch,
                copr_build=copr_build,
            )
        }
    )
    if response.status_code != 200:
        raise RuntimeError(f"Failed to submit PR [{response.status_code}]:\n{response.json()}")
    pr_id = response.json()["id"]
    return f"https://src.fedoraproject.org/rpms/{pkg}/pull-request/{pr_id}"


def get_specfile(pkg: str) -> Specfile:
    specfile_path = distgit_workdir / pkg / f"{pkg}.spec"
    specfile = Specfile(specfile_path)
    return specfile


def patch_pkg(pkg: str, specfile: Specfile) -> None:
    global cache_data

    bug_id = cache_data[pkg]["id"]
    with specfile.tags() as tags:
        last_br_index = None
        last_br_tag = None
        for indx, tag in enumerate(tags):
            if tag.name == "BuildRequires":
                last_br_index = indx
                last_br_tag = tag
                if tag.value == "make":
                    break
        else:
            assert last_br_index is not None
            tag = Tag("BuildRequires", "make", last_br_tag._separator, Comments())
            tags.insert(last_br_index + 1, tag)
        tag.comments.append("Hard-code make dependency due to ninja-build failure")
        tag.comments.append(f"https://fedoraproject.org/wiki/Changes/{change_slug}")
        tag.comments.append(Comment("%define _cmake_generator \"Unix Makefiles\"", prefix=""))

    if not specfile.has_autorelease:
        specfile.bump_release()
        specfile.add_changelog_entry(f"- {commit_msg} (rhbz#{bug_id})")

    specfile.save()


for pkg in packages:
    # Check the presence in cache file first
    if pkg in cache_data:
        if update_cahed_bugs:
            bug = bzapi.getbug(cache_data[pkg]["id"])
            cache_bug(pkg, bug)
        check_bug_state(pkg)
        print(f"Bug for {pkg} found in cache: {cache_data[pkg]['status']}")
        continue

    # Otherwise search or create the bug
    curr_title = title.format(
        package=pkg,
        change_proposal=change_proposal,
    )

    # Check if a bug was already opened
    query = bzapi.build_query(
        product="Fedora",
        component=pkg,
        version=branch,
        short_desc=curr_title,
    )
    bugs = bzapi.query(query)
    if bugs:
        if len(bugs) > 1:
            print(f"Warning, {pkg} has more than 1 bug matching.")
        bug = bugs[0]
        cache_bug(pkg, bug)
        check_bug_state(pkg)
        print(f"Bug for {pkg} already exists: Cached result")
        continue

    # Otherwise create the bug
    print(f"Creating bug for {pkg}")
    bug = bzapi.createbug(
        bzapi.build_createbug(
            product="Fedora",
            component=pkg,
            version=branch,
            summary=curr_title,
            description=body.format(
                package=pkg,
                change_proposal=change_proposal,
                copr_owner=copr_owner,
                copr_project=copr_project,
                change_slug=change_slug,
            ),
            blocks=blocks_bgz,
        )
    )
    cache_bug(pkg, bug)

print("Overview:")
for status, bug_packages in bug_state.items():
    print(f"Status {status}: {len(bug_packages)}")
