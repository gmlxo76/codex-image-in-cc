# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Docs

- `README.md` rewritten to cover 0.3.x–0.4.x scope: documents all seven slash commands (the previous README had stopped at `style-gen` and `asset-pipeline`), adds a "What asset-pipeline auto-injects" section summarizing screen-flow planning / layer separation / 9-slice / atlas strict containment + `verify-atlas` regen loop / per-kind convention blocks / transparent-output magenta-key pipeline / sample-first gate, adds a kind-first manifest schema table, adds a `slice` vs `organize` comparison, updates the fork notice to mention all four fork-added commands, and adds Python 3 + Pillow to Requirements.

## [0.4.8] - 2026-05-21 — luminance-based alpha extraction for glow / VFX content

### Added

- **`scripts/luminance_alpha.py`** — new standalone helper that converts a black-background PNG into an RGBA PNG with alpha derived from pixel brightness (`alpha = max(R, G, B)` by default; `--formula luma` and `--formula avg` available). Supports `--size WxH` LANCZOS resize, `--black-threshold` / `--white-cutoff` for alpha curve shaping, `--gamma` for edge softness, and `--premultiply` for additive/screen compositing. Provides a clean alternative to the magenta chroma-key pipeline for luminous content (glow, neon, VFX, light sources) where chroma blending leaves colored fringe artifacts.
- **Auto-detect transparency method in `scripts/codex-image.mjs`** — new `applyTransparencyPipeline()` helper that inspects the user prompt for luminance-trigger keywords (English: `glow`, `luminous`, `neon`, `vfx`, `halo`, `particle`, `sparkle`, `radiance`, `aura`, `lightning`, `ember`, `flame`, `magical`, `lens flare`, ...; Korean: `글로우`, `발광`, `빛나는`, `네온`, `광원`, `후광`, `오라`, `파티클`, `반짝`, `스파크`, `광휘`, `할로`, `이중 링`, ...) and selects luminance vs chroma-key automatically. Wired into `handleGenerate` / `handleEdit` / `handleStyleGen`. The chosen method is logged to stderr as `[codex-image] transparency method: <method>`.
- **`--transparency=<auto|luminance|chroma|none>` flag** — explicit override inside the natural-language prompt. The flag is stripped from the prompt before the request reaches Codex CLI. Aliases: `luma` → `luminance`, `magenta` → `chroma`, `off` → `none`.

### Changed

