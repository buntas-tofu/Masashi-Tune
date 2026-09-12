#!/usr/bin/env python3
"""
Compromise-assessment collector for a small fleet.

WHY THIS EXISTS, 2026-08-12. The operator's ruling was to baseline the fabric as
if any node were already infected, deep enough to speak to whether the
transistors are compromised. That word "as if" is the whole design. Ordinary
monitoring asks a host to describe itself and believes the answer. This tool
does not, because a compromised host lies: its ps, its ss, its package verifier,
and if the implant is in the kernel, its /proc as well.

So the trust ladder inverts, and this file exists to record data at a stated
tier rather than to pronounce a verdict:

  TIER 1  offline and firmware truth. The node examined while NOT running its
          own OS, or a firmware surface read and compared to a vendor image.
  TIER 2  wire truth. What node A observes about node B. B cannot forge this
          without also owning A.
  TIER 3  vendor-signed comparison. On-disk artifacts against an external
          source of truth (package signatures, upstream commits).
  TIER 4  on-host self-report. Collected in full, trusted last, and mined
          mostly for where it DISAGREES with the tiers above it.

Every record this tool writes carries its tier. Nothing here is evidence of
health on its own. The finding this design hunts is a DISCREPANCY, and three of
them are computed in-process because they are cheap and they catch the classic
implant:

  ps versus a direct readdir of /proc        a hidden process
  ss versus a raw parse of /proc/net/*       a hidden listener
  a running executable whose file is gone    the deleted-binary tell

The fourth and best discrepancy is not computable here: this node's listener
list against what another node's scanner sees on the wire. That one runs in the
wire subcommand from an OBSERVER node, and it is the reason this fabric can
assess itself at all. One host can be lied to. Five, watching each other, is a
harder room to work.

WHAT IT DOES. Read-only, always. It runs commands and reads files, it never
changes system state, and it writes only inside its own output directory.

  collect --tier volatile|persistence|firmware|all    on-host, tiers 3 and 4
  wire --targets a,b,c                                observer-side, tier 2
  seal <run-dir>                                      content-address and seal
  verify <run-dir>                                    re-check a seal

CREDENTIAL POSTURE, deliberate and load-bearing. This collector is itself a
high-value target: its output is an inventory of every listener, key, and
firmware surface on a host. So it never records a secret's CONTENT.
Credential files are inventoried by path, mode, owner, size, and hash only.
Process environments are never dumped, only probed for the three loader
variables that matter (LD_PRELOAD, LD_AUDIT, LD_LIBRARY_PATH), because an
environ block can hold a service API key. Command lines are
redacted through a pattern guard before they are written, because a key passed
as a flag is a key in the record. The policy is the design and the guard is the
belt, the same posture unit_drift.py takes toward unit content.

This file documents and reads environment variable NAMES only. It never carries
a credential value, a key, or a private path. The credential-file globs it
inventories come from FLEET_CREDENTIAL_GLOBS and the output root from
FLEET_WATCH_ROOT; both are deployment values with neutral defaults, see
fleet_config.py.

Output lands under the configured watch root, outside any repo. Never in a repo,
never anywhere with an external remote.

Exit code is 0 unless the tool itself failed. It reports, the operator judges.
"""

import argparse
import hashlib
import json
import os
import platform
import pwd
import re
import shutil
import socket
import stat
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fleet_config as cfg  # noqa: E402

TOOL_VERSION = "0.1.0"
DEFAULT_ROOT = Path(cfg.env("FLEET_WATCH_ROOT", cfg.DEFAULT_WATCH_ROOT)).expanduser()
CMD_TIMEOUT = 60

TIER_NOTES = {
    1: "firmware or offline truth",
    2: "wire truth, observed from another host",
    3: "vendor-signed comparison",
    4: "on-host self-report, least trusted under assume-breach",
}

# Anything matching these is redacted before it is written. Command lines and
# unit fragments are the realistic carriers on this fabric.
SECRET_PATTERNS = [
    re.compile(r"(?i)(api[-_]?key|apikey|secret|token|passwd|password|auth)\s*[=:]\s*\S+"),
    re.compile(r"(?i)--(key|token|secret|password|api[-_]?key)(=|\s+)\S+"),
    re.compile(r"(?i)bearer\s+[A-Za-z0-9._\-]{12,}"),
    re.compile(r"sk-[A-Za-z0-9._\-]{16,}"),
    re.compile(r"(?i)aws_(secret|session)_\w*\s*[=:]\s*\S+"),
    re.compile(r"tskey-[A-Za-z0-9\-]{8,}"),
    re.compile(r"gh[pousr]_[A-Za-z0-9]{16,}"),
]

# Inventoried by metadata and hash only. Contents are never read. The glob set
# is a deployment value (FLEET_CREDENTIAL_GLOBS); the defaults are the standard
# per-user credential locations on a Linux box.
CREDENTIAL_GLOBS = cfg.csv_env("FLEET_CREDENTIAL_GLOBS",
                               ",".join(cfg.DEFAULT_CREDENTIAL_GLOBS))


def redact(text):
    """Strip anything secret-shaped. Applied to every free-text field written."""
    if not text:
        return text
    out = text
    for pat in SECRET_PATTERNS:
        out = pat.sub(lambda m: m.group(0).split("=")[0].split(":")[0] + "=<redacted>", out)
    return out


def utcstamp():
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def sha256_file(path):
    h = hashlib.sha256()
    try:
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                h.update(chunk)
        return h.hexdigest()
    except (OSError, PermissionError) as exc:
        return f"unreadable: {type(exc).__name__}"


