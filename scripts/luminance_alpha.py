#!/usr/bin/env python3
"""Luminance-based alpha extraction for transparent PNG generation.

Converts an image that was rendered on a SOLID BLACK background (no chroma key)
into an RGBA PNG where transparency is derived from pixel brightness:

    alpha = formula(R, G, B)   # default: max(R, G, B)

This avoids the color-contamination problem of chroma-key (e.g. magenta) workflows
when generating luminous content (glow, neon, VFX, light sources): instead of mixing
content with a key color and trying to subtract it later, content is rendered on
pure black, then alpha is recovered from luminance. The natural brightness falloff
of glow effects becomes a natural alpha falloff — no purple fringes, no hard cuts.

Use when:
- The target asset has glow, light, neon, VFX, sparks, halos, or luminous edges
- The background of the source image is solid black (#000000)
- Color fidelity at the edges of bright content matters

Do NOT use when:
- The asset has intentionally dark areas you want to keep opaque (those become
  transparent under this method — use chroma-key extraction instead)
- The source image was rendered on a non-black background
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

try:
    import numpy as np
    from PIL import Image
except ImportError as exc:  # pragma: no cover - import-time diagnostic
    sys.stderr.write(
        "luminance_alpha.py requires Pillow and numpy.\n"
        "  pip install Pillow numpy\n"
        f"  (missing: {exc.name})\n"
    )
    sys.exit(2)


FORMULAS = {
    # max channel — preserves the brightest color in each pixel, perfect for
    # colored glow (gold, neon, fire) because saturated color stays saturated.
    "max": lambda arr: arr.max(axis=2),
    # Rec. 709 luma — matches human perception, dims pure blue and reds.
    "luma": lambda arr: (0.2126 * arr[..., 0] + 0.7152 * arr[..., 1] + 0.0722 * arr[..., 2]),
    # Simple average — softer falloff, useful for neutral whites/grays.
    "avg": lambda arr: arr.mean(axis=2),
}


def extract_luminance_alpha(
    src_path: Path,
    out_path: Path,
    *,
    size: tuple[int, int] | None = None,
    formula: str = "max",
    black_threshold: int = 0,
    white_cutoff: int = 255,
    gamma: float = 1.0,
    premultiply: bool = False,
) -> dict:
    """Extract alpha from luminance and save as RGBA PNG.

    Args:
        src_path: input image (assumed rendered on black background).
        out_path: destination RGBA PNG path.
        size: optional (width, height) for LANCZOS resize after extraction.
        formula: "max" (default) | "luma" | "avg".
        black_threshold: pixels with computed alpha < this become fully transparent
            (cleans up dim background noise). 0 = no cutoff.
        white_cutoff: brightness mapped to alpha=255 (1..255). Values above this
            saturate to opaque. Lower values brighten the alpha curve.
        gamma: alpha curve adjustment (>1 = harder edges, <1 = softer edges).
        premultiply: if True, multiply RGB by alpha so compositing matches
            "screen" / additive blending without halo artifacts.

    Returns:
        dict with stats: size, mode, nonzero_alpha_pixels, max_alpha, etc.
    """
    if formula not in FORMULAS:
        raise ValueError(f"Unknown formula: {formula!r}. Choose from: {sorted(FORMULAS)}")
    if not (1 <= white_cutoff <= 255):
        raise ValueError("--white-cutoff must be between 1 and 255")
    if black_threshold < 0 or black_threshold > 255:
        raise ValueError("--black-threshold must be between 0 and 255")
    if gamma <= 0:
        raise ValueError("--gamma must be > 0")

    src = Image.open(src_path).convert("RGB")
    arr = np.asarray(src, dtype=np.float32)

    luminance = FORMULAS[formula](arr)  # shape (H, W), 0..255
    if black_threshold > 0:
        luminance = np.where(luminance < black_threshold, 0.0, luminance)
    if white_cutoff < 255:
        luminance = np.clip(luminance * (255.0 / white_cutoff), 0.0, 255.0)
    if gamma != 1.0:
        norm = np.clip(luminance / 255.0, 0.0, 1.0)
        luminance = np.power(norm, 1.0 / gamma) * 255.0

    alpha = np.clip(luminance, 0.0, 255.0).astype(np.uint8)

    if premultiply:
        scale = (alpha.astype(np.float32) / 255.0)[..., None]
        rgb = np.clip(arr * scale, 0, 255).astype(np.uint8)
    else:
        rgb = arr.astype(np.uint8)

    rgba = np.dstack([rgb, alpha])
    img = Image.fromarray(rgba, "RGBA")

    if size is not None:
        img = img.resize(size, Image.Resampling.LANCZOS)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path)

    final = Image.open(out_path).convert("RGBA")
    final_alpha = np.asarray(final)[..., 3]
    return {
        "size": final.size,
        "mode": final.mode,
        "nonzero_alpha_pixels": int((final_alpha > 0).sum()),
        "max_alpha": int(final_alpha.max()),
        "corner_alpha": [int(final_alpha[0, 0]), int(final_alpha[0, -1]),
                         int(final_alpha[-1, 0]), int(final_alpha[-1, -1])],
        "formula": formula,
        "premultiplied": premultiply,
    }


def parse_size(text: str) -> tuple[int, int]:
    if "x" not in text.lower():
        raise argparse.ArgumentTypeError(f"--size must be WxH (e.g. 768x768), got {text!r}")
    parts = text.lower().split("x")
    if len(parts) != 2:
        raise argparse.ArgumentTypeError(f"--size must be WxH, got {text!r}")
    try:
        w, h = int(parts[0]), int(parts[1])
    except ValueError as err:
        raise argparse.ArgumentTypeError(f"--size dimensions must be integers: {err}")
    if w <= 0 or h <= 0:
        raise argparse.ArgumentTypeError("--size dimensions must be positive")
    return (w, h)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Extract alpha from luminance and save as RGBA PNG. "
                    "Use for glow/VFX/light assets rendered on a solid black background."
    )
    parser.add_argument("input", type=Path, help="Source image (rendered on solid black background)")
    parser.add_argument("output", type=Path, help="Destination RGBA PNG path")
    parser.add_argument("--size", type=parse_size, default=None,
                        help="Optional output size as WxH (LANCZOS resize). Default: keep source size.")
    parser.add_argument("--formula", choices=sorted(FORMULAS), default="max",
                        help="Alpha extraction formula. max (default) preserves saturated colored glow; "
                             "luma uses human-perception weights; avg gives the softest falloff.")
    parser.add_argument("--black-threshold", type=int, default=0,
                        help="Pixels with computed alpha below this become fully transparent "
                             "(cleans dim background noise). Default 0 (off).")
    parser.add_argument("--white-cutoff", type=int, default=255,
                        help="Brightness mapped to fully opaque alpha. Lower values brighten the "
                             "alpha curve. Default 255.")
    parser.add_argument("--gamma", type=float, default=1.0,
                        help="Alpha curve gamma (>1 harder edges, <1 softer edges). Default 1.0.")
    parser.add_argument("--premultiply", action="store_true",
                        help="Multiply RGB by alpha (premultiplied alpha) for cleaner "
                             "additive/screen compositing without dark fringes.")
    parser.add_argument("--quiet", action="store_true", help="Suppress per-stats output.")

    args = parser.parse_args(argv)

    if not args.input.exists():
        parser.error(f"Input not found: {args.input}")

    stats = extract_luminance_alpha(
        args.input,
        args.output,
        size=args.size,
        formula=args.formula,
        black_threshold=args.black_threshold,
        white_cutoff=args.white_cutoff,
        gamma=args.gamma,
        premultiply=args.premultiply,
    )

    print(f"SAVED: {args.output.resolve()}")
    if not args.quiet:
        print(
            f"  size={stats['size']}, mode={stats['mode']}, "
            f"formula={stats['formula']}, premultiplied={stats['premultiplied']}, "
            f"max_alpha={stats['max_alpha']}, "
            f"nonzero_alpha_pixels={stats['nonzero_alpha_pixels']}, "
            f"corner_alpha={stats['corner_alpha']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
