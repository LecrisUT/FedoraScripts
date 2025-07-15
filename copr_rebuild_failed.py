# /// script
# dependencies = [
#   "copr",
# ]
# ///

"""
Rebuild failed copr packages with the latest reference from rawhide.
"""

from __future__ import annotations

from copr.v3 import Client

# User-defined variables
branch: str = "rawhide"
project: str | None = "lecris/cmake-4.0"
packages: list[str] = []

client = Client.create_from_config_file()
owner, project = project.split("/")

if not packages:
    if not project:
        raise ValueError("No packages specified")

    for pkg in client.package_proxy.get_list(
        ownername=owner,
        projectname=project,
        with_latest_build=True,
    ):
        # TODO: Add a check to see if downstream has not been retired.
        if pkg.builds["latest"]["state"] != "failed":
            continue
        packages.append(pkg.name)

for pkg in packages:
    print(f"Submitting re-build for: {pkg}")
    client.build_proxy.create_from_distgit(
        ownername=owner,
        projectname=project,
        packagename=pkg,
        committish=branch,
        buildopts={
            "background": True,
        },
    )
