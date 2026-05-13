# codex-image-in-cc

[![License](https://img.shields.io/github/license/gmlxo76/codex-image-in-cc.svg)](LICENSE)
[![Node](https://img.shields.io/badge/node-%3E%3D18.18-brightgreen.svg)](https://nodejs.org)

> 🇰🇷 한국어 자세한 사용 가이드: [GUIDE.md](GUIDE.md)

> **Fork notice.** This is a fork of [KingGyuSuh/codex-image-in-cc](https://github.com/KingGyuSuh/codex-image-in-cc) (Apache-2.0). The original three commands (`status`, `generate`, `edit`) are preserved; this fork adds four production-asset commands — **`style-gen`**, **`asset-pipeline`**, **`slice`**, **`organize`** — plus an end-to-end atlas pipeline (strict containment, `verify-atlas`, kind-first organize layout, transparent-output via magenta chroma key, per-kind convention blocks for sprite / UI / VFX / font / tileset). See [`NOTICE`](NOTICE) for attribution and [`CHANGELOG.md`](CHANGELOG.md) for the full evolution.

Claude Code plugin that exposes Codex CLI's built-in `imagegen` skill as `/codex-image:*` user-invoked plugin skills, with extra orchestration for shipping-quality game / app asset batches.

The plugin does not implement image generation itself. Each generation skill dispatches to `codex exec --full-auto` and lets Codex's `imagegen` skill drive the built-in `image_gen` tool, save the final artifact, and print a `SAVED: <path>` line for each output. `slice`, `organize`, and the `verify-atlas` dispatcher subcommand are Pillow / stdlib-backed Python helpers shelled out via the same Node dispatcher.

## Requirements

- Claude Code with plugin support.
- `@openai/codex` CLI v0.124.0 or later.
- An active `codex login` session.
- Node.js 18.18 or later.
- **Python 3 + Pillow** — only needed for `slice`, `organize`, and `verify-atlas`. The image-generation commands do not require Python.

`OPENAI_API_KEY` is not required for the default built-in path. Codex can use either a ChatGPT login or API-key login.

## Install

### From GitHub

```bash
claude plugin marketplace add gmlxo76/codex-image-in-cc
claude plugin install codex-image@codex-image-in-cc
```

### From a local clone

```bash
git clone https://github.com/gmlxo76/codex-image-in-cc.git
cd codex-image-in-cc
claude plugin marketplace add "$PWD"
claude plugin install codex-image@codex-image-in-cc
```

Then restart Claude Code if needed. Default install scope is `user`; pass `--scope project` or `--scope local` to limit installation.

## Plugin Skills

Seven user-invoked slash commands:

| Command | Purpose |
|---|---|
| `/codex-image:status` | Node / Codex CLI / login / `imagegen` skill availability check |
| `/codex-image:generate` | New image from text prompt only |
| `/codex-image:edit` | Modify an existing image (input attached via `codex exec --image`) |
| `/codex-image:style-gen` | New image whose visual **style** matches an attached reference (reference itself is never modified or saved) |
| `/codex-image:asset-pipeline` | Interactive batch — plan asset list from project context, confirm, generate each via `style-gen`, verify atlases |
| `/codex-image:slice` | Slice an atlas sheet into per-cell PNGs + `atlas.json` sidecar; supports single-sheet and manifest modes |
| `/codex-image:organize` | Reorganize an asset-pipeline manifest into a kind-first engine folder layout |

### Usage examples

```bash
/codex-image:status

# Generate from text prompt only
/codex-image:generate "A watercolor moonlit library, save to images/library.png at 1024x1024"
/codex-image:generate "5 logo variations of a brass compass on white, save under images/logos/"

# Edit an existing image
/codex-image:edit input.png "Replace the background with a clean white studio backdrop, save to edited.png"

# Generate a NEW image whose visual style matches a reference (the reference is
# attached as a style/composition/mood reference only — never modified or saved)
/codex-image:style-gen reference.png "A coin in this exact style, transparent background, save to assets/icons/coin.png at 512x512"
/codex-image:style-gen "concepts/hero.png" "5 variations of small UI buttons in the same visual style, save under assets/ui/"

# Batch-orchestrate style-gen across a planned asset set (interactive: plans the
# list from your project context, asks you to confirm, then runs style-gen per
# item with a sample-first gate for batches > 10)
/codex-image:asset-pipeline reference.png "RPG mobile game: 5 enemies + 10 items + 4 backgrounds + UI buttons"
/codex-image:asset-pipeline concepts/hero.png "SaaS landing: hero, 4 section illustrations, OG image, favicon"

# Slice an atlas sheet into per-cell PNGs (uniform cell size, content auto-centered)
/codex-image:slice buttons.png buttons_sliced/ "4x5 grid, names primary/secondary/small/wide/icon × normal/hover/pressed/locked"

# Or slice every atlas-kind item in a manifest at once
/codex-image:slice --manifest codex-images/manifest-2026-05-12T08-00Z.json

# Reorganize a manifest's outputs into a kind-first engine folder layout
/codex-image:organize codex-images/manifest-2026-05-12T08-00Z.json public/assets/myproject/
```

The full slash-command argument string is passed verbatim to Codex's `imagegen` skill (for the generation commands). Express output paths, sizes, quality, count, transparency, etc. as natural language inside the prompt — `imagegen` interprets them. Defaults: when no path is specified, `generate` outputs land under `./codex-images/<UTC-timestamp>-<n>.png`, `edit` under `./codex-images/<UTC-timestamp>-edit-<n>.png`, and `style-gen` under `./codex-images/<UTC-timestamp>-stylegen-<n>.png`.

For `/codex-image:edit` and `/codex-image:style-gen`, the first whitespace-separated token is the input / reference image path. Quote it if the path contains spaces (e.g. `/codex-image:style-gen "my reference.png" draw a coin in this style ...`).

**Attached-image shortcut.** All path-taking skills (`edit`, `style-gen`, `asset-pipeline`, `slice`, `organize`) also accept the chat-UI image-attachment placeholder — when `$ARGUMENTS` begins with `[Image #N]`, the agent substitutes the resolved absolute path from the nearby `[Image: source: <path>]` metadata before invoking the dispatcher.

### `edit` vs `style-gen`

Both attach an image via `codex exec --image`, but they instruct Codex differently:

| | `edit` | `style-gen` |
|---|---|---|
| Role of attached image | edit target | style reference only |
| What gets saved | modified version of the input | a brand-new image |
| Preserves input layout / content | yes (unless asked otherwise) | no — only visual style is transferred |
| Reference itself modified / output | (in-place style edit) | never |

The `style-gen` instruction prefix explicitly labels the attached image as a "supporting style input" per the [Codex `imagegen` skill's role classification](https://github.com/openai/codex/blob/main/codex-rs/skills/src/assets/samples/imagegen/SKILL.md), so Codex treats the request as `generate` rather than `edit`.

### `style-gen` vs `asset-pipeline`

| | `style-gen` | `asset-pipeline` |
|---|---|---|
| What it produces | One image set (1+ images) per invocation | A planned batch of N assets — each is its own `style-gen` call under the hood |
| Who plans the resource list | You, in your prompt | The Claude Code agent, from your project context — then you approve before execution |
| User confirmation | None (direct invocation) | Yes — plan is shown and confirmed; sample-first for batches > 10 |
| Auto-injects atlas / sprite / VFX / font / tileset rules | No — caller is responsible | Yes — based on each item's `kind` and `atlas` fields |
| Manifest | None | `./codex-images/manifest-<UTC>.json` saved for reproducibility |
| Cost | 1 Codex agent turn (× number of saved images) | N Codex agent turns (one per asset) — plus a sample-first gate to avoid wasting them on a mismatched style |

Use `style-gen` for one-off matched-style images. Use `asset-pipeline` when you've locked the style and want a project's full asset set in one go.

### `slice` vs `organize`

| | `slice` | `organize` |
|---|---|---|
| Input | A single atlas PNG, **or** a manifest of atlas-kind items | A full manifest produced by `asset-pipeline` |
| Output | Per-cell PNGs (uniform size, content auto-centered) + `atlas.json` sidecar | Kind-first folder layout: `atlas/`, `sprite-sheet/`, `tileset/{floor,objects}/`, `vfx-sheet/`, `font-sheet/`, `fill-texture/`, `single/<category>/` |
| Scope | Atlas-kind items only — sprite-sheets / tilesets / vfx-sheets are left whole | Every kind, each routed to its own folder |
| Mutates source files | No | No (copies into a new target directory) |
| Backend | `scripts/slice.py` (Pillow) | `scripts/organize.py` (Python stdlib, no Pillow) |

Run `slice` when the engine needs per-cell PNGs — typical for static UI atlases (buttons, icons, frames). Skip it when the engine UV-slices at runtime — typical for sprite-sheet animations, where the whole sheet is the consumed asset.

Run `organize` after generation when handing assets to an engine; the kind-first folder name itself tells the engine how to load each file — no manifest scan or type-sniffing required.

## What asset-pipeline auto-injects

`asset-pipeline` is more than a `style-gen` chain. It plans the work and enforces production-asset rules that AI image generators routinely violate. Users do not type these — the orchestrator applies them automatically based on each manifest item's `kind` and `atlas` fields.

- **Screen-flow + element-size planning.** Step 0 confirms the target viewport; Step A enumerates every screen the product needs; Step B sizes every element on every screen in pixels; Step C consolidates identical / near-identical elements across screens into shared atlases; Step D shows the consolidated resource list for approval before any generation. The asset-list step is the **last** thing planned, not the first.
- **Infer-beyond-the-reference.** A reference image is treated as one screen of a larger product. The planner explicitly adds the unseen-but-required screens — game-over, pause, options, 404, loading skeletons, error / empty states, etc. — so the manifest matches what a shipping product actually needs. Inferred items are flagged `inferred: true` so the user can trim for minimal scope.
- **Layer separation.** UI text, fill levels, item-in-slot, badges, count digits — all enforced as separated layers, never flattened into a single container image. Enables runtime i18n, animation, equipping, and data-driven UI.
- **9-slice design.** Frames / buttons / panels that the engine resizes are prompted with decorative corners + repeatable edges + tileable centers — no central motif that would distort when stretched.
- **Atlas strict containment.** Every atlas item carries `atlas: { cols, rows, cellW, cellH, safe_margin, cells }`. The orchestrator auto-injects strict grid + safe-margin + uniform-anchor + transparent-background + uniform-style clauses into every `style-gen` prompt, then runs the **`verify-atlas`** dispatcher (`scripts/codex-image.mjs verify-atlas`) on the output. Up to 3 regeneration attempts with progressively stricter prompts if cells bleed past the safe margin; otherwise the item is marked `failed_with_violations` and surfaced — never silently accepted.
- **Per-kind convention blocks** auto-injected by `kind`:
  - **sprite-sheet** — uniform cell, foot-anchor consistency, VFX containment, standard frame counts per action (idle 4–8 / walk 4 or 8 / attack 4–6 / hurt 2–3 / death 4–8), direction conventions (Vampire-Survivors-style 1-dir; top-down RPG 4-dir with right→left mirrored in engine).
  - **ui icon / atlas** — live-area padding (~75–85 % of cell), identical stroke weight, optical alignment, multi-state position-locking.
  - **vfx-sheet** — center pivot, alpha lifecycle (opaque → fade for one-shots; frame 1 ↔ frame N match for loops), alpha containment within cell.
  - **font-sheet** — monospace cells, shared baseline, identical stroke weight across glyphs, per-variant rows for normal / crit / heal / shield / miss (same glyph order across rows, only color differs).
  - **tileset** — floor vs objects separation, edge-to-edge floor tiles with no per-tile padding, seamless tileability (right ↔ left, top ↔ bottom), strict top-down view (no isometric / 3D edges).
- **Transparent-output pipeline.** Magenta `#FF00FF` is locked as the only allowed chroma-key color (Codex's defaults pick green inconsistently). `remove_chroma_key.py` runs with `--key #FF00FF` and standard despill; LANCZOS resize + minimal alignment crop only. Codex's default "atlas containment enforcement" post-pass (which zeroes pixels inside cell margin envelopes and silently clips decoration tips) is **forbidden** — containment is audited separately by `verify-atlas`, never by overwriting pixels.
- **Sample-first gate** for batches > 10 — generates the first 3 items, asks the user to confirm style / quality before continuing. Avoids burning a 30-item batch on a mismatched style.
- **Sequential by design.** Never parallel — concurrent `style-gen` calls would collide on the shared Codex CLI session.

Full rule reference: [`skills/asset-pipeline/SKILL.md`](skills/asset-pipeline/SKILL.md).

## Manifest schema (kind-first)

Each item in a generated `manifest.json` carries a `kind` so downstream tools (`slice`, `organize`, your engine) know how the asset is consumed:

| `kind` | What it is | Engine handling |
|---|---|---|
| `atlas` | Uniform grid of cells (icons, buttons, multi-state UI, card states) | Slice per cell at build time; load each PNG as a texture. Carries `atlas: { cols, rows, cellW, cellH, safe_margin, cells[] }` |
| `sprite-sheet` | Animation frame sheet (idle / walk / attack / death) | Load whole sheet; engine UV-steps at runtime |
| `tileset` | Floor or objects tileset (`subkind: "floor"` or `"objects"`) | Floor tiles paint edge-to-edge for ground fill; objects sliced into decoration sprites at specific coords |
| `vfx-sheet` | VFX flipbook | Load whole sheet; engine plays frame sequence over time |
| `font-sheet` | Bitmap font / i18n label sheet | Glyph lookup at render time |
| `fill-texture` | Runtime composite layer (HP fill, mask, tintable strip) | Composited onto an empty container at runtime |
| `single` | Single illustration (background, portrait, splash, hero) | One static image |

`organize` reads this `kind` and lays out each asset under `atlas/<name>/`, `sprite-sheet/`, `tileset/floor/` or `tileset/objects/`, `vfx-sheet/`, `font-sheet/`, `fill-texture/`, or `single/<category>/`. The folder name itself is the rendering contract.

## Development

```bash
npm test
npm run validate:plugin
npm run status
claude --plugin-dir .
```

After editing plugin skills during a `claude --plugin-dir .` session, run `/reload-plugins`.

Image generation consumes a Codex agent turn plus the built-in `image_gen` tool usage. `slice`, `organize`, and `verify-atlas` are local Python — they do not consume Codex turns.

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for scope, dev setup, and PR conventions, and [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the call flow and load-bearing edge cases. Security issues — see [`SECURITY.md`](SECURITY.md).

## Attribution

Forked from [KingGyuSuh/codex-image-in-cc](https://github.com/KingGyuSuh/codex-image-in-cc). All credit for the original `status` / `generate` / `edit` design and the dispatcher architecture goes to KingGyuSuh. See [`NOTICE`](NOTICE) for the full attribution and modification summary as required by Apache-2.0 §4.

## License

[Apache-2.0](LICENSE).
