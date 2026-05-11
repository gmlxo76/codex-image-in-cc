# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