def run(argv, tier=4, timeout=CMD_TIMEOUT, needs_root=False):
    """Run one read-only command and record it verbatim. Never raises."""
    rec = {
        "argv": argv,
        "tier": tier,
        "tier_note": TIER_NOTES[tier],
        "needs_root": needs_root,
    }
    exe = shutil.which(argv[0])
    if exe is None:
        rec["status"] = "tool_absent"
        return rec
    if needs_root and os.geteuid() != 0:
        rec["status"] = "skipped_unprivileged"
        return rec
    started = time.time()
    try:
        proc = subprocess.run(
            argv, capture_output=True, text=True, timeout=timeout, check=False
        )
        rec["status"] = "ok"
        rec["rc"] = proc.returncode
        rec["stdout"] = redact(proc.stdout)
        rec["stderr"] = redact(proc.stderr[:4000])
    except subprocess.TimeoutExpired:
        rec["status"] = "timeout"
    except Exception as exc:  # a collector must never take the run down
        rec["status"] = f"error: {type(exc).__name__}: {exc}"
    rec["elapsed_s"] = round(time.time() - started, 3)
    return rec


def read_text(path, limit=256_000, tier=4):
    rec = {"path": str(path), "tier": tier, "tier_note": TIER_NOTES[tier]}
    try:
        p = Path(path)
        st = p.stat()
        rec["mode"] = oct(stat.S_IMODE(st.st_mode))
        rec["uid"] = st.st_uid
        rec["gid"] = st.st_gid
        rec["size"] = st.st_size
        rec["mtime"] = datetime.fromtimestamp(st.st_mtime, timezone.utc).isoformat()
        rec["sha256"] = sha256_file(p)
        rec["content"] = redact(p.read_text(errors="replace")[:limit])
        rec["status"] = "ok"
    except FileNotFoundError:
        rec["status"] = "absent"
    except PermissionError:
        rec["status"] = "permission_denied"
    except Exception as exc:
        rec["status"] = f"error: {type(exc).__name__}"
    return rec


def stat_only(path, tier=4):
    """Metadata and hash, never content. The credential-safe reader."""
    rec = {"path": str(path), "tier": tier, "tier_note": TIER_NOTES[tier],
           "content_policy": "never read by design"}
    try:
        p = Path(path)
        st = p.lstat()
        rec["mode"] = oct(stat.S_IMODE(st.st_mode))
        rec["uid"] = st.st_uid
        rec["gid"] = st.st_gid
        rec["size"] = st.st_size
        rec["mtime"] = datetime.fromtimestamp(st.st_mtime, timezone.utc).isoformat()
        rec["is_symlink"] = stat.S_ISLNK(st.st_mode)
        if not rec["is_symlink"]:
            rec["sha256"] = sha256_file(p)
        else:
            rec["target"] = os.readlink(p)
        rec["status"] = "ok"
    except FileNotFoundError:
        rec["status"] = "absent"
    except PermissionError:
        rec["status"] = "permission_denied"
    except Exception as exc:
        rec["status"] = f"error: {type(exc).__name__}"
    return rec


# ---------------------------------------------------------------- discrepancy

def proc_pids_direct():
    """PIDs by readdir of /proc. The reference the ps hook cannot reach."""
    return {int(d) for d in os.listdir("/proc") if d.isdigit()}


def ps_pids(ps_stdout):
    pids = set()
    for line in ps_stdout.splitlines()[1:]:
        line = line.strip()
        if not line:
            continue
        head = line.split()[0]
        if head.isdigit():
            pids.add(int(head))
    return pids


def hidden_process_check():
    """
    ps versus a direct readdir of /proc, twice, to survive normal churn.

    A process that starts or exits between the two reads is not a finding, so a
    candidate only counts if it is still absent from ps on the second pass AND
    its /proc entry still exists. Honest instrument, no false alarms at 4am.
    """
    out = {"check": "hidden_process", "tier": 4, "tier_note": TIER_NOTES[4],
           "method": "ps -e versus readdir(/proc), two passes"}
    argv = ["ps", "-eo", "pid"]
    first_ps = run(argv)
    if first_ps.get("status") != "ok":
        out["status"] = "unavailable"
        out["detail"] = first_ps.get("status")
        return out
    direct1 = proc_pids_direct()
    seen1 = ps_pids(first_ps.get("stdout", ""))
    candidates = direct1 - seen1
    time.sleep(0.7)
    second_ps = run(argv)
    seen2 = ps_pids(second_ps.get("stdout", ""))
    stable = []
    for pid in sorted(candidates):
        if pid in seen2:
            continue
        if not Path(f"/proc/{pid}").exists():
            continue
        entry = {"pid": pid}
        try:
            entry["exe"] = os.readlink(f"/proc/{pid}/exe")
        except OSError as exc:
            entry["exe"] = f"unreadable: {type(exc).__name__}"
        try:
            entry["comm"] = Path(f"/proc/{pid}/comm").read_text().strip()
        except OSError:
            entry["comm"] = None
        stable.append(entry)
    out["status"] = "ok"
    out["proc_count"] = len(direct1)
    out["ps_count"] = len(seen1)
    out["stable_discrepancies"] = stable
    out["finding"] = (
        "NONE: ps agrees with /proc" if not stable
        else f"DISCREPANCY: {len(stable)} pid(s) in /proc and absent from ps"
    )
    return out


