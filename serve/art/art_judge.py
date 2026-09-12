#!/usr/bin/env python3
"""Gemma eyes on plates: the art lane's judge, gated.

The loop (2026-07-18): the generator proposes, a vision model critiques
against a fixed rubric, a curator keeps the survivors. Each candidate PNG
rides to the view's /api/vision as a data URI; the model returns strict JSON
scores plus a one-line flaw note.

GATED 2026-07-30, after the judgment audit flagged this as the worst surface
on the rig. The original sorted a gallery on the model's own `verdict` field:
one unpinned draw of a 1-to-10 ordinal, written to disk, with a curator
choosing from the ranking.

That is worse than the same defect in a text report, and the reason is the
failure MODE. A false positive in a ranked report is a wrong row you can argue
with. Here it sorts a good plate below the fold and it is never seen. The
failure is an absence, and an absence does not announce itself.

Four gates, weakest to strongest:

  PIN. /api/vision accepts a temperature override (VisionReq, forwarded by
  _overrides). A scored stage runs greedy. This is the cheap one and it fixes
  the least.

  FLOOR. The commission makes claims that are measurable off the pixels
  without asking anybody: SNES-era discipline means a bounded palette, "black
  background" means dark borders, and a degenerate render has near-zero
  variance. A plate failing the floor cannot ride a generous verdict into the
  top band. The model proposes taste; the pixels dispose on fact.

  DERIVE. The rubric already asks for four component scores and nine inventory
  booleans, and then asks the seat to summarise its own answer as `verdict`.
  Booleans were measured at 97 to 100 percent reproducible on 2026-07-29 and a
  fine ordinal at 58. So the ranking is computed from the observations and the
  seat's own summary is kept beside it as a cross-check. Where a seat's verdict
  disagrees with its own observations, that divergence is printed, because it
  is a better signal than either number alone.

  BAND. A single read is not a measurement (2026-07-29). Plates
  are read K times and the observed spread sets a band width. Plates inside one
  band are TIED and printed unordered. False precision is how a good plate ends
  up below the fold, so the report refuses to express an order it cannot
  support.

Nothing here decides what is good. It decides what the machine is allowed to
claim, and makes ties look like ties.

Usage: art_judge.py out/*.png  [--model gemma] [--reads 2]
"""

import argparse
import base64
import json
import os
import re
import statistics
import sys
import time
from pathlib import Path

# The view client comes from the serving harness. Point VIEW_HARNESS at a
# directory that provides `harness.view.ViewClient`, an SSE chat and vision
# client (see the design note in this folder).
_harness = os.environ.get("VIEW_HARNESS")
if _harness:
    sys.path.insert(0, _harness)
from harness.view import ViewClient  # noqa: E402

RUBRIC = """You are the art critic for a pixel-art build. Judge this ONE image
against the commission: an isometric pixel-art diorama of a cozy bar interior
on a black background, SNES-era discipline, warm amber palette, and enough
open floor for character sprites to stand and walk.

Return ONLY a JSON object, no prose, no fences, exactly these keys:
{"iso_coherence": 1-10, "pixel_discipline": 1-10, "palette_warmth": 1-10,
 "sprite_room": 1-10,
 "inventory": {"counter": bool, "stools": bool, "back_bar_bottles": bool,
   "chalkboard": bool, "crt_tv": bool, "jukebox": bool, "pinball": bool,
   "neon_sign": bool, "pendant_lamps": bool},
 "flaws": "one short line",
 "verdict": 1-10}"""


SCORES = ("iso_coherence", "pixel_discipline", "palette_warmth", "sprite_room")
INVENTORY = ("counter", "stools", "back_bar_bottles", "chalkboard", "crt_tv",
             "jukebox", "pinball", "neon_sign", "pendant_lamps")

