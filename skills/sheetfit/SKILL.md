---
description: Strictly normalize an AI-generated animation sprite sheet so every grid cell is the SAME size and center-anchored, output as one engine-ready sheet. Auto-runs after any sprite-sheet/animation-sheet generation.
argument-hint: '<sheet.png> <grid spec e.g. "4x9"> [align-by] [tolerances]'
allowed-tools: Bash(node:*)
---

# Sheetfit — Animation Sprite Sheet Normalizer (Codex Image)

AI image generators draw each frame of a sprite sheet independently, so frames end
up at slightly different positions and sizes. If you slice such a sheet on a fixed
grid, the animation **jumps/jitters**. `sheetfit` is the **mandatory strict gate** that
fixes this: it verifies every cell shares the same content size + center anchor,
and if not, normalizes (size + position) and recomposes the frames into **one
corrected sheet** — then strictly re-verifies.

Output is a single **engine-ready sheet** (NOT per-cell files), so in Unity you set
**Sprite Mode = Multiple → Slice → Grid by Cell Count (cols × rows)** and every row
(one animation) plays registered with no jump.

## When to use — ALWAYS for sprite/animation sheets

**This is not optional.** Run `sheetfit` on the result of ANY sprite-sheet or
animation-sheet generation, every time, before the sheet is considered done:
- right after `/codex-image:generate` or `/codex-image:style-gen` produces a sheet
  whose content is a grid of animation frames,
- on every sprite-sheet / animation-sheet item produced by `/codex-image:asset-pipeline`.

If `sheetfit` reports `status: "rework"`, the sheet is NOT acceptable — **regenerate
the source sheet** (label-free, transparent gutters between every cell, strict even
grid, same character scale per cell) and run `sheetfit` again. Repeat until
`status` is `"fixed"` or `"pass"`.

## Source sheet requirements (so the gate can pass)

- **No text/labels inside the image** (labels break grid division).
- **Transparent gutters** between every row and column; content never touches a cell edge.
- **Strict even grid**, same character scale and baseline in every cell.
- Transparent background (chroma-keyed).

## Arguments

```
/codex-image:sheetfit <sheet.png> <grid spec>
```

- `<sheet.png>`: the generated sheet (quote if path has spaces).
- `<grid spec>`: free-form; the agent parses cols × rows. `"4x9"` → cols=4, rows=9.
- Optional: `--anchor bottom|center` (default `bottom` — feet planted, best for
  ground creatures), `--pad N` (transparent padding inside each cell, default 4),
  `--output <path>`, `--check` (verify only, write nothing).

## Run it

```bash
node "${CLAUDE_PLUGIN_ROOT}/scripts/codex-image.mjs" sheetfit "<sheet.png>" --grid <CxR> [--anchor bottom|center] [--pad 4] [--output <path>]
```

How it works: detects the TRUE frame grid via transparent GUTTERS (robust to uneven
AI spacing — NOT a naive even split), tightly trims each frame, sizes every cell to
the max frame extent + padding, re-anchors each frame consistently, and recomposes
into one corrected sheet. STRICT: it requires exactly `cols` column bands and `rows`
row bands with uniform column widths; labels, touching frames, or an uneven grid make
detection fail → `status: "rework"`. By default the fixed sheet is written next to the
input as `<name>_fixed.png` with a `<name>_fixed.sheet.json` sidecar.

## Result contract

The dispatcher prints one machine-readable line:

```
SHEETFIT {"status":"pass|fixed|rework","input":"...","output":"...","grid":"4x9","cellWidth":N,"cellHeight":M,...}
```

- `pass` — source was already uniform/aligned (exit 0). Use `output` as-is.
- `fixed` — normalized + recomposed into `output` (exit 0). Use `output`. Slice in
  Unity with Grid by Cell Count = grid, or Grid by Cell Size = `cellWidth × cellHeight`.
- `rework` — could not be made uniform (exit 1). **Do NOT ship it.** Regenerate the
  source sheet per the requirements above and re-run. This is the strict, adversarial
  behavior: when in doubt, fail and rework.

## Notes

- Implemented by `scripts/sheetfit.py` (Pillow + numpy).
- `--check` only verifies and reports (writes nothing) — exit 1 if not normalizable.
- Bottom-center anchor keeps the character grounded across frames; for frames that
  change shape a lot (e.g. an attack lunge) the top may move while the base stays
  fixed — usually what you want. Use `--anchor center` for symmetric content.