def parse_proc_net(path, listen_only=True):
    """
    Raw kernel socket table. The reference the ss hook cannot reach.

    States are compared like for like, which is the difference between an
    instrument and a noise generator. TCP listeners are 0A. A UDP socket that
    is bound and unconnected reads 07, and that is the UDP equivalent of
    listening; a UDP socket in 01 is connected, meaning it is the client side of
    a conversation (a DHCP client at port 68 is the standard example). ss -tuln
    lists only the listening set, so including connected UDP here would
    manufacture a discrepancy on every clean machine on earth.
    """
    rows = []
    try:
        lines = Path(path).read_text().splitlines()
    except OSError:
        return rows
    is_tcp = path.endswith(("tcp", "tcp6"))
    for line in lines[1:]:
        f = line.split()
        if len(f) < 10:
            continue
        state = f[3]
        if listen_only:
            if is_tcp and state != "0A":
                continue
            if not is_tcp and state != "07":
                continue
        hexaddr, hexport = f[1].rsplit(":", 1)
        try:
            port = int(hexport, 16)
        except ValueError:
            continue
        if len(hexaddr) == 8:
            packed = bytes.fromhex(hexaddr)[::-1]
            addr = socket.inet_ntop(socket.AF_INET, packed)
        else:
            raw = bytes.fromhex(hexaddr)
            packed = b"".join(raw[i:i + 4][::-1] for i in range(0, 16, 4))
            try:
                addr = socket.inet_ntop(socket.AF_INET6, packed)
            except (OSError, ValueError):
                addr = hexaddr
        rows.append({"addr": addr, "port": port, "state": state,
                     "uid": f[7], "inode": f[9], "source": path})
    return rows


def hidden_listener_check():
    """ss versus the raw /proc/net tables. Catches a userspace-only rootkit."""
    out = {"check": "hidden_listener", "tier": 4, "tier_note": TIER_NOTES[4],
           "method": "ss -tulpnH versus raw parse of /proc/net/{tcp,tcp6,udp,udp6}"}
    ss = run(["ss", "-tulpnH"])
    if ss.get("status") != "ok":
        out["status"] = "unavailable"
        out["detail"] = ss.get("status")
        return out
    ss_ports = set()
    for line in ss.get("stdout", "").splitlines():
        f = line.split()
        if len(f) < 5:
            continue
        local = f[4]
        if ":" in local:
            tail = local.rsplit(":", 1)[1]
            if tail.isdigit():
                ss_ports.add(int(tail))
    # Both families ask for the listening set. parse_proc_net knows that this
    # means 0A for TCP and 07 for UDP, so the caller does not carry that detail.
    raw = []
    for p in ("/proc/net/tcp", "/proc/net/tcp6", "/proc/net/udp", "/proc/net/udp6"):
        raw.extend(parse_proc_net(p, listen_only=True))
    raw_ports = {r["port"] for r in raw}
    missing = sorted(raw_ports - ss_ports)
    out["status"] = "ok"
    out["ss_ports"] = sorted(ss_ports)
    out["proc_net_ports"] = sorted(raw_ports)
    out["in_proc_not_in_ss"] = missing
    out["raw_rows"] = raw
    out["finding"] = (
        "NONE: ss agrees with the raw kernel tables" if not missing
        else f"DISCREPANCY: {len(missing)} port(s) in /proc/net and absent from ss"
    )
    return out


def deleted_binary_check():
    """A running process whose on-disk executable is gone. Classic implant tell."""
    out = {"check": "deleted_running_binary", "tier": 4, "tier_note": TIER_NOTES[4],
           "method": "readlink(/proc/<pid>/exe) for the (deleted) suffix"}
    hits, unreadable = [], 0
    for pid in sorted(proc_pids_direct()):
        try:
            target = os.readlink(f"/proc/{pid}/exe")
        except (PermissionError, OSError):
            unreadable += 1
            continue
        if target.endswith(" (deleted)"):
            entry = {"pid": pid, "exe": target}
            try:
                entry["comm"] = Path(f"/proc/{pid}/comm").read_text().strip()
                entry["cmdline"] = redact(
                    Path(f"/proc/{pid}/cmdline").read_text(errors="replace").replace("\0", " ").strip()
                )
            except OSError:
                pass
            hits.append(entry)
    out["status"] = "ok"
    out["unreadable_pids"] = unreadable
    out["hits"] = hits
    out["finding"] = (
        "NONE: no process is running from a deleted image" if not hits
        else f"REVIEW: {len(hits)} process(es) running from a deleted image"
    )
    out["note"] = (
        "A deleted image is not proof of compromise. A package upgrade under a "
        "long-lived service produces the same tell, so each hit is judged, not counted."
    )
    return out


