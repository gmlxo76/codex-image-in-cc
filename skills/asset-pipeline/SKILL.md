---
description: Plan and batch-generate a project's asset set in a locked visual style, by orchestrating /codex-image:style-gen
argument-hint: '<reference-path> <project context description>'
allowed-tools: Bash(node:*)
---

# Asset Pipeline (Codex Image)

A higher-order orchestration of `/codex-image:style-gen`: given a locked style reference and a project context, plan the project's asset list, confirm with the user, then generate each asset in the same visual style.

## Arguments

- **First whitespace-separated token**: the **reference image path** (the locked style; quote if the path contains spaces).
- **Rest**: the **project context description**, free-form. Examples:
  - `"RPG mobile game with 5 enemies, 10 items, 4 backgrounds, UI buttons"`
  - `"SaaS landing page: hero, 4 section illustrations, OG image, favicon"`
  - `"casual puzzle app: app icon, splash, 6 tile sprites, particle textures"`

## Workflow

This skill is **orchestrated by the Claude Code agent** (you), not by a single bash one-liner — that lets the user review the plan before tokens are burned. Bash is only used for the underlying dispatcher primitives.

### 1. Parse and validate arguments

**Important — resolve attached-image placeholders first.** If `$ARGUMENTS` begins with a `[Image #N]` token (Claude Code's placeholder for an image the user attached via the chat UI, not a typed path), Claude Code provides the actual file path nearby in the message as image metadata of the form `[Image: source: <absolute-path>]`. In that case:

1. Replace the `[Image #N]` token with the resolved absolute path from the image metadata.
2. Treat everything after the original placeholder as the context string.
3. Pass the resolved path + context to `parse-args` as two arguments.

Otherwise (the user typed a path directly), pass `$ARGUMENTS` through as-is.

```bash
# Typed-path case:
node "${CLAUDE_PLUGIN_ROOT}/scripts/codex-image.mjs" parse-args "$ARGUMENTS"

# Attached-image case (after substituting the placeholder with the metadata path):
node "${CLAUDE_PLUGIN_ROOT}/scripts/codex-image.mjs" parse-args "<resolved-abs-path>" "<rest of arguments>"
```

On success, stdout contains two lines:
```
REF: <absolute path>
CONTEXT: <rest of arguments>
```

On failure (missing args, missing reference file), exit code is non-zero and stderr explains. **Stop and report the error to the user.**

### 2. Plan the asset list

Based on the CONTEXT string, propose a concrete asset list **yourself** (do not call Codex for this — Codex turns are for image generation only, planning is text-only reasoning).

Each asset is an object with:
- `name` — short kebab-case identifier (e.g. `"sword-of-flames"`)
- `category` — one of `character`, `enemy`, `item`, `ui`, `background`, `icon`, `illustration`, `splash`, `app-icon`, `other`
- `subject` — one-line description of WHAT the image depicts (do NOT include style — style comes from the reference at generation time)
- `output_path` — relative path under the project, e.g. `assets/items/sword-of-flames.png`
- `size` — pixel dims as `"WIDTHxHEIGHT"` (defaults: `512x512` for icons/items/UI, `1024x1024` for backgrounds/hero, `512x512` for sprites)
- `transparent` — boolean (default `true` for sprites/items/icons/UI; `false` for backgrounds/splash/hero)
- `count` — integer, default 1 (use >1 only when user explicitly asks for variations)

Use these context templates as starting points (adapt to the user's specific wording):

| Context type | Default categories to propose |
|---|---|
| Mobile game (RPG / casual / arcade) | app-icon, splash, characters, enemies, items, UI buttons, backgrounds, icons |
| Mobile app (SaaS / utility) | app-icon, splash, onboarding illustrations, empty/error states, tab bar icons |
| Web (landing / SaaS / portfolio) | hero, section illustrations, logo, favicon, OG image, placeholder photos |
| Game design (board / card / TTRPG) | card frames, faction icons, board tiles, dice/token art, cover art |

If the user context is vague or short, default to a **5–10 item starter set**. Do not silently expand to 30+ items.

### 3. Show plan and confirm

Present the plan to the user as a readable table (Name | Category | Subject | Output | Size | Transparent). Then use `AskUserQuestion` to offer:
- **Approve as-is** → continue to step 4
- **Refine** → ask user what to add/remove/change in free text, regenerate the plan, re-ask (up to 3 refinement rounds)
- **Cancel** → stop

### 4. Save manifest

After approval, save the manifest as JSON to `./codex-images/manifest-<UTC-timestamp>.json`, with this shape:

```json
{
  "version": 1,
  "created_at": "2026-05-11T12:00:00Z",
  "reference": "<absolute path>",
  "context": "<echo of user context>",
  "items": [ /* the approved items */ ],
  "results": []
}
```

The `results` array will be populated as items are generated (one entry per item with `name`, `output_path`, `status: "ok"|"failed"`, optional `error`).

### 5. Sample-first (if items > 10)

If the manifest has more than 10 items, **do not** run the full batch immediately:

1. Generate the **first 3 items** via style-gen (see step 6 for the call pattern).
2. Show the user the `SAVED:` paths and a one-line description of each.
3. Use `AskUserQuestion` to ask whether to continue with the rest:
   - **Continue all** → proceed with items 4..N
   - **Stop** → return; the user can refine the manifest and re-run
   - **Replace reference** → user gives a new reference path, regenerate items 1..3 with the new reference, re-ask

### 6. Execute (sequential, one per Bash call)

For each item to generate, run **one Bash call** at a time and wait for it to complete before the next:

```bash
node "${CLAUDE_PLUGIN_ROOT}/scripts/codex-image.mjs" style-gen "<REF>" "<subject>, save to <output_path> at <size>[, transparent background]"
```

Construction rules for the style-gen prompt:
- Always include `save to <output_path>` and `at <size>`.
- Append `, transparent background` if `item.transparent` is true.
- Append `, <count> variations` if `item.count > 1`.
- Do NOT describe the style — the reference image provides it.

After each call:
- If exit code 0, parse the `SAVED: <abs path>` line and append `{name, output_path, status: "ok", saved_path}` to the manifest's `results`.
- If exit code non-zero, append `{name, output_path, status: "failed", error: "<stderr summary>"}` and continue with the next item (do not abort the whole batch).

**Do not parallelize.** One style-gen call at a time. The Codex CLI session is shared and parallel calls can collide.

### 7. Final report

After the batch, summarize:
- Items planned / generated / failed (with names)
- Output directory(ies) used
- Manifest path
- Token note: `N` style-gen calls were made (≈ N Codex agent turns + N `image_gen` invocations)
- Next step suggestion: post-processing (e.g., WebP conversion, multi-resolution downsampling) if relevant

## Constraints

- Sequential only — never run multiple style-gen calls in parallel from one asset-pipeline invocation.
- Always do sample-first for batches > 10, no exceptions.
- Always save the manifest **before** running execution — if the session is interrupted, the user can resume from the manifest manually.
- Never modify the reference image. Never save the reference as an output artifact.

## Cost note

Each generated asset is one Codex agent turn + one `image_gen` invocation. A 30-item batch is ≈ 30 turns. The sample-first step exists specifically to avoid burning the full batch on a mismatched style — flag generously when the reference looks unstable for the requested context.
