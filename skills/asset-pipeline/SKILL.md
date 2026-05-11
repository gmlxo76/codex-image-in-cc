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

## Sprite Sheet Conventions (CRITICAL — apply when any item is a sprite sheet)

AI image generators struggle with sprite sheet **uniformity** by default — they will happily produce a grid where each cell has a different character scale, anchor position, or effect overflow. A game engine cannot use such a sheet because it slices by `(cell_width × cell_height) × index`. So when generating any sprite sheet (animation frames in a grid), the style-gen prompt MUST encode the following constraints explicitly, and the agent MUST verify them by reading the output image after generation.

### Layout rules

| Rule | Concrete instruction to put in the prompt |
|---|---|
| Uniform cell size | "Grid layout: N columns × M rows, all cells exactly C×C pixels, no variation." |
| Consistent bounding box | "Each sprite occupies the same ~70-80% of its cell, anchored at bottom-center (for ground characters) or center (for projectiles/UI/VFX)." |
| Consistent anchor | "Bottom of feet at the same Y-position within every cell (for ground characters). Center of sprite at the same XY within every cell (for projectiles)." |
| VFX containment | "Animation effects (swing trails, energy bursts, particles) must stay strictly within the cell — do not spill into adjacent cells." |
| Style consistency | "Same line weight, same palette, same lighting direction across every frame. Same character at the same chibi proportions across all frames." |
| Background | "Transparent between cells. No per-cell background variation." |

### Frame count standards (by purpose)

| Purpose | Frame count | Notes |
|---|---|---|
| Idle | 4 (low-res) or 6-8 (smooth) | Often a slight breathing/bob loop |
| Walk cycle | 4 (basic) or 8 (smooth) | 4 keyframes capture leg/arm motion; 8 smooths it |
| Run cycle | 8 | Pixel art rarely needs more than 8 |
| Attack | 4-6 | Wind-up + impact + recovery |
| Hurt | 2-3 | Stagger pose |
| Death | 4-8 | Fall/collapse → dissolve |

### Direction conventions (top-down RPG / Vampire Survivors-style)

| # directions | What to include | Notes |
|---|---|---|
| 1-dir | Front-facing only | OK for simple games or projectile-only assets |
| 2-dir | Left + right | Vampire Survivors usually flips one side in-engine, so often just one direction is generated and mirrored |
| 4-dir | Down, left, right, up | Standard for Secret of Mana / A Link to the Past style. Most common for tile-based RPGs |
| 8-dir | + diagonals (down-left, down-right, up-left, up-right) | Symmetrical games only need 5 of the 8 — left/right diagonals can mirror |

**For Vampire Survivors-like games specifically: 1-dir or 2-dir per character/enemy is the norm — the game flips horizontally in code, no need to generate left+right separately.**

### Layout template the prompt should specify

For a 4-direction character sprite sheet, recommended layout:

```
Row 1: 4-8 idle frames (down-facing)
Row 2: 8 walk frames (down)
Row 3: 8 walk frames (side, right-facing — left is mirrored in engine)
Row 4: 8 walk frames (up)
Row 5: 4-6 attack frames (down)
Row 6: 4-6 attack frames (side)
Row 7: 4-6 attack frames (up)
Row 8: 2-3 hurt + 4-8 death frames
```

For Vampire Survivors-style (1-dir), minimal layout:

```
Row 1: 4 idle frames
Row 2: 8 walk frames (one direction, flipped in engine)
Row 3: 4-6 attack frames
Row 4: 2 hurt + 4 death frames
```

### Verification step (MANDATORY after each sprite sheet generation)

After style-gen returns SAVED, read the generated image and verify:
1. All cells have the same dimensions (visual inspection — divide canvas by grid count).
2. Character/object scale is the same in every cell.
3. Anchor point (bottom of feet / center of object) lands at the same coordinate within every cell.
4. VFX/trails do not exceed cell boundaries.
5. Style/palette/line-weight is consistent across frames.

If any of these fail, report the specific failure to the user and recommend either (a) regenerate with stronger constraints in the prompt, or (b) accept as a "reference sheet" and re-do for game use.

## UI Icon Sheet Conventions (apply for ui / icon category items)

UI icon sheets have the same uniform-cell problem as sprite sheets but with stronger expectations on optical balance, stroke weight, and style consistency. Without explicit constraints the AI will produce a beautiful but unusable grid where each icon has different padding, different line weight, and different visual density.

### Rules to encode in the style-gen prompt

