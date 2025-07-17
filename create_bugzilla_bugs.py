# /// script
# dependencies = [
#   "copr",
#   "bugzilla",
# ]
# ///

"""
Create bugzilla bugs for failing copr project builds.

This is primarily built to help create blocking bugs for a change proposal.
"""

from __future__ import annotations

import json
from json import JSONDecodeError
from pathlib import Path

from copr.v3 import Client
import bugzilla

# User defined variables
update_cahed_bugs: bool = True
branch: str = "rawhide"
packages: list[str] = []
change_slug: str | None = "CMake4.0"
copr_project: str | None = "lecris/cmake-4.0"
change_proposal: str | None = "CMake 4.0"

title: str = r"{package}: FTBFS with change proposal {change_proposal}"
body: str = r"""
Dear package maintainer,

This is an automated bug created due to a FTBFS when rebuilding this package for the change proposal {change_proposal}.

The rebuild is being tracked in https://copr.fedorainfracloud.org/coprs/{copr_owner}/{copr_project}/package/{package}.

See https://fedoraproject.org/wiki/Changes/{change_slug} for more information on how to make the package compatible.

More specifically, depending on the state of the project:
- If it is actively maintained, please update the `cmake_minimum_required`, and instruct upstream to do so as well.
  To minimize future maintenance, please add a higher bound as well, preferrably with the highest CMake version being
  tested. You may use 4.0 as the higher bound as this is being tested in the tracked copr project.
- If the project is not maintained, you may add `CMAKE_POLICY_VERSION_MINIMUM=3.5` as a CMake variable or environment
  variable.

You can check the build locally following the instructions in the change proposal, or submit your build to the tracking
copr project.

Let me know if you encounter any issues, or need any other help.
"""
blocks_bgz: int | None = 2376114

copr_client = Client.create_from_config_file()
bzapi = bugzilla.Bugzilla("bugzilla.redhat.com")

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

    cache_data[pkg] = {
        "id": bug.id,
        "status": bug.status if hasattr(bug, "status") else None,
    }
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
