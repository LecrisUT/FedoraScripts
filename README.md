# Helper scripts for Fedora packaging

A collection of helper scripts written in Python with PEP723 compatibility.

No testing or distribution is intended for these, but feel free to adapt
them to your own needs.

To run them you can simply use `(pipx|hatch) run <script>`.

- [`get_maintainers`](./get_maintainers.py): Get the package maintainers
- [`add_packit_reverse_deps`](./add_packit_reverse_deps.py): Add new reverse dependencies for a packit project
- [`copr_rev_deps`](./copr_rev_deps.py): Do impact check in copr
- [`update_rust_pacakges`](./update_rust_packages.py): Update rust packages with `rust2rpm`
