# Striker onboarding: standing up a CUDA workstation

The repeatable onboarding pattern (`node-onboarding.md`) pointed at the specific case of
a new x86 CUDA workstation: the node that carries a consumer Blackwell card and serves
LoRA adapters in weights. It consolidates the migration addenda into one runnable
sequence and names where a CUDA workstation departs from the patterns the rig already
runs.

The striker is the muscle behind a face: the workstation that has the room to be the
multi-adapter LoRA server the twin nodes, full at their model size, are not.

## Which pattern the striker follows, and where it forks

The rig runs two serving patterns. The striker inherits one and forks it:

| | twin nodes | integrated-GPU node | striker |
|---|---|---|---|
| silicon | GB10-class ARM aarch64 | Strix Halo, x86, ROCm | RTX 5090-class, x86, CUDA |
| serving | vLLM in docker, `--gpus all` | llama.cpp Vulkan/ROCm | vLLM in docker, `--gpus all` |
| onboarding tier | container pull | per-node ROCm scripts | a new CUDA tier |

**The striker follows the twin pattern, not the integrated-GPU pattern.** The integrated
node's onboarding scripts are ROCm and do not transfer. The twin unit is the template.

Three deltas from the twins, all inference until the box is on the bench:

1. **Architecture.** The twins are ARM aarch64; the striker is x86_64. The
   `vllm/vllm-openai` image is multi-arch, so the same tag should pull the x86 variant
   with no change. Verify the pulled image architecture on first run.
2. **GPU compute capability.** The twins are datacenter Blackwell; a 5090 is consumer
   Blackwell, **sm_120**. The twins' pinned vLLM tag may or may not carry sm_120 kernels.
   This is the upgrade-routine case exactly: controlled bring-up beside a known-good tag,
   never an in-place clobber. Test the pinned tag first and step forward if sm_120 is
   unserved. Adjacent compute capabilities (sm_121) are related but not the same, so
   re-test rather than assume.
3. **Model fit.** A 32GB card cannot hold a large NVFP4 model the twins run (~70GB+). The
   striker serves a base that fits 32GB (a 26B or 32B class model) **plus LoRA adapters**,
   which is its whole reason to exist. Model choice is an operator call downstream of
   this onboarding, not part of it.

## The universal sequence

The full sequence is `node-onboarding.md`. Run in order. Striker-specific notes:

### 0. Prerequisite (one-time, needs sudo)

The shared runtime directory must exist and be user-owned:
`sudo mkdir -p /srv/fabric && sudo chown "$USER":"$USER" /srv/fabric`.

### 1. Clone the repo

Clone the control plane and serving code. A new node gets the distributable software
only; the operator's umbrella tree stays home (a per-node decision, not a default).

### 2. Rebuild the service venv on the system python

```
service-kit/rebuild-service-venv.sh <repo>/.venv <pkg> [<pkg>]+
```

Uses the **system** interpreter, NOT a package-manager-managed one, so the venv survives
a garbage collection of that interpreter or a reboot. The lock is the floor. This is the
decoupling that makes a node's keeper reboot-immune; the striker matches that floor from
day one.

### 3. Units from the twin template

The striker's serving unit is the twin's docker vLLM unit with three edits: the node's
own overlay IP in the bind, the model path, and the served-model-name. The recorded twin
`ExecStart` is the reference.

**The two guards that are not optional, both learned the hard way:**

- **The boot bind race.** Drop `service-kit/wait-for-tailnet.conf` into
  `~/.config/systemd/user/<unit>.service.d/`. Every unit binds its node's overlay IP, and
  at boot the user manager starts before the overlay daemon assigns it. Ordering does not
  fix it (the daemon is a system unit, these are user units). The polling guard crosses
  that namespace boundary. Costs about 4ms when the address is already up.
- **Enable, do not just start.** `systemctl --user enable --now <unit>` for every resident
  service. Linger plus enabled is what makes the board reboot-durable. A started but
  not-enabled unit comes back dark after a power cycle. Lazy and staged services
  correctly stay disabled.

### 4. Register the service in the roster

Identity is config-as-identity in the roster TOMLs, loaded by the registry, checked by
the registry's golden test. Roster edits need a view restart to take.

### 5. Board-verify at the wire

Ask the board (`GET /api/health`, `GET /api/services`) through the view. The service should
show alive with sane latency. A chat or vision smoke call confirms the relay path end to
end.

## The bind posture, stated so it is not rediscovered

Every service binds its node's overlay IP, one posture fleet-wide, zero exceptions. The
striker binds its own overlay IP, never loopback, never `0.0.0.0` except where a service
already does. This is why the boot-race guard is mandatory rather than nice-to-have.

## First light on the metal

Ground truth from standing up the first CUDA striker. The unknowns above are now
measured, and the gotchas are recorded so the next node does not rediscover them.