def loader_env_check():
    """
    Probe for loader hijack variables only.

    The whole environ block is never recorded: a service API key can sit in one.
    Only the three loader variables are extracted, and their
    values are paths rather than secrets.
    """
    out = {"check": "loader_env", "tier": 4, "tier_note": TIER_NOTES[4],
           "method": "targeted probe of LD_PRELOAD, LD_AUDIT, LD_LIBRARY_PATH",
           "content_policy": "full environ never recorded by design"}
    watch = ("LD_PRELOAD", "LD_AUDIT", "LD_LIBRARY_PATH")
    hits, unreadable = [], 0
    for pid in sorted(proc_pids_direct()):
        try:
            blob = Path(f"/proc/{pid}/environ").read_bytes()
        except (PermissionError, OSError):
            unreadable += 1
            continue
        for item in blob.split(b"\0"):
            if not item or b"=" not in item:
                continue
            k, _, v = item.partition(b"=")
            key = k.decode(errors="replace")
            if key in watch and v:
                hits.append({"pid": pid, "var": key, "value": v.decode(errors="replace")[:512]})
    out["status"] = "ok"
    out["unreadable_pids"] = unreadable
    out["hits"] = hits
    out["global_ld_so_preload"] = read_text("/etc/ld.so.preload")

    # The count of PROCESSES is the wrong unit and it manufactures alarm: a
    # desktop with snap Firefox open shows sixteen of them and every one is the
    # same two shims. The unit that carries signal is the DISTINCT VALUE, and
    # the finding for the standing watch is a value that was not in the sealed
    # baseline. No allowlist is used, deliberately, because an allowlist is how
    # an instrument goes blind to the one thing it was built to see.
    inject = [h for h in hits if h["var"] in ("LD_PRELOAD", "LD_AUDIT")]
    distinct = {}
    for h in inject:
        distinct.setdefault(h["value"], []).append(h["pid"])
    out["distinct_injection_values"] = [
        {"var_class": "LD_PRELOAD/LD_AUDIT", "value": val,
         "process_count": len(pids), "pids": pids[:20]}
        for val, pids in sorted(distinct.items())
    ]
    out["library_path_process_count"] = len(hits) - len(inject)
    out["finding"] = (
        "NONE: no library injection variables set in visible processes" if not distinct
        else f"BASELINE: {len(distinct)} distinct injection value(s) across "
             f"{len(inject)} process(es); the watch flags a NEW value, not a count"
    )
    out["note"] = (
        "LD_LIBRARY_PATH is counted but not treated as injection: it is ordinary on "
        "any CUDA or venv host. LD_PRELOAD and LD_AUDIT are the hijack surface."
    )
    return out


# ---------------------------------------------------------------- collectors

def collect_volatile(privileged):
    """Tier 4, perishable. Everything here dies on reboot, so it goes first."""
    d = {}
    d["discrepancy_hidden_process"] = hidden_process_check()
    d["discrepancy_hidden_listener"] = hidden_listener_check()
    d["discrepancy_deleted_binary"] = deleted_binary_check()
    d["discrepancy_loader_env"] = loader_env_check()

    d["process_table"] = run(
        ["ps", "-eo", "pid,ppid,uid,user,lstart,etimes,stat,tty,args", "--sort=pid"]
    )
    d["process_exe_hashes"] = process_exe_hashes()
    d["listeners"] = run(["ss", "-tulpnH"])
    d["established"] = run(["ss", "-tunpH", "state", "established"])
    d["unix_sockets"] = run(["ss", "-xlpH"])
    d["kernel_modules"] = run(["lsmod"])
    d["modules_raw"] = read_text("/proc/modules")
    d["ebpf_progs"] = run(["bpftool", "prog", "list"], needs_root=True)
    d["ebpf_links"] = run(["bpftool", "link", "list"], needs_root=True)
    d["mounts"] = read_text("/proc/self/mountinfo")
    d["routes_v4"] = run(["ip", "-4", "route", "show"])
    d["routes_v6"] = run(["ip", "-6", "route", "show"])
    d["addresses"] = run(["ip", "-json", "addr", "show"])
    d["neighbors"] = run(["ip", "neigh", "show"])
    d["nft_ruleset"] = run(["nft", "list", "ruleset"], needs_root=True)
    d["iptables"] = run(["iptables", "-S"], needs_root=True)
    d["sessions_who"] = run(["who", "-a"])
    d["sessions_last"] = run(["last", "-n", "50", "-F"])
    d["failed_logins"] = run(["lastb", "-n", "50", "-F"], needs_root=True)
    d["lsof_network"] = run(["lsof", "-nPi"], needs_root=True)
    d["systemd_running"] = run(["systemctl", "--user", "list-units", "--type=service",
                                "--state=running", "--no-pager", "--plain"])
    d["dmesg_tail"] = run(["dmesg", "--ctime", "--level=err,warn"], needs_root=True)
    return d


def process_exe_hashes():
    """Hash the on-disk image behind every visible process."""
    out = {"tier": 4, "tier_note": TIER_NOTES[4], "entries": [], "unreadable": 0,
           "note": "hashes make a later diff meaningful; an unhashed process is not a finding"}
    seen = {}
    for pid in sorted(proc_pids_direct()):
        try:
            target = os.readlink(f"/proc/{pid}/exe")
        except (PermissionError, OSError):
            out["unreadable"] += 1
            continue
        clean = target[:-10] if target.endswith(" (deleted)") else target
        if clean not in seen:
            seen[clean] = sha256_file(clean) if Path(clean).exists() else "absent"
        try:
            comm = Path(f"/proc/{pid}/comm").read_text().strip()
        except OSError:
            comm = None
        out["entries"].append({"pid": pid, "comm": comm, "exe": target, "sha256": seen[clean]})
    out["distinct_images"] = len(seen)
    out["status"] = "ok"
    return out


