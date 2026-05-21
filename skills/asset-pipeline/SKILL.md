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

#### CRITICAL: Screen-flow + element-size planning FIRST, asset list SECOND

Do not jump straight to "list of PNGs to generate." Real apps/games need a SCREEN-LEVEL design pass first, because the same visual element (a button, an orb, an icon) has a SPECIFIC PIXEL SIZE per screen, and that pixel size determines the asset's source resolution, atlas cell size, and whether it can be shared with another screen.

**Step 0 — Confirm the target viewport BEFORE doing anything else.**

Before planning screens or assets, the agent MUST ask the user which viewport the project targets, because every downstream size calculation depends on it. Use `AskUserQuestion` with the following options (or a subset that fits the context — drop irrelevant ones for the obvious cases, e.g. don't offer "Desktop" when the context string says "iOS app"):

> Question: "What viewport(s) does this project target? Asset sizes (cells,
> backdrops, icons) depend on this — wrong viewport = wrong asset sizes."
>
> Options (header "Viewport"):
> - Mobile portrait (430×932, iPhone 14 Pro baseline) — RECOMMENDED for most mobile games/apps
> - Mobile portrait small (390×844 / 360×800 Android baseline)
> - Mobile landscape (932×430)
> - Tablet portrait (820×1180)
> - Desktop web (1440×900)
> - Mobile + Desktop responsive (need both viewports planned)

Wait for the answer. The answer becomes the **target viewport** used in Step B element sizing. For responsive web, plan TWO sets of element sizes (mobile and desktop) and pick the largest pixel size each shared asset needs across both.

Only after the user answers do you proceed:

**Step A — Enumerate every screen in the flow.**

Use the inference rules below (game / mobile app / web / SaaS / etc.) to list EVERY screen the project needs, not just the one in the reference. Include overlay screens (level-up, pause, confirmation dialogs), error/empty states, transition screens (loading), and meta screens (settings, bestiary, achievements) implied by the product type.

**Step B — Size every element on every screen.**

For each screen, lay out the actual UI elements with PIXEL DIMENSIONS at the target viewport. State the viewport up front:
- Mobile portrait game/app: 430 × 932 (iPhone-ish baseline; use 360×800 for Android baseline if specified)
- Mobile landscape: 932 × 430
- Tablet portrait: 820 × 1180
- Web desktop: 1440 × 900 (or 1280 × 720)
- Web mobile responsive: still plan two viewports — mobile 390×844 and desktop 1440×900

Write the layout as a table per screen:

| Y range | Element | Size | Notes |
|---|---|---|---|
| 0–50 | back button (top-left) | 36×36 | iconRound variant |
| 60–110 | section header label | 240×40 | text-label PNG, no frame |
| 115–375 | map landscape backdrop | 430×260 | full-bleed, 1.65:1 ratio |
| ... | ... | ... | ... |

Do this for EVERY screen. Each element is a pixel rectangle on the viewport. Position (x, y, w, h) + display purpose. This step alone takes more thinking than the asset list — and that's the point. Without it, the asset list is guessing.

**Step C — Consolidate: identify shared elements across screens.**

This is the SINGLE MOST IMPORTANT planning step. Most assets in a real product are SHARED across many screens (back arrow on every sub-screen, primary button on every CTA, modal frame on every dialog, HP icon in HUD and results screen, etc.). If you draft assets per-screen without consolidating, you end up generating the same button 7 times — wasting tokens and creating visual drift.

Procedure:
1. Take every element from every screen's Step B table.
2. Group identical/near-identical elements by visual purpose. Examples:
   - All `back-arrow` instances across screens → ONE shared icon
   - All `primary-button` instances → ONE shared button atlas (with all states)
   - All `header-banner` instances → ONE shared banner asset
   - All `modal-frame` instances → ONE shared frame
   - All `HP-icon` / `coin-icon` / `gem-icon` instances → ONE shared HUD-icons atlas
   - All `confirm-dialog` instances → ONE shared dialog frame
3. For each group, the asset's PIXEL SIZE is the **largest** display size required across consumers (so it stays sharp at all sizes — never upscale, always downscale).
4. Tag each consolidated asset with `used_by: [screen1, screen2, ...]` in the manifest so the user can see and audit the sharing.

**Examples of consolidation:**

| Per-screen draft (wrong) | Consolidated (right) | Used by |
|---|---|---|
| `back-arrow-charselect.png`, `back-arrow-options.png`, `back-arrow-bestiary.png` | ONE `nav-icons` atlas with `back-arrow` cell | charselect, options, bestiary, upgrades, settings |
| `button-start-hunt.png`, `button-resume.png`, `button-quit.png`, `button-restart.png` | ONE `buttons` atlas (primary / secondary / danger × states), labels rendered separately | every screen with CTAs |
| `pause-modal-frame.png`, `confirm-quit-frame.png`, `gameover-stats-frame.png` | ONE `modal-frame` 9-slice asset | pause, confirm, gameover, victory results |
| `hp-icon-hud.png` (32×32), `hp-icon-results.png` (64×64) | ONE `hud-icons` atlas at 64×64 (downscale for HUD) | HUD, results, bestiary detail |

