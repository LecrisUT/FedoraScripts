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
packages: list[str] = [
    "bandit",
    "fapolicy-analyzer",
    "python-aiolimiter",
    "python-box",
    "python-jinja2-cli",
    "python-matrix-nio",
    "python-nikola",
    "python-rstcheck-core",
    "python-sklearn-nature-inspired-algorithms",
    "python-toml-adapt",
    "python-usort",
    "python-vulture",
    "teampulls",
]
copr_project: str | None = None
title: str | None = r"{package}: Remove python-toml dependency"
body: str | None = r"""
Dear package maintainer,

This is an automated bug created to track the remaining packages that will be affected by the python-toml retirement
following its orphanage.

python-toml has been marked deprecated for a few release cycle, since the change proposal
https://fedoraproject.org/wiki/Changes/{change_slug}. Please see the change proposal or the blocked bug for some tips
on how to migrate to another dependency, recommended `tomllib` with `tomli` backport.
"""
change_proposal: str | None = "Deprecate python-toml"
change_slug: str | None = "DeprecatePythonToml"
blocks_bgz: int | None = 2392538

copr_client = Client.create_from_config_file()
bzapi = bugzilla.Bugzilla("bugzilla.redhat.com")

ftbfs_title = r"{package}: FTBFS in Fedora rawhide/f43"

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
        "depends": bug.depends_on if hasattr(bug, "depends_on") else [],
        "assigned_to": bug.assigned_to if hasattr(bug, "assigned_to") else None,
    }

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
