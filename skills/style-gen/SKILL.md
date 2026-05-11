---
description: Generate a new image whose visual style matches an attached reference image, via Codex CLI's built-in imagegen skill
argument-hint: '<reference-path> <natural-language generate request>'
allowed-tools: Bash(node:*)
---

# Style-Reference Generate (Codex Image)

The first whitespace-separated token in the arguments is the **reference image path** (used as a style/composition/mood reference only — never edited or returned). The rest is the generation prompt describing the new subject and any size/output-path/quality details in natural language. Quote the path if it contains spaces (e.g. `"my reference.png" draw a coin in this style ...`).

**Attached-image shortcut:** if the user attached an image via the chat UI instead of typing a path, `$ARGUMENTS` will start with a `[Image #N]` placeholder. The actual file path appears nearby in the message as image metadata: `[Image: source: <absolute-path>]`. Substitute the placeholder with that resolved path before invoking the dispatcher (the rest of `$ARGUMENTS` stays as the prompt).

Run:

```bash
node "${CLAUDE_PLUGIN_ROOT}/scripts/codex-image.mjs" style-gen "$ARGUMENTS"
```

(If you substituted an attached-image placeholder, replace `"$ARGUMENTS"` above with `"<resolved-abs-path> <rest of arguments>"` — same two-token shape.)

Output rules:
- Show the command stdout to the user verbatim — Codex prints one `SAVED: <absolute path>` line per saved image.
- If the exit code is non-zero, show stderr and stop. Common failures: missing reference image, missing generate prompt.
- Do not run any additional generations unless the user explicitly asks for another attempt.

Behavior notes:
- The reference is attached via `codex exec --image` and labeled as a *style reference* (not an edit target). The new image takes its **subject** from the user prompt and its **visual style** (palette, line weight, shading, composition, mood) from the reference.
- The reference image itself is never modified or saved. Only newly generated images are written to disk.
- Output path, size, count, transparency, and quality are all controlled via natural language inside the prompt (this command exposes no flags — same convention as `/codex-image:generate`).

## If the user is asking for a sprite sheet

Pass-through prompts that just say "make a sprite sheet of X" will reliably produce a grid where each cell has a different character scale, anchor, and effect overflow — useless for game engines that slice by `(cell × index)`. The constraints below MUST be added to the user's prompt before invoking the dispatcher. See [asset-pipeline SKILL.md](../asset-pipeline/SKILL.md) for the full spec; the must-have minimum is:

- "Grid layout: N columns × M rows, ALL CELLS EXACTLY C×C pixels."
- "Each sprite occupies the same ~70-80% of its cell, anchored at bottom-center (ground characters) or center (projectiles/UI/VFX). Bottom-of-feet at the same Y within every cell."
- "Animation effects (swing trails, energy bursts) must stay strictly within the cell — do not spill into adjacent cells."
- "Same character at the same chibi proportions, same line weight, same palette, same lighting across every frame."
- Standard frame counts: idle 4-8f, walk 4f or 8f, attack 4-6f, hurt 2-3f, death 4-8f.
- Direction convention: Vampire-Survivors-style usually 1-dir or 2-dir (engine mirrors horizontally); top-down RPG 4-dir (down/right/up, mirror right→left).

After generation, read the result image and verify: uniform cell size, consistent anchor, contained VFX, consistent style across frames. If any fail, recommend regenerating with stronger constraints — do not gloss the output as "OK" without naming what was verified.