| Rule | Concrete instruction |
|---|---|
| Uniform cell + grid | "Grid layout: N columns × M rows, ALL CELLS EXACTLY C×C pixels (24/32/48/64 base sizes). Each icon centered within its cell." |
| Live area padding | "Each icon occupies ~75-85% of its cell (vertical/horizontal padding = stroke-weight × 2). Never bleed to the edge." |
| Stroke weight | "Identical stroke weight across every icon in the sheet." |
| Style consistency | "Identical visual style across all icons: same level of detail, same line treatment (filled/outlined/duotone), same palette, same lighting direction." |
| Transparent background | "Transparent background throughout. No per-icon colored backgrounds." |
| Optical alignment | "Optically-aligned, not just bounding-box-aligned — a triangle/circle/star icon should LOOK the same visual weight as a square one even though its bounding box differs." |
| Multi-state alignment | "For button states (normal/hover/pressed/disabled), the icon stays in the exact same position; only color/effect changes." |

### Standard icon sheet sizes

| Use case | Cell size | Notes |
|---|---|---|
| Mobile tab bar | 24×24 or 32×32 | Small, single-color or duotone |
| HUD icons (health, mana, exp) | 32×32 or 48×48 | Often colorful, must read at glance |
| Inventory items | 48×48 or 64×64 | Rich, detail allowed |
| Weapon/skill icons | 64×64 or 96×96 | Detail + frame allowed |
| Achievement/badge | 96×96 or 128×128 | Most detail |

### Grouping rule

Icons in the same sheet should share a coherent set — never mix unrelated icons in one sheet. Examples of good groupings:
- All weapon icons (dagger, sword, axe, bow, staff, ...) → one weapon-icon sheet
- All blessing/skill icons → one skill-icon sheet
- All HUD/system icons (HP, MP, clock, coin, gem) → one hud-icon sheet
- Multi-state of one element (button normal/hover/pressed/disabled) → either one sheet per element, or grouped by element type

### Verification step (MANDATORY after each icon sheet)

After style-gen returns SAVED, read the result and verify:
1. All cells identical size; icons centered in each.
2. Same stroke weight across icons (look at line thickness — should be visually identical).
3. Same level of detail/style; no icon "stands out" as more illustrative or more abstract.
4. Same padding on all sides — icons don't touch cell edges.
5. Background transparent throughout.

If any fail, report and recommend regenerate.

## VFX Sheet Conventions (apply for vfx / effect category items)

VFX sheets are typically animation flipbooks: N frames of an effect played in sequence. Game engines play them via a sprite animator (UV-stepping at frame_index % frame_count). The same uniform-cell rules from sprite sheets apply, plus extra rules about alpha lifecycle and looping.

### Rules to encode in the style-gen prompt

| Rule | Concrete instruction |
|---|---|
| Uniform cell + grid | "Grid layout: N columns × M rows, ALL CELLS EXACTLY C×C pixels (typically 128/192/256). Each frame centered within its cell." |
| Alpha containment | "The effect never crosses the cell boundary. Particles, glow, debris all stay strictly inside their cell." |
| Center pivot | "Each frame anchored at the cell's center (NOT bottom). The effect expands/contracts outward from center." |
| Alpha lifecycle | "Alpha lifecycle across frames: starts opaque/intense, fades to transparent at the last frame. Last frame should be ~95% transparent — when the animation loops, you don't see a hard pop." |
| Looping continuity | "If marked as a looping effect (aura, channel), frame 1 and frame N visually connect — no jarring jump back to frame 1." |
| Style consistency | "Same color palette and lighting style across every frame. Same particle density/scale baseline." |

### Standard frame counts by effect type

| Effect type | Frames | Notes |
|---|---|---|
| Hit/impact burst | 4-6 | Quick flash, expand and fade |
| Explosion | 8-12 | Build → peak → debris → fade |
| Projectile (single frame) | 1-4 | Often just one frame, rotated in engine |
| Beam/laser | 4-8 (looping) | First/last frame must match |
| Magic circle / sigil | 8-16 (looping) | Slow rotation/pulse |
| Aura / glow (looping) | 8-12 | Subtle breathing, must loop seamlessly |
| Level-up / pickup | 6-8 (one-shot) | Sparkle/beam, fade out at end |
| Death dissolve / poof | 4-8 (one-shot) | Solid → particles → fade |

### Grouping rule

Group VFX by use case, not by visual similarity:
- Combat VFX sheet: hit-impacts + blood-splashes + weapon-trails
- Magic VFX sheet: holy-nova + shadow-strike + soul-orbit + level-up-beam
- Pickup VFX sheet: gem-sparkle + coin-shine + chest-burst
- Environment VFX: torch-flame + magic-fog + drip + dust

### Verification step (MANDATORY after each VFX sheet)

After style-gen returns SAVED, read the result and verify:
1. All cells identical size; effect centered in each.
2. Effect stays inside cell boundaries (no spilling).
3. Alpha clearly progresses across frames (last frame much more transparent than first for one-shot; first and last match for looping).
4. Same color palette across frames; no random color shifts.
5. For looping effects: frame 1 visually connects to frame N (no hard jump).

If any fail, report and recommend regenerate.