def collect_persistence(privileged):
    """Tier 3 and 4. Where an implant lives to survive the reboot."""
    d = {}
    d["note"] = (
        "systemd unit CONTENT is already owned by unit_drift.py across all 46 fleet "
        "units. This collector records unit STATE and the surfaces unit_drift does "
        "not cover. It does not duplicate that instrument."
    )
    d["systemd_user_units"] = run(["systemctl", "--user", "list-unit-files", "--no-pager", "--plain"])
    d["systemd_user_timers"] = run(["systemctl", "--user", "list-timers", "--all", "--no-pager"])
    d["systemd_system_units"] = run(["systemctl", "list-unit-files", "--no-pager", "--plain"])
    d["systemd_system_timers"] = run(["systemctl", "list-timers", "--all", "--no-pager"])
    d["systemd_generators"] = list_dir_hashes("/etc/systemd/system-generators")
    d["systemd_user_generators"] = list_dir_hashes("/usr/lib/systemd/user-generators")

    d["crontab_user"] = run(["crontab", "-l"])
    for p in ("/etc/crontab", "/etc/anacrontab"):
        d[f"cron_{Path(p).name}"] = read_text(p)
    for dpath in ("/etc/cron.d", "/etc/cron.daily", "/etc/cron.hourly",
                  "/etc/cron.weekly", "/etc/cron.monthly", "/var/spool/cron/crontabs"):
        d[f"crondir_{Path(dpath).name}"] = list_dir_hashes(dpath)

    home = Path.home()
    for rc in (".bashrc", ".bash_profile", ".bash_login", ".profile", ".zshrc",
               ".bash_logout", ".config/environment.d"):
        d[f"shellrc_{rc.replace('/', '_')}"] = read_text(home / rc)
    d["profile_d"] = list_dir_hashes("/etc/profile.d")
    d["etc_profile"] = read_text("/etc/profile")
    d["xdg_autostart_user"] = list_dir_hashes(home / ".config/autostart")
    d["xdg_autostart_system"] = list_dir_hashes("/etc/xdg/autostart")

    d["ssh_authorized_keys"] = stat_only(home / ".ssh/authorized_keys")
    d["ssh_authorized_keys_fingerprints"] = ssh_key_fingerprints(home / ".ssh/authorized_keys")
    d["sshd_config"] = read_text("/etc/ssh/sshd_config")
    d["sshd_config_d"] = list_dir_hashes("/etc/ssh/sshd_config.d")

    d["pam_d"] = list_dir_hashes("/etc/pam.d")
    d["udev_rules"] = list_dir_hashes("/etc/udev/rules.d")
    d["ld_so_conf_d"] = list_dir_hashes("/etc/ld.so.conf.d")
    d["modprobe_d"] = list_dir_hashes("/etc/modprobe.d")
    d["modules_load_d"] = list_dir_hashes("/etc/modules-load.d")
    d["sudoers_d"] = list_dir_hashes("/etc/sudoers.d")

    d["setuid_binaries"] = run(
        ["find", "/usr", "/bin", "/sbin", "/opt", "-xdev", "-type", "f",
         "-perm", "/6000", "-printf", "%M %u %g %s %p\\n"], timeout=180
    )
    d["package_verify"] = run(["dpkg", "-V"], tier=3, timeout=600)
    d["debsums"] = run(["debsums", "-c"], tier=3, timeout=900)
    d["apt_sources"] = list_dir_hashes("/etc/apt/sources.list.d")
    d["apt_sources_main"] = read_text("/etc/apt/sources.list")
    d["apt_keyrings"] = list_dir_hashes("/etc/apt/keyrings")
    d["apt_history"] = read_text("/var/log/apt/history.log", limit=400_000, tier=3)

    d["credential_inventory"] = credential_inventory()
    d["git_remotes"] = git_remote_audit()
    d["users_passwd"] = read_text("/etc/passwd", tier=3)
    d["groups"] = read_text("/etc/group", tier=3)
    d["shadow_meta"] = stat_only("/etc/shadow")
    return d


def list_dir_hashes(dirpath, tier=4, max_entries=400):
    rec = {"dir": str(dirpath), "tier": tier, "tier_note": TIER_NOTES[tier], "entries": []}
    p = Path(dirpath).expanduser()
    if not p.exists():
        rec["status"] = "absent"
        return rec
    try:
        for child in sorted(p.rglob("*"))[:max_entries]:
            if child.is_dir():
                continue
            rec["entries"].append(stat_only(child, tier=tier))
        rec["status"] = "ok"
        rec["count"] = len(rec["entries"])
    except PermissionError:
        rec["status"] = "permission_denied"
    except Exception as exc:
        rec["status"] = f"error: {type(exc).__name__}"
    return rec


def ssh_key_fingerprints(path):
    """
    Fingerprints of authorized keys, not the keys.

    An unexpected authorized key is one of the cheapest persistence mechanisms
    there is, and a fingerprint list is enough to spot one on a later diff.
    """
    rec = {"path": str(path), "tier": 4, "tier_note": TIER_NOTES[4],
           "content_policy": "fingerprints only, key material never recorded"}
    p = Path(path).expanduser()
    if not p.exists():
        rec["status"] = "absent"
        return rec
    out = run(["ssh-keygen", "-l", "-f", str(p)])
    rec["status"] = out.get("status")
    rec["fingerprints"] = out.get("stdout", "")
    return rec


def credential_inventory():
    """Every credential file by metadata and hash. Contents never read."""
    rec = {"tier": 4, "tier_note": TIER_NOTES[4], "entries": [],
           "content_policy": "metadata and hash only, contents never read by design"}
    home = Path.home()
    for pattern in CREDENTIAL_GLOBS:
        expanded = pattern.replace("~", str(home))
        base = Path(expanded)
        if any(ch in expanded for ch in "*?["):
            parent = base.parent
            if not parent.exists():
                continue
            for match in sorted(parent.glob(base.name)):
                rec["entries"].append(stat_only(match))
        elif base.exists():
            rec["entries"].append(stat_only(base))
    rec["count"] = len(rec["entries"])
    rec["status"] = "ok"
    return rec


