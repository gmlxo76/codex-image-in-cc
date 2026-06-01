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

## Transparency: luminance vs chroma key (auto-detected)

When the user asks for a transparent output, the dispatcher auto-selects one of two pipelines based on keywords in the prompt:

| Method | When | Why |
|---|---|---|
| **Luminance alpha** | Prompt mentions glow / luminous / neon / VFX / halo / particles / sparkle / fire / lightning / radiance / aura / 글로우 / 발광 / 빛나는 / 네온 / 후광 | Renders on solid black, recovers alpha from pixel brightness (`alpha = max(R, G, B)`). No chroma key color exists in the image, so semi-transparent glow pixels can't pick up colored fringes. Natural brightness falloff becomes natural alpha falloff. |
| **Chroma key** (default for transparent) | Prompt asks for transparency but contains no luminous keywords (icons, items, characters, props) | Renders on magenta (#FF00FF), subtracts to alpha. Robust for flat-edged subjects with no large soft-edged glow regions. |

Users can override the auto-detection with an explicit flag inside the prompt:

- `--transparency=luminance` — force luminance method
- `--transparency=chroma` — force chroma-key method
- `--transparency=auto` — explicit auto (same as default)
- `--transparency=none` — disable the transparency pipeline entirely

The flag is stripped from the prompt before the request reaches Codex. The dispatcher writes the chosen method to stderr as `[codex-image] transparency method: <method>` so the caller can verify.

**Why this matters:** generating luminous content (glow rings, neon icons, magical particles) against a magenta chroma key has been observed to leave purple/pink fringes on the soft edges of glow, because semi-transparent gold pixels visually blend with magenta during generation. The luminance method side-steps the problem entirely by never introducing a chroma key color in the first place.

**Caveat — dark content:** the luminance method makes ALL dark pixels transparent (since dark = low brightness = low alpha). Intentionally dark subjects (black armor, dark backgrounds, shadows) will go semi-transparent or disappear. Use chroma key for those.

## If the user is asking for a multi-state atlas (default/pressed/hover/etc.)

Pass-through prompts like "two button states side by side" produce atlases where
cells DRIFT — the AI draws each cell with slightly different center, scale, and
stroke weight, so a runtime frame swap visibly jumps. Vague prompts will fail
reliably; you must build the prompt with explicit per-cell pixel coordinates,
an enforced base subject, and an enumerated list of allowed per-cell deltas.

The full prompt skeleton + filled examples (default/pressed button, mic with
double-ring pressed state) are documented in
[`skills/asset-pipeline/SKILL.md` → "Multi-State Atlas Methodology — PIXEL-ALIGNED CELLS"](../asset-pipeline/SKILL.md).
Copy the skeleton and fill the placeholders for the user's specific request
before invoking the dispatcher. Do NOT shortcut with vague phrasing.

After generating ANY multi-cell atlas, ALWAYS run the mandatory alignment gate:
`/codex-image:check-atlas <atlas.png> --grid CxR`. It verifies every cell shares
the same content size + center anchor and, if they drift, AUTO-realigns with size
normalization (writing `<name>_aligned.png`) and re-verifies. Use the realigned
file as the asset. This is non-negotiable — a few px of drift is invisible in the
static sheet but jumps/jitters at runtime when the engine swaps states. Prefer also
fixing the prompt and regenerating, but `check-atlas` is the enforced safety net.

(`/codex-image:realign-atlas` remains available as the lower-level realign primitive
that `check-atlas` calls under the hood.)

## If the user is asking for a sprite sheet

Pass-through prompts that just say "make a sprite sheet of X" will reliably produce a grid where each cell has a different character scale, anchor, and effect overflow — useless for game engines that slice by `(cell × index)`. The constraints below MUST be added to the user's prompt before invoking the dispatcher. See [asset-pipeline SKILL.md](../asset-pipeline/SKILL.md) for the full spec; the must-have minimum is:

- "Grid layout: N columns × M rows, ALL CELLS EXACTLY C×C pixels."
- "Each sprite occupies the same ~70-80% of its cell, anchored at bottom-center (ground characters) or center (projectiles/UI/VFX). Bottom-of-feet at the same Y within every cell."
- "Animation effects (swing trails, energy bursts) must stay strictly within the cell — do not spill into adjacent cells."
- "Same character at the same chibi proportions, same line weight, same palette, same lighting across every frame."
- Standard frame counts: idle 4-8f, walk 4f or 8f, attack 4-6f, hurt 2-3f, death 4-8f.
- Direction convention: Vampire-Survivors-style usually 1-dir or 2-dir (engine mirrors horizontally); top-down RPG 4-dir (down/right/up, mirror right→left).

After generation, read the result image and verify: uniform cell size, consistent anchor, contained VFX, consistent style across frames. If any fail, recommend regenerating with stronger constraints — do not gloss the output as "OK" without naming what was verified.
