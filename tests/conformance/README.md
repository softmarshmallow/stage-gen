# gnode conformance

Each case is a folder: `in/` is a gnode project (`gnode.yaml`, workflow files, node modules,
inputs, a `routes.yaml` catalog) and `case.yaml` says which command to run on it; `expected/`
holds what that command must print. The suite runs the `gnode` command line only and never
imports gnode, so any implementation of gnode (the Rust core included) can be held to it.

    uv run python tests/conformance/run.py            # check every case
    uv run python tests/conformance/run.py --write    # rewrite expected/ after a deliberate change

Commands: `gnode expand`, `gnode identity`, `gnode price` (on a plan) and `gnode project` (on a
run the case makes with `gnode run`). Identities are content digests, so they are pinned too:
a change that moves one is a change to every cache.
