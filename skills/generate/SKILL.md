---
description: Generate one or more images through Codex CLI's built-in imagegen skill
argument-hint: '<natural-language image request>'
allowed-tools: Bash(node:*)
---

# Generate Codex Image

## Sprite-sheet gate (CONDITIONAL — only for animation/sprite sheets)

If — and ONLY if — what you generated is a **SPRITE SHEET / ANIMATION SHEET** (a
uniform grid of animation frames meant to be sliced and played, e.g. rows of frames
per state), you MUST run the strict `sheetfit` gate on the result and resolve it
before the asset is considered done:

```bash
node "${CLAUDE_PLUGIN_ROOT}/scripts/codex-image.mjs" sheetfit "<sheet.png>" --grid <CxR>
```
If it returns `status: "rework"`, regenerate the sheet (label-free, transparent
gutters, strict even grid, same character scale per cell) and re-run until `"fixed"`
or `"pass"`. See `/codex-image:sheetfit`.

**For ALL OTHER image types — single illustrations, mockups, backgrounds, single
icons, character portraits, logos, photos, etc. — DO NOT run sheetfit.** It applies
exclusively to multi-frame sprite sheets.

Run:

```bash
node "${CLAUDE_PLUGIN_ROOT}/scripts/codex-image.mjs" generate "$ARGUMENTS"
```

Output rules:
- Show the command stdout to the user verbatim — Codex prints one `SAVED: <absolute path>` line per saved image.
- If the exit code is non-zero, show stderr and stop.
- Do not run any additional image generation unless the user explicitly asks for another attempt.