def git_remote_audit():
    """
    Every git remote on the box.

    This is the surface that produced two real findings this month: private
    repositories with external remotes that nobody had noticed were there. A
    remote is a data-egress path, so it belongs in the baseline.
    """
    rec = {"tier": 3, "tier_note": TIER_NOTES[3], "repos": []}
    roots = [Path(os.path.expandvars(os.path.expanduser(r)))
             for r in cfg.csv_env("FLEET_REPO_ROOTS", cfg.DEFAULT_REPO_ROOTS)]
    found = 0
    for root in roots:
        if not root.exists():
            continue
        for gitdir in root.rglob(".git"):
            if found >= 300:
                rec["truncated"] = True
                break
            repo = gitdir.parent
            out = run(["git", "-C", str(repo), "remote", "-v"], tier=3, timeout=20)
            branch = run(["git", "-C", str(repo), "rev-parse", "--abbrev-ref", "HEAD"],
                         tier=3, timeout=20)
            rec["repos"].append({
                "path": str(repo),
                "remotes": out.get("stdout", "").strip(),
                "branch": branch.get("stdout", "").strip(),
            })
            found += 1
    rec["count"] = len(rec["repos"])
    rec["status"] = "ok"
    return rec


def collect_firmware(privileged):
    """
    Tier 1 surfaces, read-only.

    This is the transistor question as far as software can carry it. What we can
    do is enumerate every firmware surface, record its version and whatever
    measurement the platform exposes, and compare to a vendor image where one
    exists. What we cannot do is verify the silicon die against the vendor's
    mask. That is decapsulation and electron microscopy, and it is named as the
    residual gap rather than papered over.
    """
    d = {"scope_note": (
        "Firmware VERSIONS and measurements only. SPI flash dumps and offline "
        "comparison are Phase 4 and run from trusted external media with the "
        "operator present, because this node's own OS cannot be the witness to "
        "its own firmware."
    )}
    dmi = {}
    dmi_dir = Path("/sys/class/dmi/id")
    if dmi_dir.exists():
        for f in sorted(dmi_dir.iterdir()):
            if f.is_file():
                try:
                    dmi[f.name] = f.read_text().strip()
                except (PermissionError, OSError):
                    dmi[f.name] = "permission_denied"
    d["dmi_sysfs"] = {"tier": 1, "tier_note": TIER_NOTES[1], "values": dmi}
    d["dmidecode"] = run(["dmidecode"], tier=1, needs_root=True)
    d["cpu_microcode"] = run(["grep", "-m", "4", "-E", "microcode|model name", "/proc/cpuinfo"], tier=1)
    d["secureboot_mokutil"] = run(["mokutil", "--sb-state"], tier=1)
    d["efi_present"] = {"tier": 1, "efivars": Path("/sys/firmware/efi/efivars").exists(),
                        "efi_dir": Path("/sys/firmware/efi").exists()}
    d["tpm_devices"] = list_dir_hashes("/sys/class/tpm", tier=1, max_entries=50)
    d["tpm_pcrs"] = tpm_pcrs()
    d["tpm_event_log"] = {
        "tier": 1,
        "path": "/sys/kernel/security/tpm0/binary_bios_measurements",
        "present": Path("/sys/kernel/security/tpm0/binary_bios_measurements").exists(),
        "note": "root-readable measured-boot log; copied verbatim in the privileged pass",
    }
    d["fwupd_devices"] = run(["fwupdmgr", "get-devices", "--json"], tier=1, timeout=120)
    d["nvidia_gpu"] = run(["nvidia-smi", "--query-gpu=name,serial,uuid,vbios_version,driver_version",
                           "--format=csv"], tier=1)
    d["nic_firmware"] = nic_firmware()
    d["nvme_list"] = run(["nvme", "list"], tier=1, needs_root=True)
    d["block_devices"] = run(["lsblk", "-o", "NAME,MODEL,SERIAL,REV,SIZE,TYPE", "--json"], tier=1)
    d["thunderbolt"] = list_dir_hashes("/sys/bus/thunderbolt/devices", tier=1, max_entries=80)
    d["mst_status"] = run(["mst", "status"], tier=1, needs_root=True)
    d["mlx_firmware"] = run(["mstflint", "-d", "mlx5_0", "query"], tier=1, needs_root=True)
    d["kernel_cmdline"] = read_text("/proc/cmdline", tier=1)
    d["kernel_version"] = run(["uname", "-a"], tier=1)
    d["lockdown"] = read_text("/sys/kernel/security/lockdown", tier=1)
    return d


def tpm_pcrs():
    """
    PCR values, the mechanism that makes future firmware change detectable.

    Once these are sealed in a baseline, a firmware or boot-chain change shows
    as a PCR that no longer matches. That is the difference between "we looked
    once" and "we would know."
    """
    rec = {"tier": 1, "tier_note": TIER_NOTES[1], "banks": {}}
    base = Path("/sys/class/tpm/tpm0")
    if not base.exists():
        rec["status"] = "no_tpm_sysfs"
        return rec
    for bank in sorted(base.glob("pcr-*")):
        vals = {}
        for pcr in sorted(bank.iterdir(), key=lambda p: int(p.name) if p.name.isdigit() else 999):
            if pcr.name.isdigit():
                try:
                    vals[pcr.name] = pcr.read_text().strip()
                except (PermissionError, OSError):
                    vals[pcr.name] = "unreadable"
        rec["banks"][bank.name] = vals
    rec["status"] = "ok" if rec["banks"] else "no_pcr_sysfs"
    return rec


