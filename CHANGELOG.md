# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
