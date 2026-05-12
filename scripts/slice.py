"""Slice an atlas-style sheet into individual cell PNGs.

Reads an input PNG, divides into a cols x rows uniform grid, and for each cell
finds the tight non-transparent bounding box, then crops + saves each cell as
its own PNG. Also writes an `atlas.json` sidecar with per-cell metadata
(cell origin, tight rect, offset within cell, size) for engine positioning.

Can also operate in `verify` mode (no output) — slices and checks whether any
cell's tight content bleeds outside the safe-margin envelope, reporting
violations as JSON to stdout.

Usage:
    python slice.py <input.png> --output-dir <dir> --grid CxR [options]
    python slice.py <input.png> --verify --grid CxR --safe-margin N [options]

Options:
    --grid CxR              Grid spec (e.g., "4x5" for 4 cols x 5 rows). Required.
    --cell-w N              Cell width override (default: sheetW / cols).
    --cell-h N              Cell height override (default: sheetH / rows).
    --names "n1,n2,..."     Comma-separated cell names in row-major order. If
                            omitted, cells named "r0c0", "r0c1", ...
    --safe-margin N         Margin (px) inside each cell that content must respect.
                            Default 0 (no margin enforcement; just tight crop).
                            With --verify, violations are flagged when content
                            crosses the safe-margin envelope.
    --output-dir <dir>      Output directory for sliced cells + atlas.json.
                            Required unless --verify.
    --verify                Verify-only mode: no output files, report violations
                            as JSON to stdout. Exits 0 if no violations, 1 if any.
    --alpha-threshold N     Alpha value (0-255) below which pixels are treated
                            as transparent. Default 20.

Exits:
    0 = success (or verify pass)
    1 = verify failure (one or more cells violate safe margin)
    2 = usage / IO error
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

try:
    from PIL import Image
except ImportError:
    print(
        "ERROR: Pillow not installed. Install with: pip install Pillow",
        file=sys.stderr,
    )
    sys.exit(2)


def parse_grid(spec: str) -> tuple[int, int]:
    """Parse "CxR" string (e.g., "4x5") into (cols, rows)."""
    if "x" not in spec.lower():
        raise ValueError(f"Invalid --grid spec: {spec!r} (expected 'CxR' like '4x5')")
    parts = spec.lower().split("x")
    if len(parts) != 2:
        raise ValueError(f"Invalid --grid spec: {spec!r}")
    cols = int(parts[0])
    rows = int(parts[1])
    if cols <= 0 or rows <= 0:
        raise ValueError(f"Grid dims must be positive: {cols}x{rows}")
    return cols, rows


def tight_bbox_in_cell(
    img: Image.Image,
    x0: int,
    y0: int,
    x1: int,
    y1: int,
    alpha_threshold: int = 20,
) -> Optional[tuple[int, int, int, int]]:
    """Return tight non-transparent bbox (x0,y0,x1,y1) absolute coords, or None."""
    region = img.crop((x0, y0, x1, y1))
    if region.mode != "RGBA":
        region = region.convert("RGBA")
    alpha = region.split()[3]
    mask = alpha.point(lambda v: 255 if v > alpha_threshold else 0)
    bbox = mask.getbbox()
    if bbox is None:
        return None
    return (x0 + bbox[0], y0 + bbox[1], x0 + bbox[2], y0 + bbox[3])


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(prog="slice.py")
    p.add_argument("input", help="Input PNG path")
    p.add_argument("--grid", required=True, help='Grid spec "CxR" (e.g. "4x5")')
    p.add_argument("--cell-w", type=int, default=None, help="Cell width override")
    p.add_argument("--cell-h", type=int, default=None, help="Cell height override")
    p.add_argument("--names", default=None, help="Comma-separated cell names (row-major)")
    p.add_argument("--safe-margin", type=int, default=0, help="Safe margin within cell (px)")
    p.add_argument("--output-dir", default=None, help="Output dir for cells + atlas.json")
    p.add_argument("--verify", action="store_true", help="Verify mode only — no output")
    p.add_argument("--alpha-threshold", type=int, default=20, help="Alpha threshold (0-255)")

    args = p.parse_args(argv)

    input_path = Path(args.input).resolve()
    if not input_path.exists():
        print(f"ERROR: Input not found: {input_path}", file=sys.stderr)
        return 2

    try:
        cols, rows = parse_grid(args.grid)
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2

    img = Image.open(input_path).convert("RGBA")
    sheet_w, sheet_h = img.size

    cell_w = args.cell_w if args.cell_w is not None else sheet_w // cols
    cell_h = args.cell_h if args.cell_h is not None else sheet_h // rows

    expected_w = cols * cell_w
    expected_h = rows * cell_h
    if expected_w != sheet_w or expected_h != sheet_h:
        # Allow off-by-one rounding when --cell-w / --cell-h not explicit
        diff_w = abs(expected_w - sheet_w)
        diff_h = abs(expected_h - sheet_h)
        if diff_w > 2 or diff_h > 2:
            print(
                f"WARNING: grid {cols}x{rows} * cell {cell_w}x{cell_h} = "
                f"{expected_w}x{expected_h} but sheet is {sheet_w}x{sheet_h} "
                f"(diff {diff_w},{diff_h}px). Using grid as authoritative.",
                file=sys.stderr,
            )

    name_list: Optional[list[str]] = None
    if args.names:
        name_list = [n.strip() for n in args.names.split(",")]
        expected_count = cols * rows
        if len(name_list) != expected_count:
            print(
                f"ERROR: --names has {len(name_list)} entries but grid {cols}x{rows} "
                f"needs {expected_count}",
                file=sys.stderr,
            )
            return 2

    out_dir: Optional[Path] = None
    if not args.verify:
        if not args.output_dir:
            print("ERROR: --output-dir required (omit only with --verify)", file=sys.stderr)
            return 2
        out_dir = Path(args.output_dir).resolve()
        out_dir.mkdir(parents=True, exist_ok=True)

    atlas_meta: dict = {
        "source": str(input_path).replace("\\", "/"),
        "sheet_size": [sheet_w, sheet_h],
        "grid": {"cols": cols, "rows": rows, "cellW": cell_w, "cellH": cell_h},
        "safe_margin": args.safe_margin,
        "cells": {},
    }

    violations: list[dict] = []
    sliced = 0
    empty = 0

    for row in range(rows):
        for col in range(cols):
            idx = row * cols + col
            name = name_list[idx] if name_list else f"r{row}c{col}"
            x0 = col * cell_w
            y0 = row * cell_h
            x1 = x0 + cell_w
            y1 = y0 + cell_h

            tight = tight_bbox_in_cell(img, x0, y0, x1, y1, args.alpha_threshold)
            if tight is None:
                empty += 1
                continue

            # Compute offset within cell
            ox = tight[0] - x0
            oy = tight[1] - y0
            tw = tight[2] - tight[0]
            th = tight[3] - tight[1]

            # Safe-margin check
            if args.safe_margin > 0:
                m = args.safe_margin
                left_overflow = max(0, m - ox)
                top_overflow = max(0, m - oy)
                right_overflow = max(0, (ox + tw) - (cell_w - m))
                bottom_overflow = max(0, (oy + th) - (cell_h - m))
                if left_overflow or top_overflow or right_overflow or bottom_overflow:
                    violations.append({
                        "cell": name,
                        "row": row,
                        "col": col,
                        "tight_in_cell": [ox, oy, tw, th],
                        "cell_size": [cell_w, cell_h],
                        "overflow": {
                            "left": left_overflow,
                            "top": top_overflow,
                            "right": right_overflow,
                            "bottom": bottom_overflow,
                        },
                    })

            if not args.verify and out_dir is not None:
                cropped = img.crop(tight)
                out_path = out_dir / f"{name}.png"
                cropped.save(out_path, optimize=True)

            atlas_meta["cells"][name] = {
                "file": f"{name}.png",
                "row": row,
                "col": col,
                "cell_origin": [x0, y0],
                "cell_size": [cell_w, cell_h],
                "tight_rect": [tight[0], tight[1], tw, th],
                "size": [tw, th],
                "offset_in_cell": [ox, oy],
            }
            sliced += 1

    if args.verify:
        report = {
            "input": str(input_path).replace("\\", "/"),
            "grid": {"cols": cols, "rows": rows, "cellW": cell_w, "cellH": cell_h},
            "safe_margin": args.safe_margin,
            "cells_total": cols * rows,
            "cells_with_content": sliced,
            "cells_empty": empty,
            "violations": violations,
            "passed": len(violations) == 0,
        }
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0 if report["passed"] else 1
    else:
        assert out_dir is not None
        atlas_meta["violations"] = violations
        atlas_path = out_dir / "atlas.json"
        with open(atlas_path, "w", encoding="utf-8") as f:
            json.dump(atlas_meta, f, indent=2, ensure_ascii=False)
        print(
            json.dumps({
                "status": "ok",
                "sliced": sliced,
                "empty": empty,
                "violations": len(violations),
                "output_dir": str(out_dir).replace("\\", "/"),
                "atlas_json": str(atlas_path).replace("\\", "/"),
            })
        )
        return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