def nic_firmware():
    rec = {"tier": 1, "tier_note": TIER_NOTES[1], "interfaces": {}}
    net = Path("/sys/class/net")
    if not net.exists():
        rec["status"] = "absent"
        return rec
    for iface in sorted(net.iterdir()):
        if iface.name == "lo":
            continue
        rec["interfaces"][iface.name] = run(["ethtool", "-i", iface.name], tier=1, timeout=20)
    rec["status"] = "ok"
    return rec


# --------------------------------------------------------------------- wire

def collect_wire(targets, deep=False):
    """
    Tier 2. Run this FROM an observer node ABOUT the targets.

    This is the tier that makes the fabric assessable. A target cannot forge
    what another machine sees on the wire without owning the observer too, so
    the pairing of this output against a target's own listener list is the
    campaign's highest-value comparison.
    """
    d = {"observer": socket.gethostname(),
         "targets": targets,
         "tier": 2,
         "tier_note": TIER_NOTES[2],
         "method_note": (
             "Run from at least two observers. A single observer that is itself "
             "compromised is a single point of lying."
         )}
    d["tailscale_status"] = run(["tailscale", "status", "--json"], tier=2, timeout=60)
    d["tailscale_netcheck"] = run(["tailscale", "netcheck"], tier=2, timeout=90)
    d["ssh_host_keys"] = ssh_host_key_survey(targets)
    d["scans"] = {}
    for t in targets:
        if shutil.which("nmap"):
            args = ["nmap", "-Pn", "-sT", "--top-ports", "1000", "-oN", "-", t]
            if deep:
                args = ["nmap", "-Pn", "-sT", "-p-", "-sV", "--version-light", "-oN", "-", t]
            d["scans"][t] = run(args, tier=2, timeout=1800 if deep else 600)
        else:
            d["scans"][t] = {"status": "tool_absent", "argv": ["nmap"], "tier": 2,
                             "fallback": python_port_probe(t)}
    return d


def ssh_host_key_survey(targets):
    """
    Every target's SSH host keys, fingerprinted and cross-compared.

    Two jobs in one cheap probe. First, CVE-2026-24218: DGX OS factory
    provisioning cloned a base image such that identical SSH host keys shipped
    across multiple systems, which lets one machine impersonate another. This
    fabric runs two DGX Sparks, so a duplicate fingerprint across nodes is a
    direct hit on a known vulnerability rather than a curiosity. Second, once
    these are in a sealed baseline, a host key that CHANGES without a rebuild is
    one of the loudest signals a fleet can produce.

    Public keys only. Nothing secret is read or written.
    """
    rec = {"tier": 2, "tier_note": TIER_NOTES[2],
           "why": "CVE-2026-24218 cloned-host-key check, plus key-change detection",
           "hosts": {}}
    digests = {}
    for t in targets:
        out = run(["ssh-keyscan", "-T", "10", t], tier=2, timeout=30)
        keys = {}
        for line in out.get("stdout", "").splitlines():
            if line.startswith("#") or not line.strip():
                continue
            parts = line.split()
            if len(parts) < 3:
                continue
            ktype, kdata = parts[1], parts[2]
            fp = hashlib.sha256(kdata.encode()).hexdigest()
            keys[ktype] = fp
            digests.setdefault(fp, []).append(f"{t}/{ktype}")
        rec["hosts"][t] = {"status": out.get("status"), "fingerprints": keys}
    dupes = {fp: who for fp, who in digests.items() if len(who) > 1}
    rec["duplicate_fingerprints"] = dupes
    rec["finding"] = (
        "NONE: every host key is unique across the surveyed nodes" if not dupes
        else f"CVE-2026-24218 CANDIDATE: {len(dupes)} fingerprint(s) shared across hosts"
    )
    return rec


def python_port_probe(host, ports=None):
    """A stdlib fallback so a missing nmap does not stall the wire tier."""
    if ports is None:
        ports = [22, 80, 443, 3000, 5000, 8000, 8080, 8085, 8086, 8088, 8443,
                 9000, 9090, 11434, 5432, 6379, 3306, 2049, 111, 631]
    open_ports = []
    for p in ports:
        s = socket.socket()
        s.settimeout(1.0)
        try:
            if s.connect_ex((host, p)) == 0:
                open_ports.append(p)
        except OSError:
            pass
        finally:
            s.close()
    return {"method": "stdlib connect probe, common ports only",
            "host": host, "open": open_ports,
            "note": "not a substitute for a full nmap sweep"}


# --------------------------------------------------------------------- seal

def seal_run(run_dir):
    """
    Content-address the run and write the seal.

    Cross-custody is what gives this teeth: copy the seal to every other node
    and keep one offline. To rewrite its own history a compromised node would
    have to rewrite the seal everywhere at once, including on paper.
    """
    run_dir = Path(run_dir)
    files = {}
    for f in sorted(run_dir.rglob("*")):
        if f.is_file() and f.name not in ("MANIFEST.json", "MANIFEST.sha256"):
            files[str(f.relative_to(run_dir))] = {
                "sha256": sha256_file(f), "size": f.stat().st_size
            }
    manifest = {
        "tool": "compromise-watch",
        "tool_version": TOOL_VERSION,
        "run_dir": str(run_dir),
        "node": socket.gethostname(),
        "sealed_utc": utcstamp(),
        "file_count": len(files),
        "files": files,
    }
    mpath = run_dir / "MANIFEST.json"
    mpath.write_text(json.dumps(manifest, indent=2, sort_keys=True))
    seal = sha256_file(mpath)
    (run_dir / "MANIFEST.sha256").write_text(
        f"{seal}  MANIFEST.json\n"
        f"# compromise-watch seal, node {socket.gethostname()}, {utcstamp()}\n"
        f"# cross-custody this line to every other node and keep one copy offline\n"
    )
    return {"seal": seal, "files": len(files), "manifest": str(mpath)}


