---
description: Slice an atlas-style sheet into per-cell PNGs plus an atlas.json sidecar
argument-hint: '<input.png> <output-dir> <grid spec> [names...] [safe-margin]'
allowed-tools: Bash(node:*)
---

# Slice Atlas Sheet (Codex Image)

Divides an atlas sheet (uniform grid of UI/icon/button/font cells) into individual per-cell PNGs with tight non-transparent bounds. Writes an `atlas.json` sidecar with each cell's metadata (origin, tight rect, offset within cell, size) for engine positioning.

## Arguments

User invokes:

```
/codex-image:slice <input.png> <output-dir> <grid spec>
```

`<grid spec>` is free-form natural language. The Claude Code agent parses it into the structured flags the dispatcher needs. Examples:

- `"4x5 grid"` → cols=4, rows=5
- `"4x5 grid, names primary/secondary/small/wide/icon times normal/hover/pressed/locked"` → cols=4, rows=5, names array
- `"4x4 weapon icons: dagger, sword, ..."` → cols=4, rows=4, comma-separated names
- `"4x5 grid, safe margin 8"` → cols=4, rows=5, --safe-margin 8

Quote the input path if it contains spaces.

## Workflow (agent executes)

### 1. Parse user arguments

Identify:
- Input PNG path (first token; quote-aware)
- Output directory (second token)
- Grid spec (cols × rows) from the natural-language tail
- Optional cell names (if user listed them)
- Optional safe margin (default 8)

If any required field is missing or ambiguous, ask the user.

### 2. Build dispatcher command and run it

```bash
node "${CLAUDE_PLUGIN_ROOT}/scripts/codex-image.mjs" slice "<input-path>" --output-dir "<output-dir>" --grid <CxR> [--names "name1,name2,..."] [--safe-margin <N>]
```

The dispatcher shells out to `scripts/slice.py` (Pillow). Required: Python 3 + Pillow (`pip install Pillow`).

### 3. Report results to user

The dispatcher emits a JSON line on success:

```json
{ "status": "ok", "sliced": N, "empty": M, "violations": V, "output_dir": "...", "atlas_json": "..." }
```

If `violations > 0`, surface them — the source sheet has content that crosses cell boundaries (often because the source was generated without strict-grid constraints). Recommend:
1. Look at the atlas.json `violations` list to see which cells.
2. Re-generate the source sheet with explicit grid + safe-margin rules (asset-pipeline / style-gen auto-injects those rules per the v0.4.0 SKILL.md).
3. Re-run `/codex-image:slice` on the new sheet.

If `violations == 0`, output is clean and engine-ready.

## Output structure

```
<output-dir>/
├── atlas.json           # full metadata: source, sheet_size, grid, per-cell coords
├── <cell-name-1>.png    # tight-cropped, transparent-edge PNG
├── <cell-name-2>.png
└── ...
```

Each cell PNG is cropped to its tight non-transparent bounds (smaller than the cell). The atlas.json records `offset_in_cell` and `cell_origin` so the engine can re-align the cell to its original anchor if needed.

## Behavior notes

- The dispatcher is non-interactive — no prompts. All errors print to stderr.
- Cell name defaults to `r<row>c<col>` if `--names` not provided.
- `--safe-margin` only affects the violations report; it does not change cropping (cropping is always tight to non-transparent pixels).
- Cells with no non-transparent content are skipped (reported as `empty: N`).
