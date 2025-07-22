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
    "Lmod",
    "NetworkManager",
    "acpica-tools",
    "alex",
    "alsa-firmware",
    "alsa-lib",
    "alsa-plugins",
    "anthy",
    "attr",
    "augeas",
    "autotrace",
    "avahi",
    "bc",
    "beakerlib",
    "bitmap-fonts",
    "blivet-gui",
    "bolt",
    "booth",
    "breezy",
    "brltty",
    "byteman",
    "ca-certificates",
    "cabal-install",
    "calc",
    "corosync",
    "corosync-qdevice",
    "cpio",
    "cracklib",
    "cri-o",
    "criu",
    "cronie",
    "crontabs",
    "cryptsetup",
    "ctags",
    "culmus-fonts",
    "cyrus-sasl",
    "dash",
    "dbus-glib",
    "dbus-python",
    "device-mapper-multipath",
    "device-mapper-persistent-data",
    "diffutils",
    "dropwatch",
    "efi-rpm-macros",
    "ektype-mukta-fonts",
    "electron-cash",
    "etcd",
    "fcoe-utils",
    "fedora-repos",
    "findutils",
    "fontforge",
    "fprintd",
    "freeradius",
    "fstrm",
    "gawk",
    "gfs2-utils",
    "ghc",
    "ghc-zlib",
    "ghc9.0",
    "ghc9.2",
    "ghc9.4",
    "gnome-calculator",
    "golang-github-aliyun-cli",
    "golang-github-dustinkirkland-petname",
    "golang-github-haproxytech-dataplaneapi",
    "google-croscore-fonts",
    "google-crosextra-caladea-fonts",
    "groff",
    "gubbi-fonts",
    "hostapd",
    "hwdata",
    "ibus-engine-gui-ci",
    "ignition",
    "initscripts",
    "iproute",
    "iprutils",
    "ipset",
    "iptables",
    "iptraf-ng",
    "irqbalance",
    "iso-codes",
    "japanese-bitmap-fonts",
    "kacst-fonts",
    "khmer-os-fonts",
    "kmod",
    "knot",
    "knot-resolver",
    "kurdit-unikurd-web-fonts",
    "ladvd",
    "langpacks",
    "libblockdev",
    "libconfig",
    "libffi",
    "libfprint",
    "libgcrypt",
    "libguestfs",
    "libnbd",
    "libnet",
    "librabbitmq",
    "libreswan",
    "libspiro",
    "libssh",
    "libstoragemgmt",
    "libtasn1",
    "libuninameslist",
    "libusb-compat-0.1",
    "libusb1",
    "libvarlink",
    "lklug-fonts",
    "lksctp-tools",
    "lldpad",
    "lldpd",
    "llvm-test-suite",
    "llvm11",
    "llvm12",
    "lorax-templates-rhel",
    "lsscsi",
    "lua",
    "m4",
    "mariadb-connector-odbc",
    "mariadb10.11",
    "marshalparser",
    "memcached",
    "mod_authnz_pam",
    "mod_intercept_form_submit",
    "mpfr",
    "navilu-fonts",
    "nbdkit",
    "net-snmp",
    "nkf",
    "nmstate",
    "ocaml",
    "ocaml-augeas",
    "ocaml-calendar",
    "ocaml-cppo",
    "ocaml-curses",
    "ocaml-dune",
    "ocaml-fileutils",
    "ocaml-findlib",
    "ocaml-gettext",
    "ocaml-labltk",
    "ocaml-libvirt",
    "ocaml-ocamlbuild",
    "oci-seccomp-bpf-hook",
    "oflb-asana-math-fonts",
    "omping",
    "opal-prd",
    "opencc",
    "openhpi",
    "openldap",
    "openoffice-lv",
    "opensc",
    "openvpn",
    "openvswitch",
    "overpass-fonts",
    "p11-kit",
    "pacemaker",
    "paktype-naqsh-fonts",
    "paktype-tehreer-fonts",
    "pam",
    "patch",
    "po4a",
    "poetry",
    "pyparted",
    "pyproject-rpm-macros",
    "pypy",
    "pypy3.10",
    "pypy3.11",
    "python-APScheduler",
    "python-ansi2html",
    "python-augeas",
    "python-avocado",
    "python-cheetah",
    "python-configshell",
    "python-dasbus",
    "python-docker",
    "python-flit",
    "python-flit-core",
    "python-munkres",
    "python-packaging",
    "python-pidfile",
    "python-pika",
    "python-pip",
    "python-poetry-core",
    "python-rpm-generators",
    "python-rpm-macros",
    "python-rtslib",
    "python-setuptools",
    "python-setuptools-rust",
    "python-setuptools_scm",
    "python-toml",
    "python-tox",
    "python-tox-current-env",
    "python-tox-uv",
    "python-ufoLib2",
    "python-virt-firmware",
    "python-virtualenv",
    "python3.10",
    "python3.11",
    "python3.12",
    "python3.13",
    "python3.13-flit-core",
    "python3.14",
    "python3.6",
    "python3.9",
    "qrencode",
    "rpm",
    "rpm-ostree",
    "rust-add-determinism",
    "saab-fonts",
    "sbd",
    "sed",
    "sg3_utils",
    "shadow-utils",
    "shobhika-fonts",
    "sil-abyssinica-fonts",
    "smc-anjalioldlipi-fonts",
    "snapd",
    "sox",
    "spausedd",
    "squashfs-tools",
    "stubby",
    "sudo",
    "sword",
    "tar",
    "targetcli",
    "targetd",
    "teckit",
    "tibetan-machine-uni-fonts",
    "trace-cmd",
    "ttfautohint",
    "ttmkfdir",
    "udica",
    "uglify-js",
    "upower",
    "usbguard",
    "vhostmd",
    "virt-p2v",
    "virt-top",
    "virt-v2v",
    "virt-what",
    "virtiofsd",
    "volume_key",
    "wide-dhcpv6",
    "wpa_supplicant",
    "wqy-microhei-fonts",
    "wqy-unibit-fonts",
    "xsimd",
    "zip",
]
change_slug: str | None = "DisableSTI"
copr_project: str | None = None
change_proposal: str | None = "Disablement of STI tests"

title: str = r"{package}: STI tests will no longer be run in F43"
body: str = r"""
Dear package maintainer,

This is an automated bug created due to the announced change proposal {change_proposal}.

Your project still has STI tests under `tests/tests*.yml`, which will no longer be run soon. We suggest you
migrate these tests to TMT format instead.

In the simplest case when the STI tests is a simple wrapper around a `tests/run_tests.sh`, the migration would
look like this:
```
$ tmt init
$ rm tests/tests.yml
$ cat <<EOF > ./plans.fmf
summary: Run all smoke tests
discover:
  how: fmf
execute:
  how: tmt
EOF
$ cat <<EOF > ./tests/main.fmf
summary: Smoke test
test: ./run_tests.sh
EOF
```

See https://fedoraproject.org/wiki/Changes/{change_slug} for more information, including a link to a migration
guide.

Feel free to reach out to us here or in #fedora-ci or #tmt matrix rooms if you need any help.
"""
blocks_bgz: int | None = 2346261

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
