"""Reorganize an asset-pipeline manifest into a KIND-FIRST folder layout.

Input:  a manifest.json with `items[]` where each item declares `kind` (atlas /
        sprite-sheet / tileset / vfx-sheet / font-sheet / fill-texture / single)
        plus a `path` relative to the manifest dir, plus optional fields
        (`subkind`, `category`, `cells`, etc.).
Output: a target directory laid out by kind, with a rewritten manifest at the
        root that points at the new relative paths.

Target layout:

    <target>/
    ├── manifest.json                       ← rewritten paths
    ├── atlas/<name>/<name>.png             ← source sheet
    ├── atlas/<name>/atlas.json             ← cell metadata (if available)
    ├── atlas/<name>/<cell>.png             ← sliced cells (if available)
    ├── sprite-sheet/<name>.png
    ├── tileset/floor/<name>.png            ← when item.subkind == "floor"
    ├── tileset/objects/<name>.png          ← when item.subkind == "objects"
    ├── tileset/<name>.png                  ← when subkind not specified
    ├── vfx-sheet/<name>.png
    ├── font-sheet/<name>.png
    ├── fill-texture/<name>.png             ← also accepts the historical
                                              "fill-textures" plural kind
    └── single/<category>/<name>.png        ← category from item.category, else
                                              inferred from source folder name

Usage:
    python organize.py <manifest> --output-dir <target> [--no-sliced]

Options:
    --no-sliced     Do not look for <name>_sliced/ directories alongside each
                    atlas item; only copy the source sheet.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

# Map manifest `kind` → top-level folder name in the kind-first layout.
KIND_FOLDER = {
    "atlas":         "atlas",
    "sprite-sheet":  "sprite-sheet",
    "tileset":       "tileset",
    "vfx-sheet":     "vfx-sheet",
    "font-sheet":    "font-sheet",
    "fill-texture":  "fill-texture",
    "fill-textures": "fill-texture",  # legacy plural
    "single":        "single",
}

# Default sub-folder under single/ for items lacking an explicit category.
SINGLE_FOLDER_HINTS = {
    "bg":         "bg",
    "background": "bg",
    "portrait":   "portrait",
    "portraits":  "portrait",
    "item":       "item",
    "items":      "item",
    "ui":         "ui",
    "vfx":        "vfx",
}


def infer_single_subfolder(item: dict) -> str:
    """Best-effort hint at which sub-folder under single/ an item belongs to."""
    cat = item.get("category")
    if cat and cat in SINGLE_FOLDER_HINTS:
        return SINGLE_FOLDER_HINTS[cat]
    p = item.get("path", "")
    first_seg = p.split("/")[0] if "/" in p else ""
    if first_seg in SINGLE_FOLDER_HINTS:
        return SINGLE_FOLDER_HINTS[first_seg]
    # Fall back to whichever first path segment we have.
    return first_seg or "misc"


def copy_file(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def organize_atlas(
    src_dir: Path,
    target: Path,
    item: dict,
    include_sliced: bool,
) -> str:
    """Copy atlas source + (optional) sliced cells into target/atlas/<name>/.

    Returns the new manifest path (relative to target)."""
    name = item["name"]
    src_png = src_dir / item["path"]
    out_dir = target / "atlas" / name
    copy_file(src_png, out_dir / f"{name}.png")
    count = 1

    if include_sliced:
        sliced_dir = src_dir / f"{name}_sliced"
        if sliced_dir.exists() and sliced_dir.is_dir():
            for child in sliced_dir.iterdir():
                if child.is_file():
                    copy_file(child, out_dir / child.name)
                    count += 1
    print(f"  atlas/{name}/      ({count} files)")
    return f"atlas/{name}/{name}.png"


def organize_single_path(item: dict, target_kind: str, sub: str | None = None) -> Path:
    """Compose the target relative path inside the kind folder."""
    name = item["name"]
    rel = Path(target_kind)
    if sub:
        rel = rel / sub
    return rel / f"{name}.png"


def organize(
    manifest_path: Path,
    target: Path,
    include_sliced: bool = True,
) -> int:
    if not manifest_path.exists():
        print(f"ERROR: manifest not found: {manifest_path}", file=sys.stderr)
        return 2

    with open(manifest_path, encoding="utf-8") as f:
        manifest = json.load(f)

    src_dir = manifest_path.resolve().parent
    target = target.resolve()
    if target.exists():
        print(f"removing existing target {target}", file=sys.stderr)
        shutil.rmtree(target)
    target.mkdir(parents=True, exist_ok=True)

    items = manifest.get("items", [])
    new_items = []
    summary = {}

    for item in items:
        kind = item.get("kind")
        name = item.get("name", "(unnamed)")
        if kind not in KIND_FOLDER:
            print(f"  WARN: unknown kind {kind!r} for item {name}, skipping", file=sys.stderr)
            new_items.append(item)
            continue

        if kind == "atlas":
            new_rel = organize_atlas(src_dir, target, item, include_sliced)
        else:
            target_kind = KIND_FOLDER[kind]
            src_path = src_dir / item["path"]
            if not src_path.exists():
                print(f"  WARN: source missing for {name}: {src_path}", file=sys.stderr)
                new_items.append(item)
                continue

            if kind == "tileset":
                sub = item.get("subkind")
                rel = organize_single_path(item, "tileset", sub if sub in ("floor", "objects") else None)
            elif kind == "single":
                rel = organize_single_path(item, "single", infer_single_subfolder(item))
            else:
                rel = organize_single_path(item, target_kind)

            copy_file(src_path, target / rel)
            new_rel = str(rel).replace("\\", "/")
            print(f"  {kind:<14} {new_rel}")

        updated = dict(item)
        updated["path"] = new_rel
        new_items.append(updated)
        summary[kind] = summary.get(kind, 0) + 1

    new_manifest = dict(manifest)
    new_manifest["items"] = new_items
    new_manifest_note = (
        "Kind-first layout: atlas/<name>/ (source + atlas.json + sliced cells), "
        "sprite-sheet/, tileset/{floor,objects}/, vfx-sheet/, font-sheet/, "
        "fill-texture/, single/<sub>/. Paths in items[].path are relative to "
        "this manifest."
    )
    new_manifest["layout_note"] = new_manifest_note

    out_manifest = target / "manifest.json"
    with open(out_manifest, "w", encoding="utf-8") as f:
        json.dump(new_manifest, f, indent=2, ensure_ascii=False)

    print()
    print(f"manifest -> {out_manifest}")
    print()
    total_files = sum(1 for p in target.rglob("*") if p.is_file())
    print(f"--- summary ---")
    print(f"  total files: {total_files}")
    for k, v in sorted(summary.items()):
        print(f"  {k}: {v} items")
    return 0


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(prog="organize.py")
    p.add_argument("manifest", help="Path to source manifest.json")
    p.add_argument("--output-dir", required=True, help="Target directory (kind-first layout)")
    p.add_argument(
        "--no-sliced",
        action="store_true",
        help="Skip looking for <name>_sliced/ directories alongside atlas items",
    )
    args = p.parse_args(argv)

    return organize(
        manifest_path=Path(args.manifest),
        target=Path(args.output_dir),
        include_sliced=not args.no_sliced,
    )


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