- **sm_120 is served, unknown RESOLVED.** RTX 5090, driver 595.84-open, CUDA 13.2, 32GB.
  The standard driver lights it up with no fight. Secure Boot was enabled and the card
  still loaded, because the `-open` kernel-module package is signed; the open driver
  variant is what dodges the MOK dance, so prefer it.
- **The engine serves consumer Blackwell too, RESOLVED.** The pinned vLLM tag served an
  sm_120 card: an FP8 vision model compiled clean (torch.compile 12.8s, CUDA graphs) and
  answered end-to-end. The install-day matmul proved the container; this proves the
  engine.
- **Ubuntu Desktop ships no `openssh-server`.** A fresh Desktop install is unreachable by
  SSH until `sudo apt install -y openssh-server`. Do NOT lean on Tailscale SSH as the
  path: its check-mode holds a headless connection open with no banner and reads as a
  hang (cost an hour). Install real `sshd`, `sudo tailscale set --ssh=false`, drop the
  node's key.
- **Audit `/etc/apt/sources.list.d/` before installing anything.** Prior driver or
  SDK attempts leave apt sources whose keyring files are **0 bytes**, and every
  `apt update` then fails on GPG verification. Disable the strays (rename to
  `.disabled`) first.
- **A confined snap Docker breaks GPU passthrough; the box must run ONE unconfined
  apt/deb Docker.** THE ROOT CAUSE, confirmed. The first striker shipped with a snap
  Docker already running beside the apt `docker.io`: two daemons, two toolkit
  integrations. The snap daemon is confined, and its sandboxed filesystem view is why
  `--gpus all` failed to mount a present file, reading it as "no such file or directory"
  at container init. This cost a morning and two wrong roads first. `snap list | grep
  docker` on a new box finds it in ten seconds, so **check that first.** The fix:
  `sudo snap remove docker`, then bring the apt daemon up. Cleanup wrinkle: after the
  snap leaves, `docker.socket` may not recreate `/run/docker.sock`, so
  `sudo systemctl stop docker; sudo systemctl restart docker.socket; sudo systemctl
  start docker` finishes the handoff. Result: one unconfined daemon and the standard
  `--gpus all` works, verified from a non-interactive SSH session, which is what the
  units need.
- **Run `sudo -v` before pasting a multi-line sudo block.** The first `sudo` password
  prompt otherwise eats the pasted lines behind it and writes 0-byte files.
- **The desktop compositor holds about 600MiB VRAM** (Xorg plus gnome-shell). Harmless
  on 32GB, but `sudo systemctl set-default multi-user.target` reclaims it if the box
  goes headless, no reinstall needed.

## What this onboarding sets up but does not do

The striker's purpose is an adapters-in-weights build, and that is a separate lane gated
on the box being present and on an operator call:

- **Base model choice** for the LoRA server (a 26B or 32B that fits 32GB with adapter
  headroom).
- **The training lane**, which points at a new target rather than being built new.
  Training data is abundant: the journal, the archived session text, months of in-voice
  writing.
- **The deterministic style gate.** A stream-layer filter that stripped em dashes and
  ellipses was deleted in favor of moving mechanical style rules to a post-generation
  gate on artifact-producing paths. That gate did not exist at the time and is the
  mechanical half of the weights migration. Flagged, not built.

## Addendum: the build role (portable toolchains)

The striker also serves as the app build box. Everything lives on a single toolchain
shelf, no sudo required for any of it:

- A Flutter stable **git clone** (not a snap), revision pinned, engine artifacts
  precached. Deliberate divergence from a snap install: a git clone pins and never
  auto-updates under the rig's provenance discipline.
- A portable JDK tarball (Temurin LTS).
- The Android SDK under the same shelf: cmdline-tools, platform-tools, a platform, a
  build-tools version, all licenses accepted. No emulator by design; physical device
  sideloads only.
- Wiring: `JAVA_HOME`, `ANDROID_HOME`, and `PATH` in the shell profile; the framework's
  own config carries `--android-sdk` and `--jdk-dir` so builds do not depend on the shell
  environment.
- Linux desktop dependencies are apt packages and the operator's hands.

One trap for the record: `sdkmanager` aborts its whole transaction when any requested
package name is unknown, and still reads as a clean exit in a pipeline. A nonexistent
platform name next to a valid build-tools name sank the first run; the retry seated a
real platform and the doctor went green.

## Addendum: Tailscale native, never the snap

A first build may install Tailscale via the Canonical snap. Its strict confinement
exposes no home interface, so Taildrop-send from a user's home directory fails (EACCES
even under sudo; `/tmp` and a data dir fail ENOENT under the snap's PrivateTmp and
restricted mount namespace). Migrate to the native apt package (pkgs.tailscale.com),
preserving the node identity by carrying the daemon state across so the node kept its
address with no re-auth. A guarded migration removes the snap only after the native
daemon verifies up on the same address, else it rolls back.

Onboarding rule: a new node gets Tailscale from the native apt repo, not the snap.

Floor: no em dashes, no ellipses.