**Step D — Present the consolidated resource list to the user BEFORE drafting the final manifest.**

After consolidation, show the user the proposed shared-asset list, NOT just the raw element list. Use a table like:

| Asset | Kind | Pixel size | Used by | Inferred? |
|---|---|---|---|---|
| `nav-icons` | atlas (4×1 of 64×64) | 64×64/cell | charselect / options / bestiary / upgrades | no |
| `buttons` | atlas (4×5 of 280×280) | 280×280/cell | every screen with CTAs | no |
| `boss-portraits` | atlas (5×1 of 256×256) | 256×256/cell | boss-intro screen | yes |
| `gameover-skull` | single | 512×512 | game-over screen | yes |
| ... | ... | ... | ... | ... |

Use `AskUserQuestion` to confirm. Offer:
- **Approve as listed** → continue to manifest draft
- **Add / remove / merge** → take user's free-text edits, regenerate the table, re-ask (up to 3 rounds)
- **Cancel** → stop

This is the gate. Do NOT proceed to generation without the user reviewing the consolidated list. The user is the only person who knows whether a given grouping is acceptable for their project.

**Step E — Draft the manifest from the approved consolidated list.**

Each manifest entry's `size` field must trace back to specific pixel measurements from Step B (e.g. "cellW=64 because the stat-icons show at 64×64 in the character card stat row at viewport 430×932"). Each entry should carry forward the `used_by` array so future maintainers can see why the asset was sized the way it was.

Only after Step E do you actually invoke style-gen.

**Worked example (mobile game):**

```
Step A — Screens: Title, Character+Stage Select, Loading, In-Game HUD,
Level-Up Overlay, Pause, Game Over, Victory, Bestiary, Upgrades, Options.

Step B — Element sizing (Character+Stage Select @ 430×932):
| Y     | Element            | Size    |
| 0-50  | BACK arrow         | 36×36   |
| 60-110| header label       | 240×40  |
| 115-375| map landscape     | 430×260 |
| (map) | diamond markers ×5 | 50×50 each |
| ...   | ...                | ...     |

Step C — Derived assets:
- map-markers atlas: 6 cells (5 location colours + 1 locked), 64×64 each
  (oversize source for sharp display at 50×50)
- character cards atlas: 4 hunters full-body, 256×640 cells
  (source for display at 88×220 with safe headroom)
- ...
```

This is the rule: SCREEN PLAN → ELEMENT SIZES → ASSET LIST. Skipping the first two steps produces assets that don't fit the screens they're meant for.

#### CRITICAL: Infer beyond the reference (universal rule — every domain, not just games)

Do NOT limit the plan to what is literally visible in the reference image. Whatever the reference depicts — game, SaaS dashboard, e-commerce page, mobile app, restaurant menu, banking flow — a real shipping product needs many assets that aren't in any single screenshot. **You must explicitly include the contextually-obvious assets that the reference IMPLIES, even when invisible.**

For every reference, ask this question for every visible element:
> "If a user actually used this product, what other screens / states / assets must exist around this one? What does this screen logically connect to? What error/empty/loading states does it have? What lifecycle events trigger which screens?"

Whatever you'd answer "obviously also exists" — add it to the manifest.

Examples across domains:

| Reference depicts… | You must also plan for (even if not shown) |
|---|---|
| Any game (any genre) | game-over screen, pause menu, options menu, loading screen, splash/studio logo, credits screen |
| RPG / action / survival | bestiary, upgrade tree, status-effect icons (buff/debuff), achievement badges, tooltip frames, tutorial overlays |
| Any UI button that names a destination (BESTIARY, UPGRADES, OPTIONS, etc.) | that destination screen itself |
| Any combat or interaction | damage-number font, hit/death VFX, full skill/weapon icon roster (not just visible slots), warning UI |
| Mobile app (any kind) | onboarding flow, empty-state and error-state screens, permission prompts, settings, profile, notifications |
| Web product (any kind) | 404 page, loading skeletons, modal/dialog frames, toast notifications, footer, search results, empty states |
| E-commerce | cart, checkout, account, order confirmation, shipping/tracking, wishlist, search filters, product detail variations |
| SaaS dashboard | login/signup, password reset, billing/plan, profile, team members, notifications, admin panel, audit log |
| Form / data entry | success state, validation error states (per field), loading state, "are you sure" confirmation |
| Banking / fintech | transaction history, biometric/2FA, security warnings, fraud alerts, account switch |
| Social / messaging | notification badges, presence indicators, typing indicator, read receipts, empty inbox state |
| Marketing landing | header navigation, footer, contact/CTA, pricing, FAQ, social proof, 404 |

**Rule of thumb:** any time a real user would expect to reach a screen/asset that isn't in the reference, plan it. If a button names it ("BESTIARY"), the destination exists. If a flow implies it ("pause" exists because the game is real-time), the pause menu exists. If an error can occur ("login form"), the error state exists.

Note in the manifest's `inferred: true` field which items came from logical inference vs. direct reference observation, so the user can trim if they want minimal scope.

#### CRITICAL: Don't under-spec UI