## Number / Bitmap Font Sheet Conventions (apply for number-font / font-sheet items)

Damage numbers, UI scores, timers, and similar number displays are typically rendered via bitmap fonts — a sheet of digit glyphs (and optionally punctuation) that the engine composites at runtime. Without explicit constraints the AI will produce digits at inconsistent heights, varying stroke weights, and different baselines, which means the runtime composition will look like a ransom note.

### Required glyph set

| Tier | Glyphs | Notes |
|---|---|---|
| Minimum | `0 1 2 3 4 5 6 7 8 9` | 10 digits |
| Standard | + `. - +` | Decimal point (for fractions), minus (for negatives), plus (for buff numbers) |
| Extended | + `, / × !` | Comma (large numbers like 12,345), slash (HP fractions like 50/100), × (multiplier like ×3), ! (crit emphasis) |
| Special variants | normal / crit / heal / shield / miss | Each as its own row or separate sheet; typically white-yellow / red-orange / green / cyan / gray |

### Rules to encode in the style-gen prompt

| Rule | Concrete instruction |
|---|---|
| Monospace | "All digits and punctuation glyphs occupy the same cell width (monospace). Easier for runtime layout than variable-width." |
| Uniform cell + baseline | "Grid layout: single row of N cells (e.g. 13 cells for `0-9 . - +`), ALL CELLS EXACTLY C×C pixels. All digit glyphs sit on the same baseline at the same Y within their cell." |
| Consistent height | "All digit glyphs (0-9) have the exact same height. Punctuation (`. -`) sits at the appropriate baseline position relative to digits (period at baseline, hyphen at mid-height)." |
| Identical stroke weight | "Same stroke thickness across every glyph." |
| Outline / shadow for readability | "Each glyph has an identical outline (1-2 px) and optional drop shadow, so the number reads on busy game backgrounds. Outline color contrasts with fill." |
| Style consistency | "Same fill color, same outline color, same font weight, same letterforms across every glyph in the sheet (e.g. all chunky bold, or all thin serif — not mixed)." |
| Transparent background | "Transparent background throughout. No per-glyph colored backgrounds." |
| Per-variant rows | "If the sheet covers multiple damage types: one row per variant (row 1 = normal white, row 2 = crit red, row 3 = heal green, etc.). Each row uses the same glyph set." |

### Standard cell sizes

| Use case | Cell size (px) | Notes |
|---|---|---|
| Small HUD scores / coins | 16×24 or 24×32 | Mobile/pixel-art games |
| Damage numbers (in-game floating) | 32×48 or 48×64 | Readable at gameplay distance |
| Boss / big crit numbers | 64×96 or 96×128 | Dramatic emphasis |
| UI panel scores (level select, results) | 48×64 or 64×96 | Static UI use |

### Layout example for a multi-variant damage sheet

```
Row 1 (normal damage, white-yellow): 0 1 2 3 4 5 6 7 8 9 . - +
Row 2 (crit damage, red-orange):     0 1 2 3 4 5 6 7 8 9 . - +
Row 3 (heal, green):                 0 1 2 3 4 5 6 7 8 9 . - +
Row 4 (shield, cyan):                0 1 2 3 4 5 6 7 8 9 . - +
Row 5 (miss/dodge, gray):            0 1 2 3 4 5 6 7 8 9 . - +
```

Each row repeats the SAME glyph set, only the color/effect changes. The position of glyph "5" in row 1 and row 2 must be identical — only the color differs.

### Verification step (MANDATORY after each number-font sheet)

After style-gen returns SAVED, read the result and verify:
1. All digit cells identical size; glyphs vertically aligned (baseline match).
2. All digits same height — `8` is not taller than `1`.
3. Identical stroke weight across glyphs — no digit looks bolder or thinner than another.
4. Outline thickness identical across glyphs.
5. For multi-variant sheets: each row has the SAME glyph set in the SAME order; only color/effect differs between rows.
6. Punctuation (`.` `-` `+`) sits at appropriate baseline positions, not centered like a digit.

If any fail, report and recommend regenerate — bitmap fonts that misalign by even 2-3 pixels look obviously broken in-game.

## Constraints

- Sequential only — never run multiple style-gen calls in parallel from one asset-pipeline invocation.
- Always do sample-first for batches > 10, no exceptions.
- Always save the manifest **before** running execution — if the session is interrupted, the user can resume from the manifest manually.
- Never modify the reference image. Never save the reference as an output artifact.
- **For sprite sheet items: always include the Sprite Sheet Conventions above in the style-gen prompt, and run the verification step after generation.**

## Cost note

Each generated asset is one Codex agent turn + one `image_gen` invocation. A 30-item batch is ≈ 30 turns. The sample-first step exists specifically to avoid burning the full batch on a mismatched style — flag generously when the reference looks unstable for the requested context.
