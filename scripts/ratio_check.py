#!/usr/bin/env python3
"""Verify the DRAWN content's aspect ratio matches the requested cell/canvas aspect ratio.

The rule: when you ask for a canvas/cell of a given size, the SUBJECT that gets drawn
must share that aspect ratio. Margin (transparent padding) around the subject is fine —
what is NOT fine is the model drawing the subject at a different proportion than requested
(e.g. an elongated 2.7:1 bar inside a 2:1 cell, or a tall element in a wide cell).

This measures each cell's non-transparent content bbox aspect ratio and compares it to the
cell's aspect ratio. Exits 1 if any cell deviates beyond --tolerance, so the agent can
regenerate. Margin/centering does NOT cause a failure — only a proportion mismatch does.

    python ratio_check.py <input.png> --grid CxR [--tolerance 0.12] [--alpha-threshold 20]
"""
from __future__ import annotations
import argparse, json, sys

try:
    from PIL import Image
    import numpy as np
except ImportError as exc:  # pragma: no cover
    sys.stderr.write(f"ratio_check.py requires Pillow + numpy (missing: {exc.name})\n")
    sys.exit(2)


def cell_bboxes(img, cols, rows, thr):
    a = np.asarray(img.split()[-1])
    H, W = a.shape
    cw, ch = W // cols, H // rows
    out = []
    for r in range(rows):
        for c in range(cols):
            sub = a[r * ch:(r + 1) * ch, c * cw:(c + 1) * cw]
            ys, xs = np.where(sub > thr)
            if len(xs) == 0:
                out.append(None)
            else:
                out.append((int(xs.max() - xs.min() + 1), int(ys.max() - ys.min() + 1)))
    return out, cw, ch


def main(argv=None):
    p = argparse.ArgumentParser(description="Check drawn-content aspect ratio matches cell aspect ratio.")
    p.add_argument("input")
    p.add_argument("--grid", default="1x1", help="COLSxROWS (default 1x1 = whole image)")
    p.add_argument("--tolerance", type=float, default=0.12, help="max fractional deviation of content aspect from cell aspect (default 0.12 = 12%)")
    p.add_argument("--alpha-threshold", type=int, default=20)
    args = p.parse_args(argv)

    cols, rows = (int(x) for x in args.grid.lower().split("x"))
    img = Image.open(args.input).convert("RGBA")
    bxs, cw, ch = cell_bboxes(img, cols, rows, args.alpha_threshold)
    cell_aspect = cw / ch

    cells, passed = [], True
    for i, b in enumerate(bxs):
        if b is None:
            continue
        asp = b[0] / b[1]
        dev = abs(asp - cell_aspect) / cell_aspect
        ok = dev <= args.tolerance
        passed = passed and ok
        cells.append({
            "cell": i, "content_wh": [b[0], b[1]], "content_aspect": round(asp, 2),
            "cell_aspect": round(cell_aspect, 2), "deviation": round(dev, 3), "ok": ok,
        })
    print(json.dumps({
        "grid": [cols, rows], "cell": [cw, ch], "cell_aspect": round(cell_aspect, 2),
        "tolerance": args.tolerance, "passed": passed, "cells": cells,
    }, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
