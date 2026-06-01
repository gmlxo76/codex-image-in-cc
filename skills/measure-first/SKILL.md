---
description: When the user gives a reference/mockup they want replicated and asks to turn its on-screen elements into game resources, MEASURE every element's real pixel size from the mockup itself BEFORE generating — by detecting each element's exact boundary, never by guessing or arbitrary percentage crops. Run before asset-pipeline / style-gen.
argument-hint: '<mockup-or-reference-path> [<target resolution or context>]'
allowed-tools: Bash, Read, Grep, Glob
---

# Measure-First Resourcing (Codex Image)

The user shows a **mockup they like** and says "make this screen into resources." That mockup is the **source of truth** — you replicate IT. So you must measure each element's size **from the mockup itself**, accurately.

## Iron rules

> 1. **Measure from the artifact the user wants replicated** (the mockup). Do not substitute another source for sizing.
> 2. **NEVER arbitrary/percentage crops.** "crop the right 20%, that's probably the inventory" is forbidden — it slices through elements and produces garbage measurements. Every measured size MUST come from a *detected element boundary*.
> 3. No asset is generated until its pixel size is traced to a measured boundary box.

## Method — measure elements from the mockup

### 1. Canvas = the full mockup at its real resolution
Load the image, record `W×H`. All element coordinates/sizes are in this canvas. (If the game canvas differs, scale at the end — step 5.)

### 2. Detect each element's EXACT bounding box (don't eyeball, don't %-crop)
Most game UIs draw elements with a consistent accent border (cyan/teal) and a frame color (gold). Detect by color mask → connected-component labeling → per-component bounding box. This finds cards, buttons, slots, panels precisely.

```python
from PIL import Image, ImageDraw
import numpy as np
from scipy.ndimage import label
im=Image.open(MOCKUP).convert("RGB"); A=np.asarray(im).astype(int); H,W,_=A.shape
R,G,B=A[:,:,0],A[:,:,1],A[:,:,2]
# accent-border mask (tune per art: this catches bright cyan/teal UI outlines)
mask=((B-R)>40)&((G-R)>20)&(B>90)
lbl,n=label(mask)
boxes=[]
for i in range(1,n+1):
    ys,xs=np.where(lbl==i)
    if len(xs)<200: continue
    x0,x1,y0,y1=xs.min(),xs.max(),ys.min(),ys.max()
    w,h=x1-x0+1,y1-y0+1
    if w<60 or h<25: continue
    if w>W*0.95 and h>H*0.95: continue
    boxes.append((x0,y0,w,h))
boxes.sort(key=lambda b:(b[1],b[0]))
for x0,y0,w,h in boxes: print(f"x={x0} y={y0} W={w} H={h} ratio={w/h:.2f}")
# self-verify: draw the boxes and READ the result image to confirm each box hugs one element
dr=ImageDraw.Draw(im)
for x0,y0,w,h in boxes: dr.rectangle([x0,y0,x0+w,y0+h],outline=(255,0,0),width=3)
im.save(OUT_ANNOTATED)
```
- For the **gold frame**: mask `(R>150)&(G>120)&(B<110)`, take its bbox for the outer frame and the inner-edge thickness.
- For **filled/borderless** elements (a panel behind items, an icon): detect by its region color, or derive from the gap/inset relative to the bordered elements around it.
- ALWAYS self-verify: render the annotated image and READ it; every red box must tightly enclose exactly one intended element. If a box merges two elements or clips one, tighten the mask / split and re-measure. Do not trust numbers you haven't visually confirmed hug the element.

### 3. Identify & group the detected boxes
Map each bbox to its role by position/size/ratio (e.g. 3 large ~0.66 boxes side by side = cards; a column of ~2.6 boxes on the right = inventory slots; wide-short ~4:1 boxes = buttons). Pick the representative size for each repeated element (they should match; if they differ by a few px that's AA noise — use the median).

### 4. Establish containment & relationships (all in canvas px)
For each container→children: confirm children fit (card row width vs panel; N stacked slots vs inventory column height; slot vs its panel width). Record positions so the list-up preserves the mockup's layout.

### 5. Choose ONE authoring scale and scale every element together
Pick a single multiplier (commonly 2× the measured mockup px, or a factor that maps mockup canvas → target game resolution). Apply to EVERY asset so they stay consistent and children keep fitting their parents. Mixing scales is the classic bug (a slot ends up wider than its panel).

### 6. Reflect measured sizes in the resource list-up
The deliverable is a resource list where EVERY size is the measured value (and its scaled author px):

| # | Resource | Role | Measured (mockup px) | Ratio | Author px (×scale) | Fits in | Notes |
|---|---|---|---|---|---|---|---|
| 1 | outer frame | gold bezel | 1168×655 (full) | — | … | screen | 9-slice |
| 2 | card frame | shop card ×3 | 233×349 | 0.67 | 466×698 | shop panel | atlas default/selected |
| 3 | buy button | ×3 | 202×47 | 4.30 | 404×94 | card | 9-slice 3-state |
| 4 | inventory slot | ×6 | 196×74 | 2.65 | 392×148 | inven column | atlas empty/filled/hover |
| … | … | … | … | … | … | … | … |

Only after the list-up reflects the measured sizes do you proceed to `/codex-image:asset-pipeline` or `/codex-image:style-gen`, then `/codex-image:check-atlas` on every multi-cell atlas.

## Carry-forward generation gotchas

- **ASPECT-RATIO FIDELITY (mandatory):** the size you author IS the proportion the drawing must have. After every generation run `check-ratio "<path>" [--grid CxR]` — it fails if the drawn subject's aspect deviates from the requested cell/canvas aspect (e.g. an elongated bar inside a 2:1 cell). Margin/padding is fine; a proportion mismatch is not. Regenerate on failure.
- **Opaque fill:** AI renders large panels/buttons as translucent glass (center alpha ≈ 25). Sample the center pixel; if alpha ≪ 255, regenerate with "SOLID MATTE FULLY OPAQUE … NOT glass" or alpha-boost the PNG (`alpha = clip(alpha×~12, 0, 255)`).
- **Atlas alignment:** every multi-cell atlas must pass `check-atlas` (uniform cell size + centered anchor).
- **Match the mockup proportion exactly:** reproduce the measured ratio. A 2.47:1 slot when the measured mockup slot is 2.65:1 (or 2:1) is a failure — use the measured number.

## If instead modifying a live engine layout (not replicating a mockup)
When the task is to fit a real prefab (Unity `.prefab`) rather than replicate a mockup, the RectTransforms are the size source: resolve each GameObject → ITS OWN RectTransform (type 224), read `m_SizeDelta`/anchors LITERALLY (naive name→RT parsers grab wrong duplicates), and compute layout-group fit. But when the user says "replicate this mockup," the mockup wins — measure it per the method above.
