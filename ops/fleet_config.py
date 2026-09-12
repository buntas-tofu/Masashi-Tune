"""fleet_config: deployment parameters for the ops tools.

Every deployment-specific value in this toolkit is read from the environment
with a neutral default, so one tool runs unchanged against a real fleet or
against nothing at all. Set a variable to point a tool at a deployment; leave
it unset and the tool uses the neutral example value and touches nothing
outside its own working directory. This module reads locations and names only.
It never reads or holds a credential value; the credential collectors below
work from file globs and hash metadata alone.

    FLEET_NODES             Comma-separated node names, reached by ssh alias
                            (each alias carries its own per-node username).
                            Default: example-a,example-b,example-c
    FLEET_SSH_OPTS          Extra ssh options, space separated.
                            Default: -o BatchMode=yes -o ConnectTimeout=10
    FLEET_UNIT_DIR          Per-node systemd user unit directory.
                            Default: ~/.config/systemd/user
    FLEET_UNITS_RECORD      Recorded unit tree the drift gate diffs against.
                            Default: units/fleet beside the calling tool.
    FLEET_ROSTER_DIR        Optional directory holding seat roster TOML files
                            (seats.toml, vessels.toml). Unset or unreadable
                            means the roster-coupled checks are skipped and
                            the gate says so in its report.
    FLEET_POSTURE_FILE      Per-node card-claim posture JSON, read on the
                            remote side. Default: ~/.config/fleet/posture.json
    FLEET_PATH_ENV          Per-node env file sourced by the machine probe.
                            Default: ~/.config/fleet/paths.env
    FLEET_STORAGE_ROOT      Primary storage root for the reconciler.
                            Default: ~/storage
    FLEET_STORAGE_ROOTS     Comma-separated candidate roots for the collector.
                            Default: $HOME,~/storage
    FLEET_COLLECTOR         Comma-separated node paths to the collector. Set
                            this to where the collector actually lives on a
                            node; the first path that exists is used.
                            Default: ~/ops/collector.py
    FLEET_MACHINES_DIR      Recorded machine profiles.
                            Default: machines beside the calling tool.
    FLEET_MODEL_STORES      Comma-separated model-store candidate paths.
                            Default: $HOME/models,~/storage/models
    FLEET_LLAMA_GLOBS       Comma-separated llama-server build globs to probe.
                            Default: $HOME/llama.cpp/build/*/bin/llama-server
    FLEET_DISK_MOUNTS       Space-separated mounts the machine probe reports.
                            Default: / $HOME
    FLEET_REPO_ROOTS        Comma-separated roots the remote-audit walks.
                            Default: $HOME
    FLEET_CREDENTIAL_GLOBS  Comma-separated credential-file globs inventoried
                            by the compromise collector, by metadata and hash
                            only, contents never read.
                            Default: the standard ~/.ssh, ~/.aws, ~/.netrc set.
    FLEET_WATCH_ROOT        Output root for the compromise collector.
                            Default: ~/watch
    FLEET_MEMORY_DIR        Memory sediment spine for the read-only gates.
                            Default: ~/memory

Floor: DMF. No em dashes, no ellipses.
"""

from __future__ import annotations

import os
from pathlib import Path

DEFAULT_NODES = "example-a,example-b,example-c"
DEFAULT_SSH_OPTS = "-o BatchMode=yes -o ConnectTimeout=10"
DEFAULT_UNIT_DIR = "~/.config/systemd/user"
DEFAULT_POSTURE_FILE = "~/.config/fleet/posture.json"
DEFAULT_PATH_ENV = "~/.config/fleet/paths.env"
DEFAULT_STORAGE_ROOTS = "$HOME,~/storage"
DEFAULT_COLLECTOR = "~/ops/collector.py"
DEFAULT_MODEL_STORES = "$HOME/models,~/storage/models"
DEFAULT_LLAMA_GLOBS = "$HOME/llama.cpp/build/*/bin/llama-server"
DEFAULT_DISK_MOUNTS = "/ $HOME"
DEFAULT_REPO_ROOTS = "$HOME"
DEFAULT_CREDENTIAL_GLOBS = (
    "~/.ssh/id_*", "~/.ssh/authorized_keys", "~/.ssh/known_hosts",
    "~/.aws/credentials", "~/.aws/config", "~/.netrc", "~/.git-credentials",
    "~/.config/gh/hosts.yml", "~/.docker/config.json", "~/.kube/config",
    "~/.config/systemd/user/*.service.d/*.conf",
)
DEFAULT_WATCH_ROOT = "~/watch"
DEFAULT_MEMORY_DIR = "~/memory"


def env(name: str, default: str = "") -> str:
    """One environment value, or the neutral default."""
    value = os.environ.get(name, "")
    return value if value.strip() else default


def csv_env(name: str, default: str) -> list[str]:
    """A comma-separated environment value as a stripped list."""
    return [x.strip() for x in env(name, default).split(",") if x.strip()]


def nodes() -> list[str]:
    """The node list every fleet tool works over."""
    return csv_env("FLEET_NODES", DEFAULT_NODES)


def ssh_opts() -> list[str]:
    """Extra ssh options, split. Applied to every remote probe."""
    return env("FLEET_SSH_OPTS", DEFAULT_SSH_OPTS).split()


def expand(path: str) -> str:
    """A path with ~ or $HOME resolved against THIS process. Used for local
    reads and writes only; remote paths are left for the remote shell."""
    return str(Path(path).expanduser())


def tool_dir() -> Path:
    """The directory holding this toolkit, so record trees sit beside it."""
    return Path(__file__).resolve().parent


def units_record() -> Path:
    """The recorded unit tree the drift gate diffs against."""
    spec = env("FLEET_UNITS_RECORD", "")
    return Path(spec).expanduser() if spec else tool_dir() / "units" / "fleet"


def machines_dir() -> Path:
    """The recorded machine-profile tree the profile gate diffs against."""
    spec = env("FLEET_MACHINES_DIR", "")
    return Path(spec).expanduser() if spec else tool_dir() / "machines"


def roster_dir() -> Path | None:
    """The optional seat-roster directory. None when unset, which is the
    signal for a tool to skip its roster-coupled checks and say so."""
    spec = env("FLEET_ROSTER_DIR", "")
    return Path(spec).expanduser() if spec else None
