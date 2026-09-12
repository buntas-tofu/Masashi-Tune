"""bench_config: deployment parameters for the bench instruments.

Every deployment-specific value in this toolkit is read from the environment
with a neutral default, so an instrument runs unchanged against a real fabric
or against nothing at all. Set a variable to point an instrument at a
deployment; leave it unset and the instrument uses the neutral example value.

    BENCH_HOST          Host or address a bench serve binds to or is reached
                        at. Default: 127.0.0.1
    BENCH_PORT          Port the standalone bench serve binds.
                        Default: 8089
    BENCH_GPU           CUDA device index the bench serve runs on.
                        Default: 0
    BENCH_MODELS        Model store root holding one directory per vessel.
                        Default: ~/models
    BENCH_LLAMA         Path to the llama-server binary.
                        Default: ~/llama.cpp/build/cuda/bin/llama-server
    BENCH_RUNS          Directory for run tapes. Default: a runs/ directory
                        beside the calling instrument.
    BENCH_RUNS_LANE     Run-manifest telemetry lane, one JSONL per day.
                        Default: ~/bench-runs
    BENCH_NODES         Comma-separated node names the sampler and relay use.
                        Default: example-a,example-b,example-c
    BENCH_NODE_HOSTS    Comma-separated host:port pairs, one per node, for the
                        remote bench serves. Default:
                        127.0.0.1:8085,127.0.0.1:8086,127.0.0.1:8087
    BENCH_VENDORS       Comma-separated device vendor per node, nvidia or amd.
                        Default: nvidia,nvidia,nvidia
    BENCH_SSH_OPTS      Extra ssh options, space separated.
                        Default: -o BatchMode=yes -o ConnectTimeout=10
    BENCH_WORKERS       JSON list of silicon workers for the cross-silicon
                        arm. Each entry carries label, node (null for local),
                        ip, root, and residents. Default: one local worker.
    BENCH_REASONER_URL  Reasoner endpoint for the relay.
                        Default: http://127.0.0.1:8000
    BENCH_VIEW          View base URL for the wire instruments.
                        Default: http://127.0.0.1:8088
    BENCH_FACE_METRICS  Metrics endpoint of the face serve.
                        Default: http://127.0.0.1:8080/metrics
    BENCH_SEAT          Seat key a wire instrument drives.
                        Default: bench-candidate
    BENCH_CORPUS        Corpus JSONL the setlist freezes its sample from.
                        Default: anchors/operations_content_v1.json beside the
                        calling instrument.
    BENCH_RUNTIME       Directory added to sys.path for instruments that drive
                        the fabric runtime. Those instruments import the runtime
                        as the package `fabric_runtime`. Unset means they fail
                        cleanly with a neutral message.
    BENCH_SNAP          Checkpoint snapshot root for the checkpoint
                        instruments. Default: ~/models/staging/checkpoint

Floor: DMF. No em dashes, no ellipses.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def env(name: str, default: str = "") -> str:
    """One environment value, or the neutral default."""
    value = os.environ.get(name, "")
    return value if value.strip() else default


def tool_dir() -> Path:
    """The directory holding this toolkit, so tapes sit beside it by default."""
    return Path(__file__).resolve().parent


def runs_dir() -> Path:
    """The run-tape directory."""
    spec = env("BENCH_RUNS", "")
    return Path(spec).expanduser() if spec else tool_dir() / "runs"


def runs_lane() -> Path:
    """The run-manifest telemetry lane."""
    return Path(env("BENCH_RUNS_LANE", "~/bench-runs")).expanduser()


def models_dir() -> Path:
    """The model store root."""
    return Path(env("BENCH_MODELS", "~/models")).expanduser()


def llama_server() -> Path:
    """The llama-server binary."""
    return Path(env("BENCH_LLAMA", "~/llama.cpp/build/cuda/bin/llama-server")).expanduser()


def snap_dir() -> Path:
    """The checkpoint snapshot root."""
    return Path(env("BENCH_SNAP", "~/models/staging/checkpoint")).expanduser()


def csv_env(name: str, default: str) -> list[str]:
    """A comma-separated environment value as a stripped list."""
    return [x.strip() for x in env(name, default).split(",") if x.strip()]


def nodes() -> list[str]:
    """The node list the sampler and relay work over."""
    return csv_env("BENCH_NODES", "example-a,example-b,example-c")


def node_hosts() -> list[str]:
    """Host:port pairs, one per node."""
    return csv_env("BENCH_NODE_HOSTS",
                   "127.0.0.1:8085,127.0.0.1:8086,127.0.0.1:8087")


def vendors() -> list[str]:
    """Device vendor per node, nvidia or amd."""
    return csv_env("BENCH_VENDORS", "nvidia,nvidia,nvidia")


def ssh_opts() -> list[str]:
    """Extra ssh options, split. Applied to every remote probe."""
    return env("BENCH_SSH_OPTS", "-o BatchMode=yes -o ConnectTimeout=10").split()


DEFAULT_WORKERS = [
    {"label": "local", "node": None, "ip": "127.0.0.1",
     "root": env("BENCH_MODELS", "~/models"), "residents": ""},
]


def workers() -> list[dict]:
    """The silicon workers the cross-silicon arm runs against."""
    raw = env("BENCH_WORKERS", "")
    if not raw:
        return DEFAULT_WORKERS
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return DEFAULT_WORKERS
    return parsed if isinstance(parsed, list) and parsed else DEFAULT_WORKERS


def add_runtime_path() -> bool:
    """Put BENCH_RUNTIME on sys.path so a `fabric_runtime` package can import.

    Returns True when the variable is set. The instruments that drive the
    fabric runtime import it as `fabric_runtime`; a deployment points
    BENCH_RUNTIME at the parent directory of its own copy under that name.
    """
    spec = env("BENCH_RUNTIME", "")
    if not spec:
        return False
    path = str(Path(spec).expanduser())
    if path not in sys.path:
        sys.path.insert(0, path)
    return True


RUNTIME_HINT = (
    "this instrument drives the fabric runtime, which is not part of this "
    "repository; set BENCH_RUNTIME to the directory holding the "
    "`fabric_runtime` package and re-run"
)
