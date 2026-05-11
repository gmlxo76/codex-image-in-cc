# codex-image-in-cc

[![License](https://img.shields.io/github/license/gmlxo76/codex-image-in-cc.svg)](LICENSE)
[![Node](https://img.shields.io/badge/node-%3E%3D18.18-brightgreen.svg)](https://nodejs.org)

> 🇰🇷 한국어 자세한 사용 가이드: [GUIDE.md](GUIDE.md)

> **Fork notice.** This is a fork of [KingGyuSuh/codex-image-in-cc](https://github.com/KingGyuSuh/codex-image-in-cc) (Apache-2.0). The original three commands (`status`, `generate`, `edit`) are preserved; this fork adds **`/codex-image:style-gen`** for generating a new image whose visual style matches an attached reference, and **`/codex-image:asset-pipeline`** for orchestrating style-gen across a planned batch of assets. See [`NOTICE`](NOTICE) for attribution and the modification summary.

Claude Code plugin that exposes Codex CLI's built-in `imagegen` skill as `/codex-image:*` user-invoked plugin skills.

The plugin does not implement image generation itself. Each plugin skill dispatches to `codex exec --full-auto` and lets Codex's `imagegen` skill drive the built-in `image_gen` tool, save the final artifact, and print a `SAVED: <path>` line for each output.

## Requirements

- Claude Code with plugin support.
- `@openai/codex` CLI v0.124.0 or later.
- An active `codex login` session.
- Node.js 18.18 or later.

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
```

The full slash-command argument string is passed verbatim to Codex's `imagegen` skill. Express output paths, sizes, quality, count, transparency, etc. as natural language inside the prompt — `imagegen` interprets them. Defaults: when no path is specified, `generate` outputs land under `./codex-images/<UTC-timestamp>-<n>.png`, `edit` under `./codex-images/<UTC-timestamp>-edit-<n>.png`, and `style-gen` under `./codex-images/<UTC-timestamp>-stylegen-<n>.png`.

For `/codex-image:edit` and `/codex-image:style-gen`, the first whitespace-separated token is the input/reference image path. Quote it if the path contains spaces (e.g. `/codex-image:style-gen "my reference.png" draw a coin in this style ...`).

### `edit` vs `style-gen`

Both attach an image via `codex exec --image`, but they instruct Codex differently:

| | `edit` | `style-gen` |
|---|---|---|
| Role of attached image | edit target | style reference only |
| What gets saved | modified version of the input | a brand-new image |
| Preserves input layout/content | yes (unless asked otherwise) | no — only visual style is transferred |
| Reference itself modified/output | (in-place style edit) | never |

The `style-gen` instruction prefix explicitly labels the attached image as a "supporting style input" per the [Codex `imagegen` skill's role classification](https://github.com/openai/codex/blob/main/codex-rs/skills/src/assets/samples/imagegen/SKILL.md), so Codex treats the request as `generate` rather than `edit`.

### `style-gen` vs `asset-pipeline`

| | `style-gen` | `asset-pipeline` |
|---|---|---|
| What it produces | One image set (1+ images) per invocation | A planned batch of N assets — each is its own `style-gen` call under the hood |
| Who plans the resource list | You, in your prompt | The Claude Code agent, from your project context — then you approve before execution |
| User confirmation | None (direct invocation) | Yes — plan is shown and confirmed; sample-first for batches > 10 |
| Manifest | None | `./codex-images/manifest-<UTC>.json` saved for reproducibility |
| Cost | 1 Codex agent turn (× number of saved images) | N Codex agent turns (one per asset) — plus a sample-first gate to avoid wasting them on a mismatched style |

Use `style-gen` for one-off matched-style images. Use `asset-pipeline` when you've locked the style and want a project's full asset set in one go.

## Development

```bash
npm test
npm run validate:plugin
npm run status
claude --plugin-dir .
```

After editing plugin skills during a `claude --plugin-dir .` session, run `/reload-plugins`.

Image generation consumes a Codex agent turn plus the built-in image generation tool usage.

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for scope, dev setup, and PR conventions, and [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the call flow and load-bearing edge cases. Security issues — see [`SECURITY.md`](SECURITY.md).

## Attribution

Forked from [KingGyuSuh/codex-image-in-cc](https://github.com/KingGyuSuh/codex-image-in-cc). All credit for the original `status`/`generate`/`edit` design and the dispatcher architecture goes to KingGyuSuh. See [`NOTICE`](NOTICE) for the full attribution and modification summary as required by Apache-2.0 §4.

## License

[Apache-2.0](LICENSE).
