# Service kit: venvs, keepers, and the boot race

Four small pieces that keep a fabric's long-running services honest on any node. They
are the recipe half of node onboarding; the prose half is `node-onboarding.md` and
`runtime-cutover.md` next door.

- `rebuild-service-venv.sh` - rebuild a service venv on the stable system python.
- `check-service-venvs.sh` - the zombie detector: does the binary systemd would
  re-exec actually exist on disk.
- `service-venv.lock` - the pinned floor the rebuild installs against.
- `wait-for-tailnet.conf` - the systemd drop-in that waits for the overlay address
  before a unit binds it.

Every deployment-specific value is an environment variable or an argument with a
documented default. Nothing here names a node, a user, or a home directory.

## Why the venv recipe matters

A venv is not relocatable. Its entry scripts and shebangs bake the absolute path they
were created at, so moving the directory (a repo lift, a rename, a new disk) leaves a
venv that imports fine from a shell that happens to have the right `PYTHONPATH` and
fails the moment systemd re-execs it. The symptom is silent: the process that is
already running holds its deleted files open and looks healthy until the next restart
or reboot, when it simply does not come back.

Two rules follow, and both are cheap:

1. Build the service venv on the **system** python, never on a package manager's
   managed interpreter. A uv-managed standalone python can be relocated or garbage
   collected out from under you; the system interpreter stays put.
2. After any move of the repo or the venv, rebuild from the lock rather than editing
   the old venv in place:

   ```
   rebuild-service-venv.sh <new-venv-path> <pkg> [<pkg>]+
   ```

   The script installs each named package as an editable install from `<script-dir>/<pkg>`
   and constrains everything to `service-venv.lock`. Restart the affected units, then
   run `check-service-venvs.sh` and require exit 0.

## The rebuild sequence, in order

This is the sequence that closes a repo move, and it is the same on every node:

1. Stop the venv-backed units.
2. Repoint every `ExecStart` and `WorkingDirectory` that names the old path.
3. Rebuild the venv against the new path from the lock (see rule 2 above).
4. Install the repo's **own** packages editable, then import them to prove it. A
   requirements file that lists only third-party dependencies will always look
   complete; the repo's own packages are not in it, and nothing else checks.
5. Start the units.
6. `check-service-venvs.sh` must exit 0.
7. Re-capture the unit record (whatever tooling records unit files and their hashes).

Steps 3 and 4 are the two that get skipped, and both fail silently. Step 4 in
particular only surfaces when something finally imports the package, which can be days
later and on a different node.

## The boot race

Every unit that binds its node's overlay address is racing the overlay daemon at boot.
The unit's user manager starts before the daemon has assigned the address, and binding
an address that does not exist yet fails instantly. `wait-for-tailnet.conf` is dropped
into the unit's drop-in directory and polls until the address is up. It costs
milliseconds when the address is already assigned and reverts by deleting the file.
The reasoning for why unit ordering cannot fix this is in the conf's own header, and
in `runtime-cutover.md`.

## Install the drop-in

```
mkdir -p "$HOME/.config/systemd/user/<unit>.service.d"
cp wait-for-tailnet.conf "$HOME/.config/systemd/user/<unit>.service.d/"
systemctl --user daemon-reload
```

Do this for every binding unit **before** the node's first boot. The conf needs no
restart to take effect once dropped in.

Floor: no em dashes, no ellipses.
