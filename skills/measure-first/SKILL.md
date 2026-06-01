---
description: Measure every UI element's exact size from the source prefab/layout/reference BEFORE generating any asset — never guess sizes. Run this before asset-pipeline / style-gen when turning a mockup or reference screen into game resources.
argument-hint: '<reference-or-mockup-path> [<prefab/layout path or project context>]'
allowed-tools: Bash, Read, Grep, Glob
---

# Measure-First Resourcing (Codex Image)

When the user shows a **mockup / reference image** and asks to turn the elements on that screen into **game resources** (sprites/atlases), you MUST measure each element's exact size from the source of truth FIRST. **Never guess sizes or proportions.** Guessed sizes produce assets that don't fit (a slot wider than its panel, a panel that can't hold N rows, a slot that's the wrong aspect vs the mockup). This skill is the mandatory sizing pass that runs *before* `/codex-image:asset-pipeline` or `/codex-image:style-gen`.

## Iron rule

> No asset is generated until its pixel size is traced to a measured source value — a prefab RectTransform, a layout-group computation, or a measured crop of the reference. If you catch yourself typing a size you didn't measure, stop and measure it.

## Procedure

### 1. Identify the source of truth
- **Engine prefab/layout exists** (Unity `.prefab`/`.unity`, Unreal `.uasset` export, web CSS/Figma spec): this is authoritative. Use it.
- **Only a reference image**: measure pixels directly from the image (crop + inspect).
- Usually BOTH: prefab gives the rects, the mockup gives the look/proportion. Reconcile them and tell the user when they conflict.

### 2. Parse the prefab — resolve each GameObject to ITS OWN RectTransform
Naive "find name → nearest RectTransform" parsers grab the wrong block when names repeat (`_ani`, `z_back`, `_back` appear many times) and silently return wrong sizes. Resolve properly:

1. Index every YAML doc by `&fileID`.
2. For the target GameObject, read its `m_Component` list, find the component whose doc type is `224` (RectTransform).
3. Read that RectTransform's **literal** `m_SizeDelta`, `m_AnchorMin`, `m_AnchorMax`, `m_AnchoredPosition`, `m_Father`.
4. **Verify literally** — open the actual block and confirm the numbers; do not trust a one-pass dumper.

Example resolver (Python, adapt as needed):
```python
import re
txt=open(PREFAB,encoding="utf-8").read()
blocks=re.split(r'^--- !u!',txt,flags=re.M)[1:]
byid={}
for b in blocks:
    m=re.match(r'(\d+)\s+&(\d+)',b)
    if m: byid[m.group(2)]={'type':m.group(1),'b':b}
def name(go): 
    o=byid.get(go); return re.search(r'm_Name:\s*(.*)',o['b']).group(1).strip() if o else '?'
for k,v in byid.items():
    if v['type']=='1' and re.search(r'm_Name:\s*TARGET_NAME\b',v['b']):
        for c in re.findall(r'component:\s*\{fileID:\s*(\d+)\}',v['b']):
            o=byid.get(c)
            if o and o['type']=='224':
                sd=re.search(r'm_SizeDelta:\s*\{x:\s*([-\d.]+),\s*y:\s*([-\d.]+)\}',o['b'])
                amin=re.search(r'm_AnchorMin:\s*\{x:\s*([-\d.]+),\s*y:\s*([-\d.]+)\}',o['b'])
                amax=re.search(r'm_AnchorMax:\s*\{x:\s*([-\d.]+),\s*y:\s*([-\d.]+)\}',o['b'])
                print(c, sd.groups(), amin.groups(), amax.groups())
```

Notes on anchors:
- `anchorMin == anchorMax` (a point) → `sizeDelta` IS the element's fixed pixel size.
- `anchorMin != anchorMax` (stretch) → the element's size = parent size ± `sizeDelta`; you must resolve the parent's size (walk up until a fixed-size ancestor or the canvas reference resolution).
- Note nested sub-prefabs: the visible slot/card background may be a child element (e.g. a `_z_back` inside an inner container), NOT the root cell rect. Find the element that actually carries the sprite.

### 3. Establish the layout / coordinate system
- Find layout groups (`VerticalLayoutGroup`/`HorizontalLayoutGroup`/`GridLayoutGroup`): read `m_Padding`, `m_Spacing`, `m_ChildAlignment`, `m_ChildControl*`, `m_ChildForceExpand*`, and the child count.
- Compute the fit: e.g. *N children × childHeight + (N-1)×spacing + padding == container height?* State whether it fits exactly, overflows, or centers with slack.
- Confirm every child fits inside its parent (panel must contain its slots; a row must not exceed the column width).

### 4. If measuring from the reference image
- Crop the actual element out (PIL) and read its bounding box — don't eyeball the ratio.
- For repeated elements (slots/cards), crop ONE and measure W×H, then derive the count/pitch.
- When the prefab and mockup disagree on proportion, surface it and ask which wins (usually: follow the mockup's look, the prefab's rects).

### 5. Pick ONE consistent authoring scale
Choose a single multiplier (commonly **2×** the UI point size) and apply it to EVERY asset in the set. Mixing scales (e.g. a 1.1× panel with 2× slots) makes children end up larger than their containers. Verify: at the chosen scale, does the child still fit the parent? (childW×scale < panelW×scale, N×childH×scale ≤ panelH×scale.)

### 6. Produce a sizing table and CONFIRM before generating
Present a table and get sign-off:

| Element | Source (prefab rect / measured) | Author px (×scale) | Ratio | Fits in | Notes |
|---|---|---|---|---|---|
| panel | _layout_x 348×1092 | 696×2184 | 1:3.14 | screen | 9-slice |
| slot  | obj_y 242×182 | 484×364 | 1.33:1 | panel (54% w, 6×=panel h) | atlas cell |

Only after the user approves the table do you hand off to `/codex-image:asset-pipeline` (batch) or `/codex-image:style-gen` (single), then run `/codex-image:check-atlas` on every multi-cell atlas.

## Verification gotchas (carry into generation)
- **Opaque fill**: AI often renders large panels/buttons as translucent glass (center alpha ≈ 25). Sample the center pixel; if alpha << 255, regenerate with "SOLID MATTE FULLY OPAQUE … NOT glass" or alpha-boost the PNG (`alpha = clip(alpha×~12, 0, 255)`).
- **Atlas alignment**: every multi-cell atlas must pass `check-atlas` (uniform cell size + centered anchor) or it jumps/jitters at runtime.
- **Match the mockup, don't approximate**: if the user says "like the mockup," measure the mockup element and reproduce that proportion — a 2.47:1 slot when the mockup is 2:1 is a failure.

## Output
Always end the measurement pass with: the sizing table, the chosen scale, the fit-check math, and the list of assets to generate with their final pixel sizes. Then proceed to generation only on approval.
