---
description: Reorganize an asset-pipeline manifest into a kind-first engine folder layout
argument-hint: '<manifest.json> <target-dir> [--no-sliced]'
allowed-tools: Bash(node:*)
---

# Organize Manifest (Codex Image)

Takes an asset-pipeline manifest with `kind`-tagged items (atlas / sprite-sheet / tileset / vfx-sheet / font-sheet / fill-texture / single) and copies every asset into a **kind-first** folder layout suitable for game engine consumption. Atlases bring their source PNG, `atlas.json` sidecar, and per-cell sliced PNGs together in one folder. The new manifest at the root of the target dir has all `items[].path` values rewritten to the new locations.

## Arguments

User invokes:

```
/codex-image:organize <manifest.json> <target-dir>
```

The Claude Code agent parses the two positional args (plus optional `--no-sliced` flag) and builds the dispatcher call.

## Target layout

```
<target-dir>/
├── manifest.json                       ← rewritten paths, layout_note
│
├── atlas/<name>/<name>.png             ← source sheet
├── atlas/<name>/atlas.json             ← cell metadata (if present)
├── atlas/<name>/<cell>.png             ← every sliced cell (if <name>_sliced/ exists)
│
├── sprite-sheet/<name>.png             ← animation frame sheets (engine UV-steps)
│
├── tileset/floor/<name>.png            ← when item.subkind == "floor"
├── tileset/objects/<name>.png          ← when item.subkind == "objects"
├── tileset/<name>.png                  ← when no subkind declared
│
├── vfx-sheet/<name>.png                ← VFX flipbooks (engine plays frame sequence)
│
├── font-sheet/<name>.png               ← bitmap fonts / i18n label sheets
│
├── fill-texture/<name>.png             ← runtime composite layers
│
└── single/<category>/<name>.png        ← single illustrations, category from
                                          item.category or inferred from source
                                          folder (bg / portrait / item / ui / vfx)
```

## Why this layout

An AI agent (or human) reading the folder name knows the asset's purpose AND how the engine handles it:

| Folder | What the engine does |
|---|---|
| `atlas/<name>/<cell>.png` | Load per-cell PNG directly as a texture; no runtime cropping. |
| `sprite-sheet/<name>.png` | Load whole sheet, animate by UV-stepping at runtime. |
| `tileset/floor/<name>.png` | Paint seamless tile to fill ground (edge-to-edge, no padding). |
| `tileset/objects/<name>.png` | Slice into standalone decoration sprites placed at specific coords. |
| `vfx-sheet/<name>.png` | Play frame sequence over time (flipbook). |
| `font-sheet/<name>.png` | Look up glyphs / labels at render time. |
| `fill-texture/<name>.png` | Composite over a container at runtime (HP fill inside an empty orb, etc.). |
| `single/<sub>/<name>.png` | Render as one static image. |

No type-sniffing, no manifest scan needed to decide rendering strategy — the path alone says it.

## Workflow (agent executes)

### 1. Parse user arguments

- First token = source manifest path (must be a valid `manifest.json` produced by the asset-pipeline).
- Second token = target directory (the kind-first layout root, often something like `public/assets/<game-namespace>/`).
- Optional `--no-sliced`: skip looking for `<atlas-name>_sliced/` directories beside each atlas item.

Quote paths that contain spaces. If a required field is missing or ambiguous, ask the user.

### 2. Build dispatcher command and run

```bash
node "${CLAUDE_PLUGIN_ROOT}/scripts/codex-image.mjs" organize "<manifest>" --output-dir "<target>" [--no-sliced]
```

The dispatcher shells out to `scripts/organize.py`. Required: Python 3 (no Pillow needed — only `shutil` and `json`).

### 3. Report results to user

The dispatcher prints a summary like:

```
  atlas/buttons/      (22 files)
  atlas/cards/        (6 files)
  ...
  sprite-sheet  sprite-sheet/vaelis.png
  tileset       tileset/floor/graveyard.png
  ...

manifest -> <target>/manifest.json

--- summary ---
  total files: 217
  atlas: 15 items
  sprite-sheet: 2 items
  ...
```

If items are skipped (missing kind, missing source path), the dispatcher prints a `WARN:` line per skipped item and keeps going. Surface these to the user when reporting.

## Notes

- The dispatcher REMOVES the target directory if it already exists, then writes fresh. The source manifest dir is never modified.
- Atlas sliced cells are picked up from `<src-dir>/<atlas-name>_sliced/` (the default output dir of `/codex-image:slice`). Pass `--no-sliced` to skip this step (e.g., when you only want the source sheets without per-cell extractions).
- Items without `subkind` under `tileset` are placed at `tileset/<name>.png`. Specify `subkind: "floor"` or `subkind: "objects"` in the manifest to land in `tileset/floor/` or `tileset/objects/` respectively.
- For `single` items, the dispatcher tries `item.category` first, then the first segment of the source path (`bg/title.png` → `bg`). If neither yields a recognized hint, it falls back to that raw first segment.