- **`skills/style-gen/SKILL.md`** — new "Transparency: luminance vs chroma key (auto-detected)" section documents the two pipelines, when to use each, the keyword auto-detection rules, and the explicit override flag. Includes a caveat about dark intentional content under the luminance method.
- **`skills/asset-pipeline/SKILL.md` Transparent-Output Pipeline section** — restructured into Method A (luminance, for luminous content) and Method B (chroma key, for flat content) with a method-selection decision tree. The agent is instructed to inject the matching pipeline clause as belt-and-suspenders enforcement (in addition to the dispatcher's auto-detection) and to document the chosen method in the manifest.

### Why

While generating luxury gold UI buttons with strong glow halos against the magenta chroma key (`#FF00FF`), the soft edges of the glow consistently came back with purple/pink fringe contamination. The chroma-key removal cannot fully recover the original color of semi-transparent gold pixels that blended with magenta during generation — the dim gold + magenta produces purple, and that purple is neither pure magenta nor pure gold, so subtracting magenta leaves a colored ring around the glow. The luminance method side-steps the problem entirely: render on solid black, recover alpha from brightness. No chroma key color ever exists in the image, so semi-transparent glow pixels stay the color they were drawn. The natural brightness falloff of a glow becomes a natural alpha falloff — clean, no fringe. This is the same technique game engines have used for VFX / light sprites for decades.

The auto-detection keeps the magenta pipeline as the default safe choice for flat content (icons, items, characters, tilesets), but routes glow / VFX prompts to luminance without the user having to know either method exists. Explicit flags are available for the cases auto-detection guesses wrong.

## [0.4.7] - 2026-05-13 — asset-pipeline consolidates shared elements before drafting manifest

### Added to `skills/asset-pipeline/SKILL.md`

- **Step C — Consolidate identical/near-identical elements across screens.** This was the single most important planning step that was previously missing. Most assets in a real shipping product are SHARED across many screens (back arrow on every sub-screen, primary button on every CTA, modal frame on every dialog, HP icon in HUD and results screen). Per-screen asset drafting generates the same button 5–7 times across screens — wastes tokens, creates visual drift, and makes the manifest a guess instead of an audit.
- Consolidation procedure: take every element from every screen's Step B table, group identical/near-identical elements by visual purpose, set each consolidated asset's pixel size to the LARGEST display size across all consumers (so it stays sharp at every site, never upscaled), and tag each consolidated asset with `used_by: [screen1, screen2, ...]` so the user can audit the sharing.
- Worked examples baked into the SKILL.md table — three per-screen back arrows → ONE `nav-icons` atlas used by 5+ screens; four per-screen CTA buttons → ONE `buttons` atlas with primary/secondary/danger × states; three per-screen modal frames → ONE 9-slice `modal-frame`; HUD vs results vs bestiary HP icons → ONE 64×64 `hud-icons` atlas (downscaled at HUD).
- **Step D — Present the consolidated resource list before drafting the manifest.** Adds a second user-approval gate that shows the consolidated list (Asset / Kind / Pixel size / Used by / Inferred?) before any manifest entry is written. Up to 3 refinement rounds.
- Each manifest entry's `size` field must trace back to specific pixel measurements from Step B and carry forward the `used_by` array so future maintainers can see why the asset was sized the way it was.

### Why

During the second asset-pipeline test run, the planner drafted a per-screen manifest where the same back-arrow icon appeared as three separate items (`back-arrow-charselect`, `back-arrow-options`, `back-arrow-bestiary`), the same primary button appeared four times (`button-start-hunt`, `button-resume`, `button-quit`, `button-restart`), and three near-identical modal frames were planned separately (`pause-modal-frame`, `confirm-quit-frame`, `gameover-stats-frame`). The user (gmlxo76) pointed out that a real shipping product uses ONE shared asset for each of these. Without an explicit consolidation step the planner naturally produces inflated, drift-prone manifests; codifying Step C makes consolidation the rule, not an afterthought.

## [0.4.6] - 2026-05-13 — asset-pipeline planning does screen-flow + element-size FIRST

### Added to `skills/asset-pipeline/SKILL.md`

- **Step 0 — Confirm target viewport** via `AskUserQuestion` before any planning. Options cover Mobile portrait (430×932 / 390×844 / 360×800), Mobile landscape, Tablet portrait, Desktop web (1440×900), and Mobile+Desktop responsive. Every downstream size calculation (atlas cell size, backdrop dimensions, icon pixel size) depends on this answer; without it, asset sizes are guesses.
- **Step A — Enumerate every screen in the flow**, not just the one in the reference. Uses the existing inference rules to add overlays (level-up, pause, confirmation dialogs), error/empty states, transitions (loading), and meta screens (settings, bestiary, achievements) implied by the product type.
- **Step B — Size every element on every screen** as a Y-range / pixel-rectangle table at the target viewport (`| Y range | Element | Size | Notes |`). Position (x, y, w, h) + display purpose, written per screen. The asset-list step is the LAST thing planned, not the first.
- **Step E — Draft the manifest from Step B–D's pixel measurements.** Each `size` field must trace back to specific pixel dimensions in Step B (e.g. "cellW=64 because the stat-icons show at 64×64 in the character card stat row at viewport 430×932").

### Why

The previous planning flow jumped straight from "context string" to "list of PNGs to generate." Real shipping products need a screen-level design pass first, because the same visual element has a SPECIFIC PIXEL SIZE per screen and that pixel size determines the asset's source resolution, atlas cell size, and whether it can be shared with other screens. Skipping screen-level layout produced manifests where stat-icons were sized 256×256 ("just in case") for a screen that actually displays them at 64×64 — wasting tokens and producing visually mismatched output. Step 0–B force the layout to be done explicitly, in pixels, against a confirmed viewport.

## [0.4.5] - 2026-05-12 — /codex-image:organize for kind-first engine layout

### Added

- **`/codex-image:organize <manifest.json> <target-dir>`** — new user-invoked slash command. Reads a `kind`-tagged manifest (asset-pipeline output) and copies every asset into a folder layout where the path itself describes how the engine should consume each asset.
- **Target layout:**
  - `atlas/<name>/<name>.png` + `atlas.json` + `<cell>.png × N` (sliced cells bundled if present)
  - `sprite-sheet/<name>.png` (engine UV-steps at runtime)
  - `tileset/floor/<name>.png` (seamless edge-to-edge ground fill)
  - `tileset/objects/<name>.png` (standalone decoration sprites)
  - `vfx-sheet/<name>.png` (flipbook animation)
  - `font-sheet/<name>.png` (bitmap font / i18n labels)
  - `fill-texture/<name>.png` (runtime composite layer)
  - `single/<sub>/<name>.png` (one static illustration, subdir from `item.category` or inferred from source folder)
  - `manifest.json` at the target root with all `items[].path` values rewritten to the new locations
- **`scripts/organize.py`** — Python 3 stdlib (no Pillow); REMOVES the target directory if it exists, then writes fresh. Source manifest dir is never modified. Sliced cells picked up from `<src-dir>/<atlas-name>_sliced/` by default (`--no-sliced` to skip).
- Optional `--only name1,name2,...` to filter, `--output-dir` for custom base.
- **`skills/organize/SKILL.md`** — user-facing slash command definition.

### Why

An engine (or another AI agent) reading the folder name alone should know the asset's purpose AND how to load it. Without this layout, every downstream consumer has to scan the manifest and type-sniff each item — atlases want per-cell PNGs, sprite-sheets want the whole sheet for UV-stepping, floor tilesets want seamless edge-to-edge painting, VFX want flipbook playback. The kind-first folder names make the rendering contract self-documenting and remove the per-engine scan code.

## [0.4.4] - 2026-05-12 — tilemap conventions

### Added to `skills/asset-pipeline/SKILL.md`

- **Tilemap Conventions** section with four rules auto-applied when a manifest item is a tileset:
  1. **Floor tiles and object/decoration sprites are SEPARATE atlases** (`floor-<biome>.png` vs `objects-<biome>.png`). They are two different rendering passes — floor fills every map cell continuously; objects sit on top at specific spots. Packing them together complicates extraction and placement.
  2. **Floor tiles are FLAT SQUARE, EDGE-TO-EDGE, NO PADDING.** Each tile fills 100% of its cell. No transparent corners, no diamond/hexagonal shape, no per-tile background gap. Safe-margin envelopes (used for icons/buttons) do NOT apply to floor tiles — even 1px of edge padding makes two adjacent tiles render with a visible gap in the stitched map.
  3. **Floor tiles must be SEAMLESSLY TILEABLE.** Right edge column matches left edge column; top edge row matches bottom edge row. Patterns near edges flow continuously across the seam; no hard borders or vignettes. Different variants don't have to seam-match each other — only copies of themselves. Organic/noisy textures (dirt, grass, sand, stone) tile much better than geometric patterns. No centerpiece focal elements (they tile visibly when repeated 4×4).
  4. **TOP-DOWN view only.** For top-down 2D games (Vampire Survivors, Hades, Diablo-like camera), no isometric perspective, no tilted edges, no drop shadows under the tile.
- **Required prompt clauses for floor-tile generation** — auto-injected by the agent when a manifest item is `kind: "tileset"` (or has `subkind: "floor"`). Forces flat square + top-down + seamless + no centerpiece + uniform palette.
- **Decoration/object tilesets** retain the standard atlas containment rules (safe margin, centered anchor, transparent background). Only floor/terrain tilesets get the seamless edge-to-edge rules.

### Why

Tilemaps have two fundamentally different rendering strategies (floor fill vs object placement) and AI generators conflate them by default — producing "graveyard tileset" outputs where tombstones are baked into floor cells, leaving the engine unable to tile the floor or place the decorations independently. The seamless tileability rule is similarly invisible: a tile that looks fine in isolation will produce visible seams when actually stitched into a map. Codifying these four rules into the SKILL.md moves what was tribal knowledge into auto-enforcement.

## [0.4.3] - 2026-05-12 — transparent-output pipeline + manifest-driven slice + uniform centered cells

### Added to `skills/asset-pipeline/SKILL.md`

- **Transparent-Output Pipeline section** — five clauses auto-injected into every style-gen prompt for transparent items (which is most UI / sprite / icon items):
  1. Force MAGENTA `#FF00FF` as the chroma-key background color (no green, no blue, no auto-pick).
  2. Run `$CODEX_HOME/skills/.system/imagegen/scripts/remove_chroma_key.py --key #FF00FF` for alpha extraction; standard despill allowed.
  3. LANCZOS resize to requested output dimensions is allowed (preserves content↔cell geometry).
  4. **FORBIDDEN**: any per-pixel alpha-clearing pass that loops through cells and zeroes pixels within a margin envelope. This is the destructive step that Codex's default pipeline runs and that silently clips decoration tips (spike corners, glow halos, ornament fringes) the prompt deliberately placed inside the safe-margin guidance. Hard-cropping anything beyond a few border alignment pixels is also forbidden.
  5. After resize + alignment crop, the result IS the final asset. Containment is then audited by `verify-atlas`; if violations are found, regenerate with stricter prompt-level instructions — never by overwriting pixels.

### Added to `scripts/codex-image.mjs` + `skills/slice/SKILL.md`

- **`slice --manifest <path>` mode** — reads a manifest and slices every item with `kind == "atlas"` using its declared grid / cells / safe_margin fields. One command slices an entire project at once. Non-atlas kinds (`sprite-sheet`, `font-sheet`, `tileset`, `vfx-sheet`, `fill-texture`, `single`) are intentionally skipped — they are consumed whole by the engine.
- Flags: `--output-dir <base>` for custom base, `--only name1,name2,...` for filtering, `--no-sliced` skipped per-atlas.

### Changed in `scripts/slice.py`

- **Auto-bbox detection + integer pitch + centered paste are now defaults.** AI-generated atlases carry asymmetric canvas padding (e.g. L=33 T=17 R=28 B=39); slicing by `sheetW / cols` misaligns cells with where the content actually sits. Now the slicer detects the alpha bbox of the whole sheet and divides THAT area into cells.
- Integer pitch + centered offset means every cell in an atlas has identical output dimensions (no ±1px rounding drift).
- Per-cell content tight-bbox is detected and pasted centered onto a transparent cell-sized canvas, so AI-generated icons whose positions drift within their cells (skull top-left, hourglass top-right, arrow bottom-left) all come out as same-sized centered PNGs.
- Override flags: `--tight-crop` (variable per-cell dimensions), `--no-recenter` (keep raw position), `--no-auto-bbox` (use raw canvas).

### Why

Three independent pain points, one release. (1) Codex's default transparency pipeline silently destroys requested decoration — observed multiple times with corner spikes and ornament fringes vanishing despite the prompt explicitly placing them inside the safe margin. (2) Per-atlas slicing was tedious for a 15-atlas batch. (3) AI-generated atlases drift in both canvas padding and per-cell content position, so engine-consumed per-cell PNGs were misaligned without manual fix-up. All three are now handled by default.

## [0.4.0] - 2026-05-12 — atlas strict containment + slice command

### Added

- **`/codex-image:slice <input.png> <output-dir> <grid spec>`** — new user-invoked slash command. Slices a uniform-grid atlas sheet into per-cell PNGs with tight non-transparent bounds, plus an `atlas.json` sidecar containing each cell's origin, tight rect, offset within cell, and size. Backend: `scripts/slice.py` (Python 3 + Pillow). Naming: cells default to `r<row>c<col>`, or you can pass an explicit name list.
- **`verify-atlas` dispatcher subcommand** — checks a sheet's cell-internal content respects a safe-margin envelope; reports per-cell violations as JSON. Exits 0 if clean, 1 if any cell bleeds across the margin. Used by asset-pipeline to validate atlas generation.
- **Atlas Strict Containment Conventions** in `skills/asset-pipeline/SKILL.md` — for any item with an `atlas: { cols, rows, cellW, cellH, safe_margin, cells }` field in the manifest, the agent auto-injects strict grid + safe-margin + uniform-anchor + transparent-background + uniform-style clauses into the style-gen prompt. After generation, the agent runs verify-atlas and regenerates up to 3 times if cells bleed past the safe margin. The user never types these rules; the SKILL.md enforces them based on manifest metadata.
- **`skills/slice/SKILL.md`** — user-facing slash command definition that parses natural-language grid spec ("4x5 grid", optional cell-name list, optional safe margin) and dispatches to the slice subcommand.

### Why

AI image generators do not respect strict grid boundaries by default. Buttons, ornaments, and glows leak across cell boundaries; when sliced by uniform grid, content gets clipped. The previous SKILL.md rules (uniform cell, consistent anchor) were necessary but not sufficient — the agent needed an explicit, measurable safe-margin envelope plus an automated verification + regeneration loop. The new `atlas` manifest field carries that metadata, the SKILL.md applies it automatically, and the new verify/slice tooling closes the loop.

### Notes

- Slicing is intentionally **user-invoked**, not auto-run by asset-pipeline. The agent surfaces the slice command after each atlas generation but lets the user decide when to extract. This keeps sheet inspection in the user's hands and avoids polluting output directories for sheets used as animation atlases.
- Backend requires Python 3 + Pillow. The dispatcher prints install instructions if Python isn't found.

## [0.3.3] - 2026-05-11 — layer separation + 9-slice rules

### Added to `skills/asset-pipeline/SKILL.md`

- **CRITICAL: Layer separation — content vs container** — UI must be authored as separated layers, never flattened. Buttons separate frame from label (for i18n), progress bars separate track from fill (for animation), orbs separate frame from liquid, slots separate frame from item icon, counters separate panel from icon and from number digits, cards separate frame from portrait and from name-plate text, locked variants separate base art from padlock overlay. Decision table maps each common component to its required layer breakdown.
- **CRITICAL: 9-slice scaling** — frames/buttons/panels that the engine resizes must be designed with fixed decorative corners, stretchable repeatable edges, and a solid/tileable center. Prompts for resizable container assets must explicitly include 9-slice design guidance.
- **Practical manifest implications** — for every visible composite, the manifest must list multiple items (container + each content layer). Verification step expanded: no language-specific text baked into UI elements (logo branding is exempt), no fill levels baked into bars/orbs, no specific item icons baked into slots, frames intended for resizing have decorative corners and repeatable edges.

### Motivation

During the MVP asset-pipeline run, the agent generated several UI sheets (`hud-orbs`, `hud-panels`, `buttons`, `map-nodes`, `weapons`) with content fully baked into containers — red liquid painted inside the HP orb at a fixed %, "START HUNT"/"OPTIONS" text baked into button images, padlock icons painted onto locked map nodes, weapon icons embedded inside slot frames. The user (gmlxo76) pointed out that none of these are usable in a real shipping game: localization requires text on a separate layer, runtime fill animation requires bar background separate from fill, and runtime equip requires slot separate from item icon. The user then asked the rule be generalized and codified into the SKILL.md so future invocations don't repeat the mistake.

Sources for the rules: Gridly game UI localization best practices, Unity Localization documentation, Unity Manual 9-slicing, GameMaker 9-slice docs.

## [0.3.2] - 2026-05-11 — infer beyond reference (universal) + UI granularity rules

### Added to `skills/asset-pipeline/SKILL.md`

- **CRITICAL: Infer beyond the reference (universal rule, every domain)** — the agent must NOT limit the plan to literally-visible assets. Whatever the reference depicts — game, SaaS dashboard, e-commerce page, mobile app, restaurant menu, banking flow — a real shipping product needs many assets that aren't in any single screenshot. For every visible element the agent must ask "what other screens/states/assets must exist around this one?" and add whatever it answers "obviously also exists" to the manifest. Includes a multi-domain checklist (game / RPG / mobile / web / e-commerce / SaaS / forms / banking / social / marketing) of unseen-but-required assets to add. Items inferred from logic rather than observed in the reference are flagged `inferred: true` so the user can trim if they want minimal scope.
- **CRITICAL: Don't under-spec UI** — a single in-product screen typically implies 10-15 distinct UI sheets (logo/typography, button states, frames, panels, icons, indicators, etc.). When the reference shows any UI, the plan must reflect that granularity — never group everything into a single "ui-misc" bucket.

### Motivation

During the asset-pipeline test on 2026-05-11, the agent under-planned five times in a row (10 → 20 → 24 → 26 → 40 items), each time missing entire categories — at first only "2 enemy types and 1 tileset", then conflating portraits with sprite-sheets, then missing 80% of the UI elements visible in the reference, then missing genre-essential screens (game-over / pause / options / bestiary / upgrades) that weren't visible at all but every shipping product has. The user had to call out each under-spec individually, then explicitly request the rule generalize to "any product, not just games — whatever the reference depicts, infer the surrounding screens/states a real user would expect." These two rules move that principle from tribal knowledge into the SKILL.md so future invocations don't repeat the under-spec pattern.

## [0.3.1] - 2026-05-11 — asset-type conventions baked into SKILL.md

### Fixed / Added

`skills/asset-pipeline/SKILL.md` now includes three concrete rule sections that AI image generators violate by default unless explicitly constrained. Each section ends with a mandatory verification step (read the output, check the rules, recommend regenerate if they fail — do NOT gloss with "looks good" without naming what was verified).

- **Sprite Sheet Conventions** — uniform cell size, consistent character bounding box and bottom-center anchor, VFX containment within cells, style/palette consistency across frames. Standard frame counts (idle 4-8 / walk 4-8 / attack 4-6 / hurt 2-3 / death 4-8) and direction conventions (1-dir for Vampire-Survivors-style, 4-dir for top-down RPG; left/right mirrored in-engine so don't generate both sides).
- **UI Icon Sheet Conventions** — uniform cell, live-area padding (~75-85% of cell), identical stroke weight, optical alignment (not just bounding-box alignment), transparent backgrounds, multi-state alignment (icon stays in same position across normal/hover/pressed/disabled). Standard cell sizes (24/32/48/64/96/128 by use case) and grouping rule (one coherent set per sheet, never mix unrelated icons).
- **VFX Sheet Conventions** — uniform cell, alpha containment within cell, center-pivot anchoring, alpha lifecycle (opaque → fade for one-shots; first/last must match for loops), looping continuity. Standard frame counts by effect type (hit 4-6 / explosion 8-12 / beam 4-8 looping / aura 8-12 looping / level-up 6-8 one-shot / death-dissolve 4-8 one-shot).
- **Number / Bitmap Font Sheet Conventions** — required glyph sets (minimum 0-9, standard adds `. - +`, extended adds `, / × !`), monospace recommended for easier runtime layout, uniform cell + shared baseline (all digits the same height), identical stroke weight across all glyphs, outline/shadow for readability on busy backgrounds, per-variant rows for damage/crit/heal/shield/miss (same glyph order across rows, only color changes). Standard cell sizes by use case (HUD scores 16-24 / damage numbers 32-48 / big crit 64-96).

`skills/style-gen/SKILL.md` gets a shorter mirror of the sprite sheet rules for direct style-gen sheet invocations.

GUIDE.md updated to mention the sprite-sheet conventions section.

### Motivation

The first real asset-pipeline test (2026-05-11) produced a sprite sheet where cell anchors drifted between idle/walk/attack/death rows and VFX trails spilled outside their cells, and I (the agent) presented it as "OK" without actually scrutinizing the result. The user caught both the asset issue AND the verification gap. This release moves the rules from tribal knowledge into the SKILL.md so future invocations don't repeat the mistake — and adds a mandatory verification step so the agent must inspect and critique its own output before claiming success.

Sources for the rules: Unity Sprite Editor docs, Slynyrd Pixelblog (top-down character animation), Aseprite pivot conventions, design system iconography guides, particle/flipbook standards from PlayCanvas/Unity/Effekseer.

## [0.3.0] - 2026-05-11 — asset-pipeline orchestrator

### Added

- `/codex-image:asset-pipeline <reference-path> <project context>` — high-order orchestration of `/codex-image:style-gen`. Given a locked style reference and a project context (e.g. "RPG mobile game with 5 enemies + 10 items"), the Claude Code agent plans the asset list, confirms it with the user, saves a `manifest-<UTC>.json`, and runs `style-gen` once per item. For batches over 10 items, a **sample-first** gate generates the first 3 and asks the user to confirm before continuing — designed to avoid burning a full batch on a mismatched style.
- `parse-args` dispatcher subcommand — tiny arg validator (path/context split + exists check) used by the asset-pipeline skill at step 1.
- `skills/asset-pipeline/SKILL.md` with the full step-by-step orchestration (parse → plan → confirm → save manifest → sample-first → execute → report). Planning is done by the Claude Code agent itself (no Codex turn) so token cost lives entirely in generation.
- `renderStatusReport` now lists `style-gen` and `asset-pipeline` in its Usage examples.
- All three path-taking skills (`edit`, `style-gen`, `asset-pipeline`) now document the `[Image #N]` attached-image shortcut — when the user attaches an image via the chat UI, Claude Code passes a placeholder in `$ARGUMENTS` and exposes the real path as `[Image: source: <abs-path>]` metadata; the skills now instruct the agent to substitute that resolved path before invoking the dispatcher.
- `GUIDE.md` — comprehensive Korean usage guide (install, all five commands, typical workflow, known limits, troubleshooting).

### Notes

- Planning intentionally does **not** call Codex — planning is text-only reasoning that the Claude Code agent can do for free. Codex turns are reserved for image generation. A 30-item batch is ≈ 30 Codex turns total.
- The asset-pipeline skill is sequential by design — parallel style-gen calls would compete for the shared Codex CLI session.

## [0.2.0] - 2026-05-11 — fork by gmlxo76

### Added

- `/codex-image:style-gen <reference-path> <generate instructions>` — generate a brand-new image whose visual style (palette, line weight, shading, composition language, mood) matches an attached reference. The reference is attached via `codex exec --image` and labeled as a "supporting style input" per the Codex `imagegen` skill's role classification — Codex treats the request as `generate`, not `edit`. The reference itself is never saved or modified.
- New `STYLE_GEN_INSTRUCTION_PREFIX` in `scripts/codex-image.mjs` and a `style-gen` subcommand on the Node dispatcher.
- New `skills/style-gen/SKILL.md` slash-command definition (same single-line invocation pattern as the other skills).
- `NOTICE` file documenting the fork relationship and modifications, per Apache-2.0 §4.

### Changed

- Plugin author / homepage / repository / marketplace owner updated to `gmlxo76`.
- README rewritten to document the fork relationship and the new `style-gen` command (including an `edit` vs `style-gen` decision table).
- Package and plugin manifests bumped to `0.2.0`.

### Attribution

This release is a derivative work of `KingGyuSuh/codex-image-in-cc@0.1.0`. The original `status`, `generate`, and `edit` commands and the dispatcher architecture are unchanged. See `NOTICE` and `README.md` for full attribution.

## [0.1.0] - 2026-04-26

### Added

- `/codex-image:generate` — generate one or more images via Codex CLI's built-in `imagegen` skill. The full slash-command argument string is passed verbatim to Codex; output paths, sizes, quality, count, transparency, etc. are expressed in natural language and interpreted by the `imagegen` skill.
- `/codex-image:edit` — edit an existing image. The first whitespace-separated token is the input path (quoted paths with spaces are supported, e.g. `"my photo.png" tint blue`); the rest is the edit prompt. Input is attached via `codex exec --image`.
- `/codex-image:status` — diagnostic for Node, Codex CLI version, login state, headless `--full-auto` support, and `imagegen` skill availability. Backed by `scripts/codex-image.mjs`.
- Apache-2.0 license.

### Notes

- Authentication flows through `codex login`. `OPENAI_API_KEY` is not required for the default built-in `image_gen` path.
- All three skills are 1-line `node "${CLAUDE_PLUGIN_ROOT}/scripts/codex-image.mjs" <subcommand> "$ARGUMENTS"` invocations. The Node wrapper does only arg splitting (for edit) and codex spawning with a ~6-line minimal instruction prefix. Image-generation intelligence lives entirely in Codex's bundled `imagegen` skill.
- SKILL.md bash is intentionally kept to a single-line script invocation. Putting parsing logic (`awk '...$1...'`, heredocs with substitutions) directly in SKILL.md is unsafe because the model does not always execute SKILL.md bash verbatim — see the `SKILL.md bash is not executed verbatim` entry in [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).
- See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for call flow and load-bearing edge cases.