UI is almost always the most under-counted category. A single in-game screen typically implies 10-15 distinct UI sheets (logo/typography, button states, frames, HUD orbs, HUD panels, weapon-slot frame, weapon icons, blessing/skill icons, card frames, stat indicators, damage number font, section icons, map nodes, etc.). When the reference shows ANY UI, your plan should reflect that granularity — don't group everything into a single "ui-misc" sheet.

#### CRITICAL: Layer separation — content vs container

UI elements must be authored as SEPARATED LAYERS that the game engine composites at runtime, not as flattened images. Anything that CHANGES at runtime — text, fill levels, item-in-slot, icon-in-frame, badge-on-state, count digits — must be on its own asset, separate from the static container. Without this, the product is impossible to localize, animate, or make data-driven.

| Component | WRONG (baked into single image) | RIGHT (separated layers) |
|---|---|---|
| Button | Frame + "START HUNT" text in one image | (a) button frame (multi-state) + (b) text rendered by engine text system at runtime — enables i18n/localization |
| Progress bar (HP/EXP/mana) | Frame with fill drawn at fixed % | (a) empty track background + (b) fillable bar (tintable strip or pre-colored fill texture) — enables animated fill |
| Liquid orb | Liquid baked at certain % | (a) orb frame with transparent center + (b) liquid fill texture (clipped/masked at runtime) |
| Inventory / skill / weapon slot | Item icon baked into slot frame | (a) slot frame (multi-state: normal/equipped/levelup/locked) + (b) each item icon as separate sprite — enables runtime equipping |
| HUD counter (kills, gold, gems) | Number digits + icon + frame all in one | (a) panel frame + (b) icon (separate) + (c) number rendered by engine using bitmap-font sheet |
| Card with portrait | Portrait painted inside frame | (a) card frame (multi-state) + (b) portrait + (c) name-plate text rendered at runtime |
| Locked / disabled variant | Padlock painted onto base art | (a) base art + (b) padlock + dim-overlay applied at runtime as a tint or sprite stack |
| Node / map marker with state | Node art with state-specific decoration baked | (a) node base + (b) state overlay (padlock for locked, glow for active) on separate layer |

#### CRITICAL: 9-slice scaling for resizable frames

Frames, buttons, and panels that the engine resizes (button widths varying with label length; panel sizes varying with content) MUST be designed for 9-slice scaling:

- **Four corners stay fixed** in size — make them distinct and decorative.
- **Top/bottom edges** stretch or tile horizontally — design as repeatable horizontal patterns.
- **Left/right edges** stretch or tile vertically — design as repeatable vertical patterns.
- **Center area** stretches both ways — design as solid or tileable, never with a baked-in motif that would distort.

When the prompt asks for a frame/button/panel sprite, the prompt MUST say: "designed for 9-slice scaling — decorative corners, simple repeatable edges, solid or tileable center, no central motif that would distort when stretched."

#### Practical implications for the manifest

When planning any UI sheet for the manifest:
- For every visible composite (button-with-label, slot-with-item, orb-with-fill, counter-with-number), list TWO+ items: the container AND each content layer separately.
- Number-display areas: empty in the panel sheet (no digits baked) — digits live on a separate bitmap font sheet.
- Text labels: empty in the button sheet (no text baked) — text rendered by engine.
- Fill bars/orbs: empty containers OR separate tintable fill strips.
- Item slots: slot frame only — item icons on their own sheet, composited at runtime.

#### Verification step (MANDATORY after each layered UI sheet)

After generation, verify in addition to the per-type rules:
1. No language-specific text baked into any button/UI element (logo branding text is OK; UI labels like "OPTIONS"/"BESTIARY" are NOT — those should be empty plate frames).
2. No fill levels baked into any progress bar / orb / gauge (empty containers only, OR separate fill textures).
3. No specific item icons baked into slots (slot frame only; item icons live on a separate sheet).
4. Frames intended for resizing have decorative corners and repeatable edges (9-slice friendly).
5. Variant states (normal/hover/pressed/locked) on the SAME container, but separated from any content layers.

If any baked content is found where it should be a layer, regenerate as separated layers and add the missing layer sheet(s) to the manifest.



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

## Tilemap Conventions (CRITICAL — apply when generating any tilemap/tileset asset)

A tilemap is a 2D grid of cells the engine paints to build a level (graveyard floor, dungeon walls, etc.). The game engine reads the tileset by `(cell_w × cell_h) × index` and stitches tiles edge-to-edge to fill the screen. This imposes hard constraints on how the source asset is authored:

### Rule 1 — Floor tiles and object/decoration sprites are SEPARATE atlases

Floor tiles tile across the entire ground plane (every cell of the visible map). Decorations (tombstones, columns, lanterns, broken statues) sit on top of the floor at specific spots. These two are **fundamentally different rendering passes** and must NOT be packed into one atlas.

| Layer | What it is | Atlas | Cell content |
|---|---|---|---|
| Floor / terrain | Continuous ground that fills every map cell | `floor-<biome>.png` | Edge-to-edge tileable texture (no transparent corners) |
| Objects / decoration | Isolated props placed on specific cells | `objects-<biome>.png` | Standalone sprites with transparent background |

