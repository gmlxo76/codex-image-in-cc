#!/usr/bin/env python3
"""sheetfit — strict animation sprite-sheet normalizer.

AI image generators draw each animation frame independently, so a generated
sprite sheet has frames at slightly different sizes/positions and an uneven grid.
A straight grid-slice of such a sheet jitters when played.

sheetfit makes an AI sheet engine-ready by:
  1. Detecting the TRUE frame grid via transparent GUTTERS (gaps between frames),
     which is robust to uneven AI spacing — NOT a naive even division.
  2. Tightly trimming each frame's content.
  3. Sizing every output cell identically (max frame extent + padding).
  4. Re-anchoring each frame consistently (bottom-center by default) and
     recomposing into ONE corrected sheet (cols*cellW x rows*cellH).
  5. STRICT (adversarial) verification: if it cannot find cols-1 clean column
     gutters and rows-1 clean row gutters, or any cell is empty, it FAILS with
     status "rework" — meaning the source must be regenerated (label-free,
     transparent gutters, strict grid). When in doubt, it fails.

Output is a single engine-ready sheet: Unity "Sprite Mode = Multiple ->
Grid by Cell Count (cols x rows)" yields registered frames (no jump).

Prints exactly one machine-readable line:  SHEETFIT {json}
Exit 0 = pass/fixed (engine-ready).  Exit 1 = rework needed.  Exit 2 = usage/dep error.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    import numpy as np
    from PIL import Image
except ImportError as exc:  # pragma: no cover
    sys.stderr.write(
        "sheetfit.py requires Pillow and numpy.\n  pip install Pillow numpy\n"
        f"  (missing: {exc.name})\n"
    )
    sys.exit(2)

ALPHA_THRESH = 16  # alpha above this counts as "content"


def parse_grid(text: str):
    t = str(text).lower().replace("×", "x")
    parts = t.split("x")
    if len(parts) != 2:
        raise argparse.ArgumentTypeError(f"grid must be COLSxROWS, got {text!r}")
    return int(parts[0]), int(parts[1])


def content_mask(alpha: np.ndarray) -> np.ndarray:
    return alpha > ALPHA_THRESH


def global_bbox(mask: np.ndarray):
    ys, xs = np.where(mask)
    if len(xs) == 0:
        return None
    return int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1


def runs_of_true(flags: np.ndarray):
    """Return list of (start, end_exclusive) maximal runs where flags == True."""
    runs = []
    n = len(flags)
    i = 0
    while i < n:
        if flags[i]:
            j = i
            while j < n and flags[j]:
                j += 1
            runs.append((i, j))
            i = j
        else:
            i += 1
    return runs


def clean_profile(flags: np.ndarray, min_run: int, min_gap: int):
    """Despeckle a 1-D boolean content profile so chroma-key noise doesn't
    fragment the grid. Order matters:
      (1) OPEN  — drop content runs shorter than min_run (stray specks / key
          artifacts). Done first so noise specks vanish regardless of how close
          they sit to a real frame.
      (2) CLOSE — fill interior transparent gaps shorter than min_gap (only
          true hairline splits; kept tiny so thin-but-real gutters survive)."""
    f = flags.copy()
    n = len(f)
    # 1) open: remove short content runs (noise)
    i = 0
    while i < n:
        if f[i]:
            j = i
            while j < n and f[j]:
                j += 1
            if (j - i) < min_run:
                f[i:j] = False
            i = j
        else:
            i += 1
    # 2) close short interior gaps (hairline splits only)
    i = 0
    while i < n:
        if not f[i]:
            j = i
            while j < n and not f[j]:
                j += 1
            if i > 0 and j < n and (j - i) < min_gap:
                f[i:j] = True
            i = j
        else:
            i += 1
    return f


def content_bands(has_content: np.ndarray, count: int):
    """Find content bands as maximal runs of columns/rows that have content
    (projected over the FULL region — a true gutter is empty across ALL rows/cols,
    so intra-frame gaps do NOT create false bands).

    STRICT: the number of detected bands must EXACTLY equal `count`. If there are
    more bands than expected (e.g. an extra label column, or frames split by a
    real gap) or fewer (frames touch / merged), detection FAILS. Returns
    (bands, ok, detected_count)."""
    bands = runs_of_true(has_content)
    return bands, (len(bands) == count), len(bands)


def tight_bbox(mask_region: np.ndarray):
    ys, xs = np.where(mask_region)
    if len(xs) == 0:
        return None
    return int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1


def main(argv=None):
    ap = argparse.ArgumentParser(description="Strict animation sprite-sheet normalizer.")
    ap.add_argument("input", type=Path)
    ap.add_argument("--grid", type=parse_grid, required=True, help="COLSxROWS, e.g. 4x9")
    ap.add_argument("--output", type=Path, default=None,
                    help="Output sheet PNG. Default: <input>_fixed.png")
    ap.add_argument("--anchor", choices=["bottom", "center"], default="bottom",
                    help="How each frame is placed in its uniform cell (default: bottom-center).")
    ap.add_argument("--pad", type=int, default=4, help="Transparent padding inside each cell (px).")
    ap.add_argument("--check", action="store_true", help="Verify only; write nothing.")
    args = ap.parse_args(argv)

    cols, rows = args.grid

    def emit(obj, code):
        print("SHEETFIT " + json.dumps(obj))
        sys.exit(code)

    if not args.input.exists():
        emit({"status": "rework", "input": str(args.input), "reason": "input not found"}, 2)

    img = Image.open(args.input).convert("RGBA")
    arr = np.array(img)
    alpha = arr[:, :, 3]
    mask = content_mask(alpha)

    bb = global_bbox(mask)
    if bb is None:
        emit({"status": "rework", "input": str(args.input), "reason": "image is fully transparent / empty"}, 1)
    gx0, gy0, gx1, gy1 = bb
    region = mask[gy0:gy1, gx0:gx1]
    rh, rw = region.shape

    # Detect frame grid via gutters.
    col_has = region.any(axis=0)  # length rw
    row_has = region.any(axis=1)  # length rh
    # Despeckle each profile (chroma-key noise fragments the grid otherwise).
    # Thresholds are relative to the expected cell pitch.
    col_cell = rw / cols
    row_cell = rh / rows
    # min_run drops noise specks (well below a real frame); min_gap only fuses
    # hairline splits (kept tiny so thin real gutters are preserved).
    col_clean = clean_profile(col_has, min_run=max(4, int(0.2 * col_cell)), min_gap=3)
    row_clean = clean_profile(row_has, min_run=max(4, int(0.2 * row_cell)), min_gap=3)
    xbands, ok_x, n_cols = content_bands(col_clean, cols)
    ybands, ok_y, n_rows = content_bands(row_clean, rows)
    if not ok_x or not ok_y:
        emit({
            "status": "rework", "input": str(args.input), "grid": f"{cols}x{rows}",
            "detectedCols": n_cols, "detectedRows": n_rows,
            "reason": (f"expected a {cols}x{rows} grid but detected {n_cols} column band(s) "
                       f"and {n_rows} row band(s) separated by transparent gutters. "
                       "A mismatch means in-cell labels/extra content, frames touching, "
                       "or an uneven grid. Regenerate the sheet: NO text/labels, a clear "
                       "transparent gutter between every frame, strict even grid, same "
                       "character scale per cell."),
        }, 1)

    # STRICT: column bands are frames of the same animations, grid-aligned, so
    # their widths must be roughly uniform. A label glued to the first column (or
    # a merged/extra frame) makes one band much wider -> reject.
    if cols > 1:
        widths = [e - s for (s, e) in xbands]
        if min(widths) > 0 and max(widths) / min(widths) > 1.4:
            emit({
                "status": "rework", "input": str(args.input), "grid": f"{cols}x{rows}",
                "columnBandWidths": widths,
                "reason": ("column bands have uneven widths (ratio "
                           f"{max(widths) / min(widths):.2f} > 1.4) — likely an in-cell "
                           "label glued to a frame or merged/missing frames. Regenerate "
                           "label-free with a clear transparent gutter between every column."),
            }, 1)

    # Per-cell tight content boxes (coords relative to the region).
    cells = []      # row-major list of (x0,y0,x1,y1) tight boxes in region coords
    empties = []
    sizes = []
    for r in range(rows):
        ry0, ry1 = ybands[r]
        for c in range(cols):
            cx0, cx1 = xbands[c]
            sub = region[ry0:ry1, cx0:cx1]
            tb = tight_bbox(sub)
            if tb is None:
                empties.append([c, r])
                cells.append(None)
                continue
            tx0, ty0, tx1, ty1 = tb
            box = (cx0 + tx0, ry0 + ty0, cx0 + tx1, ry0 + ty1)
            cells.append(box)
            sizes.append((tx1 - tx0, ty1 - ty0))

    if empties:
        emit({
            "status": "rework", "input": str(args.input), "grid": f"{cols}x{rows}",
            "reason": f"{len(empties)} cell(s) had no content (grid mis-detected or missing frames)",
            "empty_cells": empties,
        }, 1)

    max_w = max(w for (w, h) in sizes)
    max_h = max(h for (w, h) in sizes)
    cell_w = max_w + 2 * args.pad
    cell_h = max_h + 2 * args.pad

    if args.check:
        emit({
            "status": "pass", "input": str(args.input), "grid": f"{cols}x{rows}",
            "cellWidth": cell_w, "cellHeight": cell_h,
            "note": "clean gutters detected; sheet is normalizable",
        }, 0)

    # Recompose into a uniform-grid sheet.
    src_rgba = arr  # full image (RGBA) so we copy real pixels, not just the mask
    out = np.zeros((rows * cell_h, cols * cell_w, 4), dtype=np.uint8)
    idx = 0
    for r in range(rows):
        for c in range(cols):
            box = cells[idx]
            idx += 1
            x0, y0, x1, y1 = box
            # box is in region coords; convert to full-image coords
            fx0, fy0, fx1, fy1 = x0 + gx0, y0 + gy0, x1 + gx0, y1 + gy0
            crop = src_rgba[fy0:fy1, fx0:fx1, :]
            w = fx1 - fx0
            h = fy1 - fy0
            cell_ox = c * cell_w
            cell_oy = r * cell_h
            px = cell_ox + (cell_w - w) // 2  # horizontally centered
            if args.anchor == "bottom":
                py = cell_oy + (cell_h - h) - args.pad
            else:
                py = cell_oy + (cell_h - h) // 2
            out[py:py + h, px:px + w, :] = crop

    out_path = args.output if args.output else args.input.with_name(args.input.stem + "_fixed.png")
    Image.fromarray(out, "RGBA").save(out_path)

    # Sidecar metadata for engine import.
    meta = {
        "source": str(args.input), "output": str(out_path),
        "cols": cols, "rows": rows,
        "cellWidth": cell_w, "cellHeight": cell_h,
        "sheetWidth": cols * cell_w, "sheetHeight": rows * cell_h,
        "anchor": args.anchor, "pad": args.pad,
    }
    out_path.with_suffix(".sheet.json").write_text(json.dumps(meta, indent=2))

    emit({
        "status": "fixed", "input": str(args.input), "output": str(out_path),
        "grid": f"{cols}x{rows}", "cellWidth": cell_w, "cellHeight": cell_h,
        "anchor": args.anchor,
        "note": "normalized to uniform cells + recomposed; engine-ready",
    }, 0)


if __name__ == "__main__":
    main()
