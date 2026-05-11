---
description: Generate a new image whose visual style matches an attached reference image, via Codex CLI's built-in imagegen skill
argument-hint: '<reference-path> <natural-language generate request>'
allowed-tools: Bash(node:*)
---

# Style-Reference Generate (Codex Image)

The first whitespace-separated token in the arguments is the **reference image path** (used as a style/composition/mood reference only — never edited or returned). The rest is the generation prompt describing the new subject and any size/output-path/quality details in natural language. Quote the path if it contains spaces (e.g. `"my reference.png" draw a coin in this style ...`).

Run:

```bash
node "${CLAUDE_PLUGIN_ROOT}/scripts/codex-image.mjs" style-gen "$ARGUMENTS"
```

Output rules:
- Show the command stdout to the user verbatim — Codex prints one `SAVED: <absolute path>` line per saved image.
- If the exit code is non-zero, show stderr and stop. Common failures: missing reference image, missing generate prompt.
- Do not run any additional generations unless the user explicitly asks for another attempt.

Behavior notes:
- The reference is attached via `codex exec --image` and labeled as a *style reference* (not an edit target). The new image takes its **subject** from the user prompt and its **visual style** (palette, line weight, shading, composition, mood) from the reference.
- The reference image itself is never modified or saved. Only newly generated images are written to disk.
- Output path, size, count, transparency, and quality are all controlled via natural language inside the prompt (this command exposes no flags — same convention as `/codex-image:generate`).