When the prompt asks for a "graveyard tileset", produce TWO files: `floor-graveyard.png` and `objects-graveyard.png`. Don't pack them together — the engine treats them as two different rendering layers and packing them complicates everything (extraction, placement, slicing).

### Rule 2 — Floor tiles are FLAT SQUARE, EDGE-TO-EDGE, NO PADDING

Each floor tile must occupy 100% of its cell. No transparent corners, no diamond shape (that's an isometric pattern, not a top-down tile), no per-tile background gap, no rounded vignette. The tile is a solid opaque RGBA region edge-to-edge in its 128×128 (or 64×64 or whatever) cell.

If even 1px of transparent padding exists around the tile, two adjacent tiles will show a gap in the rendered map. Floor tiles do NOT use safe-margin envelopes — the safe-margin guidance for atlas containment exists for ICONS/BUTTONS, NOT for floor tiles.

### Rule 3 — Floor tiles must be SEAMLESSLY TILEABLE

When two of the same floor tile sit next to each other in the rendered map, the seam must be invisible. That means:

- The **right edge column** of pixels must visually flow into the **left edge column** of the same tile (and vice versa).
- The **top edge row** must flow into the **bottom edge row**.
- Patterns near edges do NOT terminate with a hard border — pebbles, cracks, grass blades, mortar lines run continuously across the seam.
- Different variants (e.g. dirt vs cobblestone) don't have to seam-match each other; they only need to seam-match COPIES OF THEMSELVES.

Organic, noisy textures (dirt, grass, sand, snow, stone) tile much better than geometric/structured patterns. Avoid centerpieces (a single rune in the middle of a tile) — placing the same tile 4×4 immediately makes the rune repeat visibly. If you need a focal element, put it on a DECORATION sprite, not on a floor tile.

### Rule 4 — TOP-DOWN view only, NO isometric/3D perspective

For top-down 2D games (Vampire Survivors, Hades, Diablo-like camera), floor tiles must be rendered as if looking STRAIGHT DOWN. No tilted/3D edges, no isometric diamond shape, no drop shadow under the tile. Otherwise tiles look like floating tilted props instead of seamless ground.

### Required prompt clauses for floor-tile generation (auto-injected by the agent)

When a manifest item is a `floor` tileset (or generic `tileset` kind without explicit "object" label), the style-gen prompt MUST include:

```
FLOOR TILESET RULES — every tile in this sheet:

1. FLAT SQUARE, EDGE-TO-EDGE. Each cell is fully painted from pixel 0 to
   pixel cellW-1 horizontally and 0 to cellH-1 vertically. NO transparent
   corners, NO diamond/hexagonal shape, NO per-tile background gap.

2. TOP-DOWN view. Looking straight down at the ground. NO isometric
   perspective, NO tilted edges, NO drop shadow under the tile.

3. SEAMLESSLY TILEABLE. The right edge column matches the left edge column;
   the top edge row matches the bottom edge row. Two copies of the same
   tile placed adjacent show NO visible seam. Patterns flow across the
   edges continuously — do NOT terminate with a border, do NOT add a
   vignette near the edges.

4. NO centerpiece focal elements. The texture should look natural when
   repeated in a 4x4 or larger grid without visible repetition artifacts.
   Focal decorations belong on the OBJECTS atlas, not the floor tileset.

5. UNIFORM PALETTE across all variants. Variation is in material
   (dirt/cobble/grass/stone), not in art style or lighting direction.
```

### Decoration/object tilesets

Object atlases (gravestones, columns, lanterns, etc.) DO use the standard atlas containment rules (safe margin, centered anchor, transparent background between cells). They are NOT seamless. Standard atlas pipeline applies — the floor rules above only apply to TERRAIN/FLOOR sheets.

## Transparent-Output Pipeline (CRITICAL — auto-applied for every transparent item)

Codex CLI's built-in `imagegen` skill produces transparency by generating on a chroma-key background and then locally running `remove_chroma_key.py` to convert that key color to alpha. By default Codex picks its own chroma color (often green `#03f904`) and frequently chains an additional "atlas containment enforcement" post-processing pass that ZEROES PIXELS within the cell margin envelope — this is destructive and silently clips decoration tips (corner spikes, glow halos, ornament fringes) the prompt asked for.

**Two methods are available** — chroma-key (default for flat content) and luminance (for glow / VFX / luminous content). As of v0.4.8 the dispatcher auto-detects which method to use based on keywords in the prompt; the agent should still inject the matching pipeline clause explicitly when building style-gen prompts, both as a belt-and-suspenders enforcement and to document the choice in the manifest.

### Method A — Luminance alpha (for luminous / glow / VFX content)

When the asset is glow-heavy (gold halos, neon rings, magical particles, fire, lightning, sparkles, light sources), chroma-key extraction leaves colored fringes on the soft edges of the glow because semi-transparent gold/light pixels visually blend with the magenta key during generation, and no chroma-key removal can fully recover the original color.

The luminance method side-steps this entirely: render on solid black, recover alpha from pixel brightness.

```
TRANSPARENT OUTPUT — LUMINANCE-BASED ALPHA EXTRACTION (mandatory):

This asset has luminous / glow / VFX content. DO NOT use magenta chroma key.

1. RENDER ON SOLID BLACK BACKGROUND (#000000). Do NOT use magenta, green,
   or any other chroma key. Paint the entire image — including the area
   outside the subject — on pure black. The glow naturally fades from
   bright color to pure black at its edges.

2. After image_gen produces the raw black-background PNG, run the plugin
   helper to recover alpha from brightness:

       python "${CLAUDE_PLUGIN_ROOT}/scripts/luminance_alpha.py" \
              <raw-black-bg.png> <final-rgba.png> --size WxH

   This computes alpha = max(R, G, B) per pixel, so:
     - pure black pixels        → fully transparent
     - bright gold/light pixels → fully opaque
     - dim glow edges           → naturally semi-transparent (smooth falloff)

3. DO NOT run remove_chroma_key.py for this asset. DO NOT use chroma-key
   alpha extraction. DO NOT add an alpha-clearing post-pass.

4. The output of step 2 IS the final asset — save directly at the
   requested output path.
```

The dispatcher will auto-inject this clause if the prompt contains keywords like `glow`, `luminous`, `neon`, `vfx`, `halo`, `particle`, `sparkle`, `radiance`, or their Korean equivalents (`글로우`, `발광`, `빛나는`, `네온`, etc.), OR if the prompt includes `--transparency=luminance`.

**Caveat:** luminance alpha makes ALL dark pixels transparent. Intentionally dark subjects (black armor, dark backgrounds, shadows) will go semi-transparent. Use chroma-key (Method B) for those.

### Method B — Chroma-key alpha (for flat / opaque-content sprites — default)

For icons, items, characters, props, tilesets, and any flat-edged subject without large luminous glow regions, the chroma-key method remains the safe default:

```
TRANSPARENT OUTPUT PIPELINE — these rules override any default behaviour:

1. CHROMA KEY: use MAGENTA #FF00FF as the chroma-key background colour for the
   generated raw image. Do not use green, blue, or any other key colour. Pure
   magenta (255, 0, 255) is the only allowed key. This colour never appears in
   the requested art and is unambiguous to extract.

2. ALPHA EXTRACTION: after generation, run the local helper
   `$CODEX_HOME/skills/.system/imagegen/scripts/remove_chroma_key.py` to convert
   the magenta key to alpha. Pass `--auto-key border` or explicit `--key #FF00FF`
   so the script removes magenta and only magenta. Standard despill is allowed.

3. ALLOWED after alpha extraction: resize the canvas with LANCZOS resampling
   to exactly match the requested output dimensions. LANCZOS preserves the
   geometric relationship between content and grid cells — a button that fit
   inside its cell at the generated size will still fit at the resized size.

4. FORBIDDEN after alpha extraction: any per-pixel ALPHA-CLEARING pass that
   loops through cells and zeroes pixels within a margin envelope. This is
   the specific destructive step that has been observed clipping decoration
   tips (spike corners, glow halos, ornament fringes) the prompt deliberately
   placed inside the safe-margin guidance. The safe-margin instruction is a
   GUIDE for generation, NOT a license for post-hoc pixel destruction.

   Also forbidden: hard-cropping anything beyond a few border pixels for
   grid alignment (e.g., trimming 2px right + 2px bottom to make an even
   grid divisor is fine; cropping anything that contains content is not).

5. After resize + alignment crop, the result IS the final asset. Save directly
   at the requested output path. Containment compliance is then audited by
   verify-atlas; if violations are found, the agent regenerates with stricter
   PROMPT-level instructions (smaller decoration, more padding), never by
   running an alpha-clearing pass.
```

The agent injects the chroma-key clauses INTO EVERY transparent style-gen prompt for flat / opaque content. For luminous content, inject the luminance clause from Method A instead. This goes alongside the Atlas Strict Containment clauses (next section) — both are required for atlas items, the transparent clauses alone for non-atlas transparent items.

### Method-selection decision tree

```
Is the item transparent?
├── No → skip both clauses entirely
└── Yes
    ├── Does the prompt describe glow / luminous / neon / VFX / halo / particles /
    │   sparkle / radiance / 글로우 / 발광 / 빛나는 / 네온 / etc?
    │   → Method A (luminance alpha)
    └── Else (flat icon, character, item, tileset, prop)
        → Method B (chroma key)
```

If unsure, prefer Method B (chroma key) — it works on any content. Method A is a specialization that produces much cleaner results on glow content but degrades dark intentional content.

The user can override the auto-detection by adding `--transparency=luminance` / `--transparency=chroma` to the prompt; the dispatcher strips the flag and logs the chosen method to stderr.

### Why this matters

Without the explicit magenta key + stop-at-step-2 instruction, Codex defaults to its own pipeline which has been observed to:
- pick green `#03f904` as the chroma key (works but inconsistent across runs)
- run a follow-up "atlas containment enforcement" script that LOOPS THROUGH every cell and clears all pixels in a 20-pixel inset zone — this PERMANENTLY DELETES decoration that the prompt explicitly requested and that the safe-margin instruction was supposed to merely guide, not enforce destructively
- silently rescale and pad the canvas, drifting from the requested output dimensions

By locking the chroma key to magenta and forbidding the destructive enforcement pass, we get: raw generation → alpha-extracted PNG → done. The asset preserves all the intentional decoration. Containment is then audited separately (via verify-atlas), and if the output bleeds across cells the agent regenerates with stricter prompt-level instructions — never by overwriting pixels.

And for glow content where chroma-key would still leave colored fringes, Method A (luminance) removes the chroma key from the equation entirely — making clean luminous transparency feasible without per-asset color cleanup.

## Multi-State Atlas Methodology — PIXEL-ALIGNED CELLS (CRITICAL)

This block solves the single most painful problem when generating UI atlases:
**cells that drift between frames.** When you ask an image generator for "two
identical button states side by side", the model will silently draw each cell
with slightly different center, scale, stroke weight, and icon position. The
drift is invisible in the atlas image itself but obvious the moment your engine
swaps cells at runtime — the button "jumps" by 5–40 px. Per-pixel realignment
after the fact is expensive, brittle, and unnecessary if the prompt is built right.

The prompt structure below is the way to force AI image generators to draw
cells that share a pixel-identical base. Use the exact wording — vague
phrasing like "two identical buttons" fails reliably.

### Required prompt skeleton (template — fill in {placeholders})

```
TASK: Render a {COLS}×{ROWS} STATE ATLAS on a single canvas.

CANVAS: exactly {CANVAS_W} × {CANVAS_H} pixels. Divide into a grid of
{COLS} columns × {ROWS} rows, where each cell is exactly {CELL_W} × {CELL_H}
pixels. Cell (col, row) occupies pixels (col*{CELL_W}, row*{CELL_H}) to
((col+1)*{CELL_W}-1, (row+1)*{CELL_H}-1).

THE BASE SUBJECT IS IDENTICAL IN EVERY CELL.

Base subject (drawn in EVERY cell at the same position, same size, same
rotation, same icon detail):
{BASE_SUBJECT_DESCRIPTION}

The base subject's geometric center MUST sit at the exact CENTER of each
cell — i.e., at pixel ({CELL_W}/2 + col*{CELL_W}, {CELL_H}/2 + row*{CELL_H}).
The base subject's BOUNDING BOX must be the SAME pixel dimensions in every
cell. The icon inside the subject (mic, speaker, dots, etc.) must appear at
the SAME relative position inside the subject in every cell.

PER-CELL DIFFERENCES (ONLY these may differ between cells — the base subject
itself is pixel-identical otherwise):

Cell [0] (col=0, row=0) — state name "{STATE_0_NAME}":
{STATE_0_DELTA}

Cell [1] (col=1, row=0) — state name "{STATE_1_NAME}":
{STATE_1_DELTA}

(...continue for each cell...)

ENFORCEMENT: do NOT redraw the base subject from scratch per cell. Treat the
base subject as a fixed stamp placed identically in every cell. Then OVERLAY
the per-cell delta on top of that stamp.

ANTI-PATTERNS — DO NOT do any of these:
- Do NOT shift the subject's center between cells.
- Do NOT scale the subject differently between cells.
- Do NOT redraw the icon at a different rotation, position, or detail level.
- Do NOT vary stroke width / line weight between cells.
- Do NOT let glow / decoration from one cell bleed across the cell boundary.

BACKGROUND: pure solid {BG_COLOR} fills all areas not covered by the subject
or its per-cell delta. The boundary between cells is a hard {BG_COLOR} line
— no glow, no halo crosses it.
```

### How to fill the template — worked examples

**Example A: 2-frame button atlas (default + pressed) for a circular mobile UI button**

```
TASK: Render a 2×1 STATE ATLAS on a single canvas.

CANVAS: exactly 768 × 384 pixels. Divide into a grid of 2 columns × 1 row,
where each cell is exactly 384 × 384 pixels.
  Cell (0,0) occupies pixels (0, 0) to (383, 383).
  Cell (1,0) occupies pixels (384, 0) to (767, 383).

THE BASE SUBJECT IS IDENTICAL IN EVERY CELL.

Base subject (drawn in EVERY cell at the same position, same size, same
icon detail):
  A circular button. Outer diameter ≈ 88% of the cell (≈ 338 px). Centered
  at the cell center. Thin gold ring border (~7 px stroke, pale warm gold
  #D4A574). Solid very dark interior fill (#0a0a0a). A bold gold line-art
  SPEAKER icon centered inside the ring (trapezoidal cone on the left +
  single curved sound wave on the right, 6 px strokes, same pale gold).

The base subject's center sits at:
  - Cell (0,0): pixel (192, 192)
  - Cell (1,0): pixel (576, 192)
The button's bounding box is the same pixel size in both cells. The speaker
icon appears at the same relative position inside the ring in both cells.

PER-CELL DIFFERENCES:

Cell (0,0) — state "default":
  Ring color #D4A574. Interior fill #0a0a0a. No glow halo, no outer ring.

Cell (1,0) — state "pressed":
  Ring color #E8C088 (brighter). Interior fill #251F15 (warm-lifted). No
  outer glow halo, no outer ring. The button is illuminated FROM WITHIN —
  it does NOT grow larger and its outline does NOT shift.

BACKGROUND: solid black (#000000) everywhere outside the buttons. The
boundary at pixel x=384 is a hard black line — no glow crosses it.
```

**Example B: main-CTA mic with single ring (default) → double ring + glow (pressed)**

```
TASK: Render a 2×1 STATE ATLAS on a single canvas.

CANVAS: exactly 1536 × 768 pixels. Cell size 768 × 768.
  Cell (0,0): pixels (0,0) – (767, 767), center at (384, 384).
  Cell (1,0): pixels (768,0) – (1535, 767), center at (1152, 384).

THE BASE SUBJECT IS IDENTICAL IN EVERY CELL.

Base subject (in EVERY cell, identical pixels):
  A circular microphone button. Diameter ≈ 420 px (≈ 55% of cell).
  Centered at the cell center. Bold gold ring border (~9 px stroke,
  #D4A574). Solid dark interior #0a0a0a. Bold gold line-art microphone
  icon (capsule head + stem + base bracket, ~8 px strokes, #D4A574)
  centered inside the ring.

Base subject center:
  - Cell (0,0): pixel (384, 384)
  - Cell (1,0): pixel (1152, 384)

PER-CELL DIFFERENCES (overlay only — base subject pixels stay identical):

Cell (0,0) — state "default" (idle):
  A soft warm gold halo extends ~80 px outward from the ring, fading
  smoothly to black. Single halo, no outer ring.

Cell (1,0) — state "pressed" (LIVE recording):
  A SECOND concentric gold ring at radius +35 px from the base ring,
  ~7 px stroke, color #D4A574. Plus a stronger, wider gold halo that
  fades to black at the cell edges. The base subject (inner ring +
  microphone icon) is UNCHANGED from cell (0,0) — same pixel position,
  same size, same stroke.

BACKGROUND: pure black (#000000). The pixel column at x=768 is a hard
boundary — no halo from cell (1,0) crosses into cell (0,0).
```

### Why this prompt structure works (and vague ones don't)

| Element | Why it matters |
|---|---|
| Explicit pixel coordinates for cell bounds AND subject center | The model has been seen to "drift" by 5–40 px when given just "centered" — giving exact pixel values reduces drift to 0–3 px on most outputs. |
| Splitting "base subject" (identical) from "per-cell delta" (allowed to differ) | The model treats the base as a stamp and the delta as an overlay, instead of regenerating each cell from scratch. |
| ENFORCEMENT clause + ANTI-PATTERNS list | Image generators ignore single-sentence constraints. Repeating the constraint as both a positive enforcement and a list of forbidden behaviors raises adherence. |
| Hard background between cells | Without an explicit boundary rule, glow halos from one cell bleed into the next, making per-cell slicing unreliable. |

### Verification step (mandatory after generation)

After generation, read the resulting atlas and verify by visual inspection:

1. Open both cells side-by-side. The base subject (button outline, icon
   position, stroke weight) must look IDENTICAL between cells. The only
   visible difference is the per-cell delta.
2. Slice the atlas by the declared grid (e.g., 2×1 at 384×384). Each
   sliced cell, viewed independently, must have its subject visibly
   centered (the subject's bounding box midpoint within ~3 px of the
   cell center).
3. If either check fails, the atlas is misaligned — regenerate with even
   stricter pixel coordinates, OR fall back to per-cell post-realignment
   via `/codex-image:realign-atlas` (last resort; loses some quality
   because of the integer-pixel shift).

### Don't try these (known failures)

- "Two identical buttons side by side" without pixel coordinates → cells drift.
- "Same button, just brighter on the right" without enumerating what must stay
  fixed → the model brightens AND moves AND resizes the button.
- "Make sure both buttons are exactly the same size" without saying *what*
  reference defines the size → the model picks a size per cell.
- Generating each cell as a separate image and stitching them yourself →
  AI variance between generation calls is worse than within-call drift; the
  cells will look like different buttons entirely.

## Atlas Strict Containment Conventions (CRITICAL — auto-applied for all atlas/sheet items)

This block is the single most important rule for sheet-style assets. AI image generators DO NOT respect grid boundaries by default. Buttons leak across cells, headers extend into neighbouring rows, icons drift to edges. When the resulting sheet is later sliced by uniform grid, content gets clipped at cell boundaries.

**For every item that is a uniform-grid atlas (sprite-sheet, button-atlas, icon-set, font-sheet, card-states, etc.), the style-gen prompt MUST include these constraints — the user never types them; the agent auto-injects them based on the item's `atlas` metadata in the manifest.**

### Required prompt clauses (auto-injected)

For any item where the manifest declares `atlas: { cols, rows, cellW, cellH, safe_margin }`, the agent MUST append the following to the style-gen prompt before invoking the dispatcher:

```
STRICT ATLAS CONTAINMENT — these rules override any default layout latitude:

1. Grid: EXACTLY {cols} columns by {rows} rows on the canvas. Each cell is
   EXACTLY {cellW} x {cellH} pixels. The total canvas dimensions equal
   {cols * cellW} x {rows * cellH}.

2. SAFE MARGIN: every visible pixel of cell content MUST stay strictly INSIDE
   the inner rectangle defined by margin {safe_margin} pixels in from each
   cell edge. That is, for each cell at (col*cellW, row*cellH), all non-
   transparent pixels must lie within
       ( col*cellW + {safe_margin}, row*cellH + {safe_margin} )
       to
       ( (col+1)*cellW - {safe_margin}, (row+1)*cellH - {safe_margin} ).
   NO decoration, ornament, glow, or shadow may cross the cell boundary or
   bleed into neighbouring cells. The {safe_margin}-pixel inset on all sides
   is non-negotiable.

3. UNIFORM ANCHOR: every cell's content is anchored at the same position
   within the cell (typically centered, or bottom-center for ground sprites).
   Same position. Same scale. Same baseline. No drift.

4. TRANSPARENT BACKGROUND between cells and outside content. No painted
   backgrounds, no shared borders, no full-canvas color washes.

5. UNIFORM STYLE: same line weight, same palette, same lighting direction
   across every cell. Variation is only in subject (e.g., different weapon
   icons) or state (e.g., normal/hover/pressed for buttons), never in art
   style.
```

The agent substitutes `{cols}`, `{rows}`, `{cellW}`, `{cellH}`, `{safe_margin}` from the manifest item's `atlas` field. If `safe_margin` is not specified, default to **max(8, min(cellW, cellH) // 16)** pixels — roughly 6% of the smaller cell dimension.

### Mandatory verification after each atlas generation

Immediately after the style-gen call for an atlas item finishes (the SAVED line appears), the agent MUST run the verify-atlas dispatcher to confirm no cell content crosses the safe-margin envelope:

```bash
node "${CLAUDE_PLUGIN_ROOT}/scripts/codex-image.mjs" verify-atlas "<saved-path>" --grid <cols>x<rows> --cell-w <cellW> --cell-h <cellH> --safe-margin <safe_margin>
```

The verifier exits 0 if clean, 1 if violations. Capture the JSON report. If `passed: false`:

1. Inspect the `violations` list for which cells bled and which sides (left/top/right/bottom overflow).
2. Append a stricter clause to the style-gen prompt — for each violated side, e.g. "INCREASE inner padding from the cell's top edge by another 16 pixels — current generation has cell {name} content starting at the cell's top edge with NO padding, which is forbidden".
3. Regenerate. Repeat up to 3 attempts. If still failing after 3 attempts, mark the item as `failed_with_violations` in the manifest results, surface the issue to the user, and continue with the rest of the batch — do NOT silently accept a broken sheet.

### Manifest schema extension for atlas items

When the agent plans the asset list (step 2 above), atlas items in the manifest take this shape:

```json
{
  "name": "ui-buttons",
  "category": "ui",
  "subject": "Menu button atlas — 5 button styles × 4 states each",
  "output_path": "mvp_2/ui/buttons.png",
  "size": "1024x1024",
  "transparent": true,
  "atlas": {
    "cols": 4,
    "rows": 5,
    "cellW": 256,
    "cellH": 204,
    "safe_margin": 12,
    "cells": [
      "primaryNormal", "primaryHover", "primaryPressed", "primaryLocked",
      "secondaryNormal", "secondaryHover", "secondaryPressed", "secondaryLocked",
      "smallNormal", "smallHover", "smallPressed", "smallLocked",
      "wideNormal", "wideHover", "widePressed", "wideLocked",
      "iconNormal", "iconHover", "iconPressed", "iconLocked"
    ]
  }
}
```

The `cells` array must contain exactly `cols * rows` names in row-major order (row 0 col 0 first, then row 0 col 1, ..., row N col M last). These names are passed to the slice command later when the user wants per-cell PNGs.

### Slicing is user-invoked, not automatic

The asset-pipeline does NOT auto-slice. After generation + verification, surface to the user:

> Sheet saved at `<output_path>`. To extract per-cell PNGs, run:
>
>     /codex-image:slice <output_path> <output_dir>/<name>_sliced "<cols>x<rows> grid, names <comma-separated>"

This keeps slicing under user control — they may want to inspect the sheet first or skip slicing entirely for sheets used as animation atlases (where the engine slices at runtime).

## Constraints

- Sequential only — never run multiple style-gen calls in parallel from one asset-pipeline invocation.
- Always do sample-first for batches > 10, no exceptions.
- Always save the manifest **before** running execution — if the session is interrupted, the user can resume from the manifest manually.
- Never modify the reference image. Never save the reference as an output artifact.
- **For sprite sheet items: always include the Sprite Sheet Conventions above in the style-gen prompt, and run the verification step after generation.**
- **For ANY atlas item (item with `atlas` field in manifest): always inject the Atlas Strict Containment clauses above into the style-gen prompt, run verify-atlas after generation, and regenerate up to 3 times if violations are found.**

## Cost note

Each generated asset is one Codex agent turn + one `image_gen` invocation. A 30-item batch is ≈ 30 turns. The sample-first step exists specifically to avoid burning the full batch on a mismatched style — flag generously when the reference looks unstable for the requested context.
