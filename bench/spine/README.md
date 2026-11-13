# The bench spine

Publishable projection of the masashi-tune bench tapes. Built 2026-11-13 on the
operator's ruling for c-0054: ship the raw run tapes so aggregate numbers are
independently reproducible, without shipping the raw text.

## Where the tapes are, measured

`~/besaid/memory/operational/bench/runs` holds 54 jsonl files, 29 MiB, 48,035
rows. The card that requested this spine cited `local/spira/bench/runs`, which no
longer exists; the tapes moved into the memory tree's operational lane. That tree
is gitignored by the besaid repo (`/memory/operational/bench/`, line 86), so the
tapes are untracked working material. That is the reason a spine is needed at all
rather than a push of the directory.

## Why it is a whitelist and not a column drop

The tapes are twenty different row shapes, not one schema. 30,727 rows carry
`parsed`, 25,846 carry `relpath`, 22,278 carry `fields`, 4,872 carry `raw`, 2,098
carry `read`, 1,263 carry `error`. `relpath` is a document path and carries real
filenames including personal surnames, and `raw`/`parsed`/`fields` can carry model
input or output.

So the projection is a whitelist applied per row. Anything not named in the
whitelist is omitted whether or not the build understands it, which means a future
tapen shape cannot leak by being new.

## Included

Measurement and identity, nothing that names a document or carries its text:

`seat`, `phase`, `pass`, `kind`, `task`, `anchor`, `anchor_set`, `anchor_sha256`,
`seconds`, `secs`, `wall`, `ttft`, `ttft_s`, `t`, `i`, `prompt_chars`,
`out_chars`, `prompt_tokens`, `completion_tokens`, `target_tokens`, `tg_tok_s`,
`tokens`, `finish`, `parse_ok`, `ok`, `n_fields`, `n`, `qdepth`, `lateness_s`,
`node`, `vendor`, `devices`, `power_w_total`, `ts`.

Plus `_source`, the tape filename, so any spine row can be traced back to the run
it came from without the spine naming a document.

## Excluded, and why

- `relpath`: document paths with personal surnames.
- `raw`, `parsed`, `fields`, `candidate`, `read`: model input or output.
- `error`: free text, and routinely a filesystem path. A failure is still visible
  as `ok` / `parse_ok`; only the message is dropped.

## Rebuild

```
cd ~/besaid/buntas-tofu/masashi-tune
python3 bench/spine/build_spine.py --out bench/spine/bench_spine_<date>.jsonl
```

The build re-reads its own output and fails if any denylisted KEY survived. It
checks keys rather than the text, because a substring check matches a value that
happens to be the word "read" and reports a leak that is not one.