def verify_run(run_dir):
    run_dir = Path(run_dir)
    mpath = run_dir / "MANIFEST.json"
    spath = run_dir / "MANIFEST.sha256"
    if not mpath.exists() or not spath.exists():
        return {"status": "unsealed", "detail": "MANIFEST.json or MANIFEST.sha256 absent"}
    recorded = spath.read_text().split()[0]
    actual = sha256_file(mpath)
    manifest = json.loads(mpath.read_text())
    mismatches = []
    for rel, meta in manifest["files"].items():
        f = run_dir / rel
        if not f.exists():
            mismatches.append({"file": rel, "problem": "missing"})
            continue
        if sha256_file(f) != meta["sha256"]:
            mismatches.append({"file": rel, "problem": "content_changed"})
    return {
        "status": "ok" if (recorded == actual and not mismatches) else "TAMPER_SUSPECTED",
        "seal_recorded": recorded,
        "seal_actual": actual,
        "seal_matches": recorded == actual,
        "file_mismatches": mismatches,
    }


# --------------------------------------------------------------------- main

def write_out(run_dir, name, payload):
    path = run_dir / f"{name}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str))
    return path


def build_meta(mode, privileged, extra=None):
    meta = {
        "tool": "compromise-watch",
        "tool_version": TOOL_VERSION,
        "mode": mode,
        "node": socket.gethostname(),
        "user": pwd.getpwuid(os.geteuid()).pw_name,
        "privileged": os.geteuid() == 0,
        "privileged_requested": privileged,
        "started_utc": utcstamp(),
        "kernel": platform.release(),
        "machine": platform.machine(),
        "python": platform.python_version(),
        "posture": "assume-breach: this host's self-report is tier 4 and is trusted last",
        "readonly": "this tool never modifies system state; it writes only inside its run directory",
    }
    if extra:
        meta.update(extra)
    return meta


def main():
    ap = argparse.ArgumentParser(
        description="compromise-watch: read-only compromise-assessment collector for a fleet"
    )
    ap.add_argument("--root", default=str(DEFAULT_ROOT),
                    help=f"output root (default {DEFAULT_ROOT})")
    sub = ap.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("collect", help="on-host collection, tiers 3 and 4")
    c.add_argument("--tier", choices=["volatile", "persistence", "firmware", "all"],
                   default="all")
    c.add_argument("--privileged", action="store_true",
                   help="acknowledge root-only probes are wanted (run under sudo)")
    c.add_argument("--label", default="baseline", help="run label (default baseline)")

    w = sub.add_parser("wire", help="observer-side collection about other nodes, tier 2")
    w.add_argument("--targets", required=True, help="comma-separated hostnames")
    w.add_argument("--deep", action="store_true", help="all ports plus light service probe")
    w.add_argument("--label", default="baseline")

    s = sub.add_parser("seal", help="content-address and seal a run directory")
    s.add_argument("run_dir")

    v = sub.add_parser("verify", help="re-verify a sealed run directory")
    v.add_argument("run_dir")

    args = ap.parse_args()

    if args.cmd == "seal":
        print(json.dumps(seal_run(args.run_dir), indent=2))
        return 0
    if args.cmd == "verify":
        result = verify_run(args.run_dir)
        print(json.dumps(result, indent=2))
        return 0

    root = Path(args.root)
    node = socket.gethostname()
    run_dir = root / args.label / node / utcstamp()
    run_dir.mkdir(parents=True, exist_ok=True)

    if args.cmd == "collect":
        meta = build_meta("collect", args.privileged, {"tier_requested": args.tier})
        write_out(run_dir, "meta", meta)
        started = time.time()
        if args.tier in ("volatile", "all"):
            print("collecting volatile (tier 4, perishable)", file=sys.stderr)
            write_out(run_dir, "volatile/volatile", collect_volatile(args.privileged))
        if args.tier in ("persistence", "all"):
            print("collecting persistence (tiers 3 and 4)", file=sys.stderr)
            write_out(run_dir, "persistence/persistence", collect_persistence(args.privileged))
        if args.tier in ("firmware", "all"):
            print("collecting firmware (tier 1 surfaces, read-only)", file=sys.stderr)
            write_out(run_dir, "firmware/firmware", collect_firmware(args.privileged))
        meta["finished_utc"] = utcstamp()
        meta["elapsed_s"] = round(time.time() - started, 2)
        write_out(run_dir, "meta", meta)

    elif args.cmd == "wire":
        targets = [t.strip() for t in args.targets.split(",") if t.strip()]
        meta = build_meta("wire", False, {"targets": targets, "deep": args.deep})
        write_out(run_dir, "meta", meta)
        started = time.time()
        print(f"scanning {len(targets)} target(s) from {node} (tier 2)", file=sys.stderr)
        write_out(run_dir, "wire/wire", collect_wire(targets, deep=args.deep))
        meta["finished_utc"] = utcstamp()
        meta["elapsed_s"] = round(time.time() - started, 2)
        write_out(run_dir, "meta", meta)

    sealed = seal_run(run_dir)
    print(json.dumps({"run_dir": str(run_dir), **sealed}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
