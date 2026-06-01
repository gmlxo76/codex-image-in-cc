#!/usr/bin/env python3
"""Realign cells in a multi-cell atlas so each cell's content is center-anchored.

AI image generators produce atlas-style images where cells are intended to be
pixel-identical (e.g., a button's default vs pressed state) but the AI rarely
draws them in exactly matching positions. Cells drift by a few to many pixels,
which means a straight cell-slice produces frames that "jump" when an engine
swaps them at runtime.

This script:
1. Slices the input atlas by the given grid.
2. Detects an alignment anchor per cell (ring center, bbox center, or centroid).
3. Shifts each cell's content so the anchor lands at the cell's geometric center.
4. Recomposes the cells into a new atlas (or overwrites the input).
5. Optionally writes the aligned per-cell PNGs to a directory.
6. Optionally writes an atlas.json sidecar describing the cell layout.

Detection methods (--align-by):
  ring      Best for circular UI buttons (most common). Finds connected components
            of high-alpha pixels, identifies ring-shaped components (large bbox,
            low fill factor, near-square aspect). For multi-ring (concentric)
            cases like a pressed mic with inner + outer rings, picks the smaller
            (inner) ring as the anchor. Requires scipy.
  bbox      Geometric center of the high-alpha (alpha >= 200) bounding box.
            Robust fallback; works for any content but doesn't isolate the
            inner ring in multi-ring cases.
  centroid  Alpha-weighted centroid of pixels with alpha >= 50. Drifts when
            an outer glow halo is asymmetric — avoid for glow content.
  none      No detection; use the cell's existing geometric center (= straight
            slice without any realignment).

The script preserves transparency (RGBA throughout) and never resizes content;
it only translates cell pixels by integer offsets.
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
        "realign_atlas.py requires Pillow and numpy.\n"
        "  pip install Pillow numpy\n"
        f"  (missing: {exc.name})\n"
    )
    sys.exit(2)

try:
    from scipy.ndimage import label as cc_label
    HAS_SCIPY = True
except ImportError:
    HAS_SCIPY = False


HIGH_ALPHA = 200
CENTROID_ALPHA = 50
RING_FILL_MAX = 0.25
RING_ASPECT_MAX = 1.3
RING_MIN_BBOX_FRACTION = 0.30  # ring's bbox must span at least 30% of cell
CONCENTRIC_TOL = 25            # max distance between concentric ring centers


def parse_grid(text: str) -> tuple[int, int]:
    text = text.lower().strip()
    if "x" not in text:
        raise argparse.ArgumentTypeError(f"--grid must be COLSxROWS (e.g. 2x1), got {text!r}")
    cols_s, rows_s = text.split("x", 1)
    cols, rows = int(cols_s), int(rows_s)
    if cols <= 0 or rows <= 0:
        raise argparse.ArgumentTypeError("--grid values must be positive")
    return cols, rows


def detect_anchor(img: Image.Image, method: str) -> tuple[float, float]:
    """Detect alignment anchor (x, y) in cell-local coordinates.

    Falls back to the cell's geometric center if detection fails.
    """
    w, h = img.size
    canvas_center = (w / 2.0, h / 2.0)

    if method == "none":
        return canvas_center

    alpha = np.asarray(img.split()[-1])

    if method == "centroid":
        mask = alpha >= CENTROID_ALPHA
        ys, xs = np.where(mask)
        if len(xs) == 0:
            return canvas_center
        weights = alpha[mask].astype(np.float64)
        return (
            float(np.sum(xs * weights) / np.sum(weights)),
            float(np.sum(ys * weights) / np.sum(weights)),
        )

    mask = alpha >= HIGH_ALPHA
    ys, xs = np.where(mask)
    if len(xs) == 0:
        return canvas_center

    if method == "bbox":
        return (
            (int(xs.min()) + int(xs.max())) / 2.0,
            (int(ys.min()) + int(ys.max())) / 2.0,
        )

    # method == "ring"
    if not HAS_SCIPY:
        # Without scipy we cannot do connected-component analysis; fall back to bbox.
        return (
            (int(xs.min()) + int(xs.max())) / 2.0,
            (int(ys.min()) + int(ys.max())) / 2.0,
        )

    labeled, n = cc_label(mask.astype(np.uint8), structure=np.ones((3, 3), dtype=int))
    canvas_dim = max(h, w)

    rings: list[dict] = []
    for i in range(1, n + 1):
        cys, cxs = np.where(labeled == i)
        if len(cxs) < 50:
            continue
        x0, y0 = int(cxs.min()), int(cys.min())
        x1, y1 = int(cxs.max()), int(cys.max())
        bw, bh = x1 - x0 + 1, y1 - y0 + 1
        bbox_max = max(bw, bh)
        bbox_min = min(bw, bh)
        aspect = bbox_max / max(1, bbox_min)
        fill = len(cxs) / float(bw * bh)
        is_ring = (
            bbox_max > canvas_dim * RING_MIN_BBOX_FRACTION
            and fill < RING_FILL_MAX
            and aspect < RING_ASPECT_MAX
        )
        if is_ring:
            rings.append({
                "bbox_center": ((x0 + x1) / 2.0, (y0 + y1) / 2.0),
                "bbox_max": bbox_max,
                "n_pixels": len(cxs),
            })

    if len(rings) >= 2:
        cxs_r = [r["bbox_center"][0] for r in rings]
        cys_r = [r["bbox_center"][1] for r in rings]
        concentric = (
            max(cxs_r) - min(cxs_r) <= CONCENTRIC_TOL
            and max(cys_r) - min(cys_r) <= CONCENTRIC_TOL
        )
        if concentric:
            # Concentric multi-ring -> pick the inner ring (smallest bbox).
            rings.sort(key=lambda r: r["bbox_max"])
            return rings[0]["bbox_center"]
        # Non-concentric (e.g., broken-ring fragments) -> pick the dominant piece.
        rings.sort(key=lambda r: -r["n_pixels"])
        return rings[0]["bbox_center"]

    if len(rings) == 1:
        return rings[0]["bbox_center"]

    # No ring detected -> bbox center of all high-alpha pixels.
    return (
        (int(xs.min()) + int(xs.max())) / 2.0,
        (int(ys.min()) + int(ys.max())) / 2.0,
    )


def shift_to_center(cell: Image.Image, anchor: tuple[float, float]) -> Image.Image:
    w, h = cell.size
    cx, cy = w / 2.0, h / 2.0
    dx = int(round(cx - anchor[0]))
    dy = int(round(cy - anchor[1]))
    out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    out.alpha_composite(cell, (dx, dy))
    return out


def content_bbox(cell: Image.Image, alpha_threshold: int = CENTROID_ALPHA):
    """Return (x0, y0, x1, y1) tight bbox of pixels with alpha > threshold, or None."""
    alpha = np.asarray(cell.split()[-1])
    ys, xs = np.where(alpha > alpha_threshold)
    if len(xs) == 0:
        return None
    return int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1


def normalize_cell_size(cell: Image.Image, target_w: int, target_h: int,
                        alpha_threshold: int = CENTROID_ALPHA) -> Image.Image:
    """Scale the cell's tight content to (target_w, target_h) and paste centered.

    Equalizes content SIZE across cells (translation alone cannot do this), so a
    runtime state-swap shows no size jump. Near-identical variants scale by <2%,
    which is visually imperceptible.
    """
    w, h = cell.size
    bb = content_bbox(cell, alpha_threshold)
    out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    if bb is None:
        return out
    inner = cell.crop(bb)
    if inner.size != (target_w, target_h):
        inner = inner.resize((max(1, target_w), max(1, target_h)), Image.LANCZOS)
    paste_x = int(round((w - target_w) / 2.0))
    paste_y = int(round((h - target_h) / 2.0))
    out.alpha_composite(inner, (paste_x, paste_y))
    return out


def analyze_cells(cells: list[Image.Image], cw: int, ch: int,
                  alpha_threshold: int = CENTROID_ALPHA) -> dict:
    """Measure per-cell content center offset (from cell center) and content size.

    Returns a report dict with per-cell stats plus the cross-cell spreads used to
    decide pass/fail (max center drift, content width/height spread).
    """
    cell_center = (cw / 2.0, ch / 2.0)
    per_cell = []
    centers_x, centers_y, widths, heights = [], [], [], []
    for i, cell in enumerate(cells):
        bb = content_bbox(cell, alpha_threshold)
        if bb is None:
            per_cell.append({"index": i, "empty": True})
            continue
        x0, y0, x1, y1 = bb
        ccx, ccy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
        bw, bh = x1 - x0, y1 - y0
        per_cell.append({
            "index": i,
            "content_center": [round(ccx, 1), round(ccy, 1)],
            "center_offset": [round(ccx - cell_center[0], 1), round(ccy - cell_center[1], 1)],
            "content_size": [bw, bh],
        })
        centers_x.append(ccx)
        centers_y.append(ccy)
        widths.append(bw)
        heights.append(bh)
    spread = {
        "center_x": round(max(centers_x) - min(centers_x), 1) if centers_x else 0.0,
        "center_y": round(max(centers_y) - min(centers_y), 1) if centers_y else 0.0,
        "width": (max(widths) - min(widths)) if widths else 0,
        "height": (max(heights) - min(heights)) if heights else 0,
    }
    return {"cells": per_cell, "spread": spread}


def slice_atlas(atlas: Image.Image, cols: int, rows: int) -> list[Image.Image]:
    aw, ah = atlas.size
    cw, ch = aw // cols, ah // rows
    cells = []
    for row in range(rows):
        for col in range(cols):
            x0 = col * cw
            y0 = row * ch
            cells.append(atlas.crop((x0, y0, x0 + cw, y0 + ch)))
    return cells


def compose_atlas(cells: list[Image.Image], cols: int, rows: int) -> Image.Image:
    cw, ch = cells[0].size
    atlas = Image.new("RGBA", (cw * cols, ch * rows), (0, 0, 0, 0))
    for i, cell in enumerate(cells):
        col, row = i % cols, i // cols
        atlas.alpha_composite(cell, (col * cw, row * ch))
    return atlas


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Realign cells in a multi-cell atlas so each cell's content is center-anchored, "
            "then recompose. Fixes the 'AI drew the cells at slightly different positions' "
            "problem in one shot."
        )
    )
    parser.add_argument("input", type=Path, help="Input atlas PNG")
    parser.add_argument("--grid", type=parse_grid, required=True, help="Grid as COLSxROWS (e.g. 2x1)")
    parser.add_argument(
        "--align-by", choices=["ring", "bbox", "centroid", "none"], default="ring",
        help=(
            "Anchor detection method (default: ring — best for circular UI buttons). "
            "bbox = high-alpha bbox center, centroid = alpha-weighted centroid, "
            "none = no realignment (straight slice)."
        ),
    )
    parser.add_argument(
        "--output", type=Path, default=None,
        help="Output atlas PNG path. Default: overwrite the input file.",
    )
    parser.add_argument(
        "--write-cells", type=Path, default=None,
        help="Optional directory to write the realigned per-cell PNGs.",
    )
    parser.add_argument(
        "--cell-names", default=None,
        help="Comma-separated cell names (in row-major order). Used for --write-cells filenames and the JSON sidecar.",
    )
    parser.add_argument(
        "--write-json", action="store_true",
        help="Write an atlas.json sidecar (cell coords) next to the output PNG.",
    )
    parser.add_argument("--quiet", action="store_true", help="Suppress per-cell stats.")
    parser.add_argument(
        "--check", action="store_true",
        help=(
            "Check-only mode: measure per-cell content center offset and size spread, "
            "print a JSON report, and exit 1 if the atlas exceeds --tolerance / "
            "--size-tolerance (0 = aligned). Writes no files."
        ),
    )
    parser.add_argument(
        "--normalize-size", action="store_true",
        help=(
            "When realigning, also scale each cell's content to a canonical size so "
            "every cell is pixel-identical in BOTH position and size (not just centered). "
            "Required for clean runtime state-swaps; translation alone cannot equalize size."
        ),
    )
    parser.add_argument(
        "--tolerance", type=float, default=2.0,
        help="Max allowed cross-cell content-center spread in px before --check fails (default 2.0).",
    )
    parser.add_argument(
        "--size-tolerance", type=int, default=2,
        help="Max allowed cross-cell content width/height spread in px before --check fails (default 2).",
    )

    args = parser.parse_args(argv)

    if not args.input.exists():
        parser.error(f"Input atlas not found: {args.input}")
    if args.align_by == "ring" and not HAS_SCIPY:
        sys.stderr.write(
            "WARNING: --align-by=ring requires scipy; falling back to bbox.\n"
            "  Install with: pip install scipy\n"
        )

    cols, rows = args.grid
    atlas = Image.open(args.input).convert("RGBA")
    aw, ah = atlas.size
    if aw % cols != 0 or ah % rows != 0:
        parser.error(
            f"Atlas size {aw}x{ah} is not evenly divisible by grid {cols}x{rows}."
        )
    cw, ch = aw // cols, ah // rows

    cells = slice_atlas(atlas, cols, rows)

    # --- Check-only mode: measure alignment/size uniformity, report, exit code. ---
    if args.check:
        report = analyze_cells(cells, cw, ch)
        sp = report["spread"]
        passed = (
            sp["center_x"] <= args.tolerance
            and sp["center_y"] <= args.tolerance
            and sp["width"] <= args.size_tolerance
            and sp["height"] <= args.size_tolerance
        )
        report["grid"] = {"cols": cols, "rows": rows, "cellW": cw, "cellH": ch}
        report["tolerance"] = {"center": args.tolerance, "size": args.size_tolerance}
        report["passed"] = passed
        print(json.dumps(report, indent=2))
        return 0 if passed else 1

    # Canonical content size for --normalize-size: per-axis max across non-empty cells.
    target_w = target_h = None
    if args.normalize_size:
        bws, bhs = [], []
        for cell in cells:
            bb = content_bbox(cell)
            if bb is not None:
                bws.append(bb[2] - bb[0])
                bhs.append(bb[3] - bb[1])
        if bws:
            target_w, target_h = max(bws), max(bhs)

    aligned: list[Image.Image] = []
    anchors: list[tuple[float, float]] = []
    shifts: list[tuple[int, int]] = []
    for cell in cells:
        anchor = detect_anchor(cell, args.align_by)
        if args.normalize_size and target_w is not None:
            # Equalize size AND center in one step (anchor==content center after normalize).
            aligned_cell = normalize_cell_size(cell, target_w, target_h)
        else:
            aligned_cell = shift_to_center(cell, anchor)
        anchors.append(anchor)
        shifts.append((int(round(cw / 2 - anchor[0])), int(round(ch / 2 - anchor[1]))))
        aligned.append(aligned_cell)

    new_atlas = compose_atlas(aligned, cols, rows)
    output_path = args.output if args.output else args.input
    output_path.parent.mkdir(parents=True, exist_ok=True)
    new_atlas.save(output_path)
    print(f"SAVED: {output_path.resolve()}")

    if not args.quiet:
        for i, (anchor, shift) in enumerate(zip(anchors, shifts)):
            col, row = i % cols, i // cols
            print(
                f"  cell[{i}] (col={col},row={row}) "
                f"anchor=({anchor[0]:.1f},{anchor[1]:.1f}) "
                f"shift=({shift[0]:+d},{shift[1]:+d})"
            )

    names: list[str] = []
    if args.cell_names:
        names = [n.strip() for n in args.cell_names.split(",")]
    while len(names) < len(aligned):
        names.append(f"cell{len(names)}")

    if args.write_cells:
        args.write_cells.mkdir(parents=True, exist_ok=True)
        for i, cell in enumerate(aligned):
            (args.write_cells / f"{names[i]}.png").parent.mkdir(parents=True, exist_ok=True)
            cell.save(args.write_cells / f"{names[i]}.png")
        print(f"SAVED cells: {args.write_cells.resolve()}")

    if args.write_json:
        json_path = output_path.with_suffix(".json")
        cells_meta = []
        for i in range(len(aligned)):
            col, row = i % cols, i // cols
            cells_meta.append({
                "name": names[i],
                "index": i,
                "x": col * cw,
                "y": row * ch,
                "w": cw,
                "h": ch,
            })
        sidecar = {
            "name": output_path.stem,
            "image": output_path.name,
            "size": [cw * cols, ch * rows],
            "grid": {"cols": cols, "rows": rows, "cellW": cw, "cellH": ch},
            "cells": cells_meta,
            "alignment_method": args.align_by,
        }
        json_path.write_text(json.dumps(sidecar, indent=2), encoding="utf-8")
        print(f"SAVED JSON: {json_path.resolve()}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
