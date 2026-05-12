---
description: Slice an atlas-style sheet into per-cell PNGs plus an atlas.json sidecar
argument-hint: '<input.png> <output-dir> <grid spec> [names...] [safe-margin]'
allowed-tools: Bash(node:*)
---

# Slice Atlas Sheet (Codex Image)

Divides an atlas sheet (uniform grid of UI/icon/button/font cells) into individual per-cell PNGs with tight non-transparent bounds. Writes an `atlas.json` sidecar with each cell's metadata (origin, tight rect, offset within cell, size) for engine positioning.

## Arguments

Two modes:

### A) Single-sheet mode

```
/codex-image:slice <input.png> <output-dir> <grid spec>
```

`<grid spec>` is free-form natural language. The Claude Code agent parses it into the structured flags the dispatcher needs. Examples:

- `"4x5 grid"` → cols=4, rows=5
- `"4x5 grid, names primary/secondary/small/wide/icon times normal/hover/pressed/locked"` → cols=4, rows=5, names array
- `"4x4 weapon icons: dagger, sword, ..."` → cols=4, rows=4, comma-separated names
- `"4x5 grid, safe margin 8"` → cols=4, rows=5, --safe-margin 8

Quote the input path if it contains spaces.

### B) Manifest mode (slice many atlases at once)

```
/codex-image:slice --manifest <manifest.json> [--output-dir <base-dir>] [--only name1,name2,...]
```

Reads the manifest, finds every item whose `kind` is `"atlas"`, and slices each one using its declared `grid` (cols/rows/cellW/cellH), `cells` (named cell array in row-major order), and `safe_margin`. Each atlas writes its own output directory.

- `--manifest <path>`: required, points at a manifest.json with an `items[]` array.
- `--output-dir <base-dir>` (optional): write `<base-dir>/<atlas-name>/` per atlas. Default: `<manifest-dir>/<atlas-name>_sliced/`.
- `--only name1,name2,...` (optional): only slice atlases whose `name` matches the comma list. Without this flag, every atlas-kind item is sliced.

Items with any kind other than `"atlas"` (sprite-sheet / font-sheet / tileset / vfx-sheet / fill-textures / single) are **skipped** — they are intended to be read by the engine at runtime, not split into per-cell files.

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
├── <cell-name-1>.png    # cellW x cellH PNG (transparent padding preserved)
├── <cell-name-2>.png
└── ...
```

**Default: each cell PNG is uniform per atlas, with content auto-centered.** The slicer:

1. Detects the non-transparent content bbox of the whole sheet (handles asymmetric canvas padding produced by AI generators).
2. Divides that content area into `cols × rows` integer-pitch cells, centering any remainder.
3. For each cell, detects the cell's own content tight-bbox and pastes it centered onto a transparent cell-sized canvas.

The result: every output PNG for the same atlas has identical dimensions AND the icon/element inside is centered, regardless of positional drift in the source (e.g. AI generated atlas where skull is top-left in cell A and hourglass is top-right in cell B).

Flags to override:
- `--tight-crop` — output PNGs cropped to their non-transparent bbox (variable dimensions per cell). Disables uniform-size + recentering.
- `--no-recenter` — keep cell content at its raw position; do not paste-center. Use when positional layout within the cell matters (e.g. multi-state button atlases where each state is in the same spot).
- `--no-auto-bbox` — divide the raw canvas instead of the content bbox. Use when the source atlas was authored edge-to-edge with no overall canvas padding.

`atlas.json` records `tight_rect` / `tight_size` / `offset_in_cell` per cell either way, so an engine can locate the inner content if needed.

## Behavior notes

- The dispatcher is non-interactive — no prompts. All errors print to stderr.
- Cell name defaults to `r<row>c<col>` if `--names` not provided.
- `--safe-margin` only affects the violations report; it does not change cropping.
- Cells with no non-transparent content are skipped (reported as `empty: N`).
