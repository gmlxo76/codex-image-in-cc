"""Slice an atlas-style sheet into individual cell PNGs.

Reads an input PNG, divides into a cols x rows uniform grid, and for each cell
crops + saves each cell as its own PNG at the FULL CELL DIMENSIONS (transparent
padding preserved). Also writes an `atlas.json` sidecar with per-cell metadata.

By default every sliced PNG is the same size (cellW x cellH), regardless of how
much non-transparent content sits inside the cell. Pass `--tight-crop` to use
the legacy tight-bbox behaviour (each PNG cropped to its non-transparent bounds,
producing variable per-cell dimensions).

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
                            Default 0 (no margin enforcement).
                            With --verify, violations are flagged when content
                            crosses the safe-margin envelope.
    --tight-crop            Crop each cell to its non-transparent bbox instead of
                            the full cell rect. Outputs variable-sized PNGs.
                            Default: every cell PNG is exactly cellW x cellH.
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
    p.add_argument(
        "--tight-crop",
        action="store_true",
        help="Crop each cell to its non-transparent bbox instead of full cell rect.",
    )
    p.add_argument(
        "--no-auto-bbox",
        action="store_true",
        help=(
            "Disable content-bbox auto-detection. By default the slicer computes "
            "the alpha bbox of the whole sheet and divides THAT area into cols x rows "
            "cells (so asymmetric canvas padding doesn't shift cell boundaries away "
            "from where the content actually sits). Disable to use the raw canvas "
            "and divide sheetW/cols x sheetH/rows from (0, 0)."
        ),
    )
    p.add_argument(
        "--no-recenter",
        action="store_true",
        help=(
            "Disable per-cell content recentering. By default each cell's "
            "non-transparent content is detected and pasted CENTERED in the output "
            "PNG, so AI-generated atlases with positional drift (icons placed "
            "top-left in one cell, bottom-right in another) become visually "
            "aligned. Disable to keep content at its raw position within the cell."
        ),
    )

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

    # Content-bbox auto-detection (default on). AI-generated atlases routinely
    # have asymmetric padding around the entire content area (e.g. 33px left,
    # 17px top, 28px right, 39px bottom). Dividing the canvas by cols×rows
    # then slices through content; dividing the content bbox instead lines
    # cells up with where the art actually sits.
    if args.no_auto_bbox:
        content_x0, content_y0 = 0, 0
        content_w_raw, content_h_raw = sheet_w, sheet_h
    else:
        alpha_mask = img.split()[3].point(
            lambda v: 255 if v > args.alpha_threshold else 0
        )
        bbox = alpha_mask.getbbox()
        if bbox is None:
            print("ERROR: sheet is entirely transparent.", file=sys.stderr)
            return 2
        content_x0, content_y0, content_x1, content_y1 = bbox
        content_w_raw = content_x1 - content_x0
        content_h_raw = content_y1 - content_y0

    if args.cell_w is not None:
        cell_w = args.cell_w
    else:
        cell_w = content_w_raw // cols
    if args.cell_h is not None:
        cell_h = args.cell_h
    else:
        cell_h = content_h_raw // rows

    # Fractional remainder distributed across cells by using float pitch for boundaries.
    pitch_w = content_w_raw / cols
    pitch_h = content_h_raw / rows

    if not args.no_auto_bbox and (content_x0 > 0 or content_y0 > 0 or
                                   content_x0 + content_w_raw < sheet_w or
                                   content_y0 + content_h_raw < sheet_h):
        print(
            f"INFO: auto-bbox detected content area "
            f"({content_x0},{content_y0})-({content_x0+content_w_raw},{content_y0+content_h_raw}) "
            f"in {sheet_w}x{sheet_h} canvas; "
            f"slicing within bbox. Output cell size: {cell_w}x{cell_h}",
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

    # Integer pitch so every cell in this atlas has IDENTICAL output dimensions.
    # The remainder (content_w_raw - cols*int_pitch_w) is centered as padding
    # before the first cell, so cells stay centered on the content area.
    int_pitch_w = content_w_raw // cols
    int_pitch_h = content_h_raw // rows
    pad_x = (content_w_raw - cols * int_pitch_w) // 2
    pad_y = (content_h_raw - rows * int_pitch_h) // 2
    origin_x = content_x0 + pad_x
    origin_y = content_y0 + pad_y

    for row in range(rows):
        for col in range(cols):
            idx = row * cols + col
            name = name_list[idx] if name_list else f"r{row}c{col}"
            x0 = origin_x + col * int_pitch_w
            y0 = origin_y + row * int_pitch_h
            x1 = x0 + int_pitch_w
            y1 = y0 + int_pitch_h

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
                if args.tight_crop:
                    cropped = img.crop(tight)
                elif args.no_recenter:
                    # Crop at full cell rect; content stays at its raw position.
                    cropped = img.crop((x0, y0, x1, y1))
                else:
                    # Default: crop tight content, then paste centered into a
                    # transparent cell-sized canvas. Fixes AI-generated atlases
                    # where each cell's icon drifts to a different anchor.
                    out_w = int_pitch_w
                    out_h = int_pitch_h
                    cropped = Image.new("RGBA", (out_w, out_h), (0, 0, 0, 0))
                    inner = img.crop(tight)
                    iw, ih = inner.size
                    paste_x = (out_w - iw) // 2
                    paste_y = (out_h - ih) // 2
                    cropped.paste(inner, (paste_x, paste_y), inner)
                out_path = out_dir / f"{name}.png"
                cropped.save(out_path, optimize=True)

            atlas_meta["cells"][name] = {
                "file": f"{name}.png",
                "row": row,
                "col": col,
                "cell_origin": [x0, y0],
                "cell_size": [cell_w, cell_h],
                "tight_rect": [tight[0], tight[1], tw, th],
                "tight_size": [tw, th],
                "offset_in_cell": [ox, oy],
                "output_size": [tw, th] if args.tight_crop else [cell_w, cell_h],
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