# Floor thresholds. Deliberately generous: the floor exists to catch a render
# that CANNOT satisfy the commission, never to express taste. Every threshold
# here was checked against all ten real plates before it was allowed to gate.
MAX_BORDER_LUMA = 40    # "on a black background", 0-255 mean over the frame
MIN_STDDEV = 8          # a near-uniform image is a failed render, not a plate

# NOT a gate, measured and reported only.
#
# The first cut of this floor capped the palette at 4096 on the reasoning that
# SNES-era discipline means bounded colour. It floored ALL TEN plates including
# v2_plate_s55, the hero that was kept. The check is invalid rather than
# mistuned: these are diffusion renders IN a pixel-art style, not indexed pixel
# art, so they carry 121k to 179k distinct colours while looking correctly
# blocky. Palette count measures the encoding, not the discipline, and no
# threshold exists that keeps the crowned plate and rejects anything.
#
# Left in the report as a diagnostic because the number is still interesting,
# and left out of the gate because a floor may only assert what is true of
# every good plate. Observed range on real work: border luma 0.0 to 1.6,
# stddev 47.4 to 55.2, palette 121k to 179k.
REPORT_ONLY = ("palette",)


class VisionClient(ViewClient):
    """The chat() SSE loop, pointed at /api/vision."""

    def vision(self, seat: str, prompt: str, images: list[str],
               max_tokens: int = 900, temperature: float | None = 0.0) -> str:
        body = {"seat": seat, "prompt": prompt, "images": images,
                "max_tokens": max_tokens}
        # Scored stage, so greedy by default. VisionReq carries temperature and
        # server._overrides forwards it; omitting it inherits the vessel's
        # conversational 0.6, which is what made this a single draw.
        if temperature is not None:
            body["temperature"] = temperature
        content = ""
        event = ""
        with self._client.stream(
                "POST", f"{self.base_url}/api/vision", json=body) as resp:
            resp.raise_for_status()
            for line in resp.iter_lines():
                if not line:
                    continue
                if line.startswith("event:"):
                    event = line.split(":", 1)[1].strip()
                    continue
                if not line.startswith("data:"):
                    continue
                try:
                    data = json.loads(line.split(":", 1)[1].strip())
                except json.JSONDecodeError:
                    continue
                if event == "content":
                    content += data.get("text", "")
        return content


def parse_verdict(text: str) -> dict | None:
    """Tolerant JSON pull: seats sometimes fence or preamble despite orders."""
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


def validate(rec: dict) -> list[str]:
    """Schema gate. Catches a malformed verdict; it cannot catch a well-formed
    wrong one, which is exactly why it is the weakest of the four."""
    errs = []
    for k in SCORES + ("verdict",):
        v = rec.get(k)
        if not isinstance(v, (int, float)) or not 1 <= v <= 10:
            errs.append(f"{k} not a 1-10 number ({v!r})")
    inv = rec.get("inventory")
    if not isinstance(inv, dict):
        errs.append("inventory missing or not an object")
    else:
        for k in INVENTORY:
            if not isinstance(inv.get(k), bool):
                errs.append(f"inventory.{k} not boolean ({inv.get(k)!r})")
    return errs


def pixel_floor(path: Path) -> dict:
    """Measure the commission's mechanical claims off the image itself.

    No model involved and no taste expressed. These are the things the rubric
    asserts that a picture either does or does not do, so a seat cannot talk a
    plate past them.
    """
    try:
        from PIL import Image, ImageStat
    except ImportError:
        return {"floor": "unavailable", "reasons": ["PIL not installed"]}
    try:
        with Image.open(path) as im:
            im = im.convert("RGB")
            w, h = im.size
            palette = len(im.getcolors(maxcolors=1 << 24) or [])
            stdev = statistics.mean(ImageStat.Stat(im.convert("L")).stddev)
            # Mean luminance of a 6 percent frame around the edge.
            g = im.convert("L")
            band = max(2, int(min(w, h) * 0.06))
            edge = [g.crop((0, 0, w, band)), g.crop((0, h - band, w, h)),
                    g.crop((0, 0, band, h)), g.crop((w - band, 0, w, h))]
            border = statistics.mean(ImageStat.Stat(e).mean[0] for e in edge)
    except Exception as e:
        return {"floor": "unreadable", "reasons": [f"{type(e).__name__}: {e}"]}

    reasons = []
    if border > MAX_BORDER_LUMA:
        reasons.append(f"border luma {border:.0f} > {MAX_BORDER_LUMA}, "
                       "background is not black")
    if stdev < MIN_STDDEV:
        reasons.append(f"stddev {stdev:.1f} < {MIN_STDDEV}, degenerate render")
    return {"floor": "pass" if not reasons else "FAIL", "reasons": reasons,
            "palette": palette, "border_luma": round(border, 1),
            "stddev": round(stdev, 1), "size": f"{w}x{h}"}


def derived_score(rec: dict) -> float:
    """Rank on what the seat OBSERVED, not on how it summarised itself.

    The four component scores and the nine inventory booleans are the seat's
    observations. `verdict` is the seat re-reading its own answer and
    compressing it to one ordinal, which is the least reproducible shape it
    produces. Weighting is deliberately plain so it can be argued with: the
    components carry 70 percent, inventory completeness 30.
    """
    comp = statistics.mean(float(rec[k]) for k in SCORES)
    inv = rec.get("inventory") or {}
    present = sum(1 for k in INVENTORY if inv.get(k)) / len(INVENTORY)
    return round(comp * 0.7 + present * 10 * 0.3, 2)


def band(rows: list[dict], width: float) -> list[list[dict]]:
    """Group plates whose derived scores are closer together than the
    instrument can distinguish. Inside a band there is no order, and the
    report says so rather than inventing one."""
    live = sorted([r for r in rows if r.get("derived") is not None],
                  key=lambda r: -r["derived"])
    out: list[list[dict]] = []
    for r in live:
        if out and out[-1][0]["derived"] - r["derived"] <= width:
            out[-1].append(r)
        else:
            out.append([r])
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("plates", nargs="+")
    ap.add_argument("--model", default=os.environ.get("JUDGE_VISION_MODEL",
                                                       "gemma"))
    ap.add_argument("--reads", type=int, default=2,
                    help="reads per plate; a single read is not a measurement")
    ap.add_argument("--temperature", type=float, default=0.0)
    args = ap.parse_args()

    client = VisionClient(archive=False)
    results, spreads = [], []
    for path in args.plates:
        p = Path(path)
        floor = pixel_floor(p)
        uri = ("data:image/png;base64,"
               + base64.b64encode(p.read_bytes()).decode())
        row: dict = {"plate": p.name, **{f"floor_{k}": v
                                         for k, v in floor.items()}}

        reads, errors = [], []
        t0 = time.time()
        for i in range(max(1, args.reads)):
            try:
                raw = client.vision(args.model, RUBRIC, [uri],
                                    temperature=args.temperature)
            except Exception as e:   # a dark seat must not kill the gallery
                errors.append(f"read{i}: {e}")
                continue
            rec = parse_verdict(raw)
            if rec is None:
                errors.append(f"read{i}: unparseable")
                continue
            errs = validate(rec)
            if errs:
                errors.append(f"read{i}: {'; '.join(errs[:3])}")
                continue
            reads.append(rec)
        row["elapsed_s"] = round(time.time() - t0, 1)
        row["reads_ok"] = len(reads)
        if errors:
            row["read_errors"] = errors

        if not reads:
            row["derived"] = None
            row["status"] = "NO VALID READ"
        else:
            ds = [derived_score(r) for r in reads]
            spread = round(max(ds) - min(ds), 2)
            spreads.append(spread)
            first = reads[0]
            row.update({k: first.get(k) for k in SCORES})
            row["inventory"] = first.get("inventory")
            row["flaws"] = first.get("flaws", "")
            row["seat_verdict"] = first.get("verdict")
            row["derived"] = round(statistics.mean(ds), 2)
            row["spread"] = spread
            # The seat's own summary against the seat's own observations.
            row["divergence"] = round(
                float(first.get("verdict", 0)) - row["derived"], 2)
            row["status"] = "FLOORED" if floor.get("floor") == "FAIL" else "ok"
        results.append(row)
        print(f"[judge] {p.name}: derived {row.get('derived', '-')} "
              f"(seat said {row.get('seat_verdict', '-')}), "
              f"floor {floor.get('floor')}, {row['reads_ok']}/{args.reads} "
              f"reads ok, {row['elapsed_s']}s", flush=True)

    # Band width from the measured instrument, never a guessed constant. If
    # every plate read identically, fall back to a floor of 0.5 so exactly
    # equal scores still band together.
    width = max(0.5, max(spreads) if spreads else 0.0)
    floored = [r for r in results if r.get("status") == "FLOORED"]
    dead = [r for r in results if r.get("derived") is None]
    ranked = band([r for r in results
                   if r.get("derived") is not None and r not in floored], width)

    out_dir = Path(args.plates[0]).parent
    report = out_dir / f"JUDGE_{time.strftime('%Y%m%d-%H%M')}.md"
    L = [f"# Plate gallery, judged by {args.model}", "",
         f"{len(results)} plates, {args.reads} reads each at temperature "
         f"{args.temperature}. Band width **{width}**, taken from the largest "
         "observed read-to-read spread, so plates inside one band are tied and "
         "printed unordered. Rank is DERIVED from the component scores and "
         "inventory; the seat's own `verdict` is shown beside it as a "
         "cross-check, never as the sort key.", ""]

    for i, grp in enumerate(ranked, 1):
        tie = "  (tied, no order within band)" if len(grp) > 1 else ""
        L += [f"## Band {i}{tie}", "",
              "| plate | derived | seat said | spread | iso | pixels | palette "
              "| room | missing | flaws |", "|---|---|---|---|---|---|---|---|---|---|"]
        for r in sorted(grp, key=lambda d: d["plate"]):
            inv = r.get("inventory") or {}
            missing = ", ".join(k for k in INVENTORY if not inv.get(k)) or "-"
            div = f" ({r['divergence']:+})" if r.get("divergence") else ""
            L.append(f"| {r['plate']} | **{r['derived']}** | "
                     f"{r.get('seat_verdict')}{div} | {r.get('spread')} | "
                     f"{r.get('iso_coherence')} | {r.get('pixel_discipline')} | "
                     f"{r.get('palette_warmth')} | {r.get('sprite_room')} | "
                     f"{missing} | {r.get('flaws','')} |")
        L.append("")

    if floored:
        L += ["## Floored (failed the pixel gate, held out of the bands)", "",
              "These did not lose on taste. They failed a measurable claim the "
              "commission makes, so no verdict can carry them up.", "",
              "| plate | why | palette | border luma | stddev | seat said |",
              "|---|---|---|---|---|---|"]
        for r in sorted(floored, key=lambda d: d["plate"]):
            L.append(f"| {r['plate']} | {'; '.join(r.get('floor_reasons', []))} "
                     f"| {r.get('floor_palette')} | {r.get('floor_border_luma')} "
                     f"| {r.get('floor_stddev')} | {r.get('seat_verdict')} |")
        L.append("")

    if dead:
        L += ["## No valid read (named, never dropped)", ""]
        for r in dead:
            L.append(f"- `{r['plate']}`: {'; '.join(r.get('read_errors', []))}")
        L.append("")

    report.write_text("\n".join(L) + "\n")
    print(json.dumps(results, indent=1))
    print(f"[judge] gallery written: {report}", flush=True)
    print(f"[judge] band width {width}, {len(ranked)} bands, "
          f"{len(floored)} floored, {len(dead)} unread", flush=True)


if __name__ == "__main__":
    main()
