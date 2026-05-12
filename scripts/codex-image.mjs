#!/usr/bin/env node

import { spawn, spawnSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import process from "node:process";
import { pathToFileURL, fileURLToPath } from "node:url";

const MIN_NODE_VERSION = "18.18.0";
const MIN_CODEX_VERSION = "0.124.0";

function parseSemver(text) {
  const match = String(text ?? "").match(/(\d+)\.(\d+)\.(\d+)/);
  if (!match) {
    return null;
  }
  return match.slice(1, 4).map((part) => Number.parseInt(part, 10));
}

function compareSemver(a, b) {
  const left = Array.isArray(a) ? a : parseSemver(a);
  const right = Array.isArray(b) ? b : parseSemver(b);
  if (!left || !right) {
    return null;
  }
  for (let index = 0; index < 3; index += 1) {
    if (left[index] > right[index]) {
      return 1;
    }
    if (left[index] < right[index]) {
      return -1;
    }
  }
  return 0;
}

function timestampForFile(date = new Date()) {
  return date.toISOString().replace(/\.\d{3}Z$/, "Z").replace(/[-:]/g, "").replace("T", "-");
}

function parseStatusOptions(argv) {
  const options = {};
  for (let index = 0; index < argv.length; index += 1) {
    const token = argv[index];
    if (token === "--json") {
      options.json = true;
      continue;
    }
    if (token === "--cwd" || token.startsWith("--cwd=")) {
      const eq = token.indexOf("=");
      const value = eq === -1 ? argv[index + 1] : token.slice(eq + 1);
      if (!value || value.startsWith("--")) {
        throw new Error("Missing value for --cwd.");
      }
      options.cwd = value;
      if (eq === -1) {
        index += 1;
      }
      continue;
    }
    if (token === "--help" || token === "-h" || token === "help") {
      options.help = true;
      continue;
    }
  }
  return options;
}

function resolveCwd(options) {
  return path.resolve(process.cwd(), options.cwd ?? ".");
}

function runSync(command, args, options = {}) {
  const result = spawnSync(command, args, {
    cwd: options.cwd,
    env: process.env,
    encoding: "utf8",
    input: options.input,
    stdio: "pipe",
    windowsHide: true
  });

  return {
    available: !(result.error && result.error.code === "ENOENT"),
    status: result.status,
    stdout: result.stdout ?? "",
    stderr: result.stderr ?? "",
    error: result.error ?? null
  };
}

// Windows: Node 22+ refuses to spawn .cmd shims without shell:true (CVE-2024-27980),
// but the user's prompt is passed as a single arg with newlines — cmd.exe would split it.
// Bypass by invoking node directly on the codex package entry point.
function codexInvocation() {
  if (process.platform !== "win32") {
    return { cmd: "codex", prefixArgs: [] };
  }
  const npmPrefix = process.env.APPDATA ? path.join(process.env.APPDATA, "npm") : null;
  if (!npmPrefix) {
    return { cmd: "codex", prefixArgs: [] };
  }
  const codexJs = path.join(npmPrefix, "node_modules", "@openai", "codex", "bin", "codex.js");
  if (fs.existsSync(codexJs)) {
    return { cmd: process.execPath, prefixArgs: [codexJs] };
  }
  return { cmd: "codex", prefixArgs: [] };
}

function statusLine(ok, label, detail) {
  return `${ok ? "OK" : "FAIL"} ${label}: ${detail}`;
}

function findImagegenSkill() {
  const codexHome = process.env.CODEX_HOME || path.join(os.homedir(), ".codex");
  const candidate = path.join(codexHome, "skills", ".system", "imagegen", "SKILL.md");
  return fs.existsSync(candidate) ? candidate : null;
}

function buildStatusReport(options = {}) {
  const cwd = resolveCwd(options);
  const nodeVersion = process.versions.node;
  const nodeVersionCompare = compareSemver(nodeVersion, MIN_NODE_VERSION);
  const nodeOk = nodeVersionCompare !== null && nodeVersionCompare >= 0;

  const inv = codexInvocation();
  const codexVersion = runSync(inv.cmd, [...inv.prefixArgs, "--version"], { cwd });
  const codexVersionText = (codexVersion.stdout || codexVersion.stderr).trim();
  const codexVersionCompare = compareSemver(codexVersionText, MIN_CODEX_VERSION);
  const codexOk = codexVersion.available && codexVersion.status === 0 && codexVersionCompare !== null && codexVersionCompare >= 0;

  const loginStatus = codexOk ? runSync(inv.cmd, [...inv.prefixArgs, "login", "status"], { cwd }) : null;
  const loginText = loginStatus ? (loginStatus.stdout || loginStatus.stderr).trim() : "Codex unavailable";
  const loginOk = Boolean(loginStatus?.status === 0 && /logged in/i.test(loginText));

  const fullAutoStatus = codexOk ? runSync(inv.cmd, [...inv.prefixArgs, "exec", "--full-auto", "--help"], { cwd }) : null;
  const fullAutoOk = Boolean(fullAutoStatus?.status === 0);

  const imagegenSkillPath = findImagegenSkill();
  const imagegenOk = Boolean(imagegenSkillPath);

  const ready = nodeOk && codexOk && loginOk && fullAutoOk && imagegenOk;
  const nextSteps = [];
  if (!nodeOk) {
    nextSteps.push(`Install Node.js ${MIN_NODE_VERSION} or newer.`);
  }
  if (!codexVersion.available) {
    nextSteps.push("Install Codex CLI with `npm install -g @openai/codex`.");
  } else if (!codexOk) {
    nextSteps.push(`Upgrade Codex CLI to ${MIN_CODEX_VERSION} or newer with \`npm install -g @openai/codex\`.`);
  }
  if (codexOk && !loginOk) {
    nextSteps.push("Run `codex login`.");
  }
  if (codexOk && !fullAutoOk) {
    nextSteps.push("This plugin depends on `codex exec --full-auto`; verify the installed Codex CLI still supports that documented alias.");
  }
  if (!imagegenOk) {
    nextSteps.push("The Codex imagegen skill was not found under CODEX_HOME. Reinstall or update Codex CLI.");
  }

  return {
    ready,
    cwd,
    node: { ok: nodeOk, version: nodeVersion, minimum: MIN_NODE_VERSION },
    codex: {
      ok: codexOk,
      available: codexVersion.available,
      version: codexVersionText || codexVersion.error?.message || "not found",
      minimum: MIN_CODEX_VERSION
    },
    login: { ok: loginOk, detail: loginText || "not logged in" },
    fullAuto: {
      ok: fullAutoOk,
      detail: fullAutoOk
        ? "`codex exec --full-auto` accepted"
        : (fullAutoStatus?.stderr || fullAutoStatus?.stdout || "not checked").trim()
    },
    imagegenSkill: { ok: imagegenOk, path: imagegenSkillPath },
    nextSteps
  };
}

function renderStatusReport(report) {
  const lines = ["Codex Image status", "", `Ready: ${report.ready ? "yes" : "no"}`, ""];
  lines.push(statusLine(report.node.ok, "Node", `v${report.node.version} (minimum ${report.node.minimum})`));
  lines.push(statusLine(report.codex.ok, "Codex", `${report.codex.version} (minimum ${report.codex.minimum})`));
  lines.push(statusLine(report.login.ok, "Codex login", report.login.detail));
  lines.push(statusLine(report.fullAuto.ok, "Headless exec", report.fullAuto.detail));
  lines.push(statusLine(report.imagegenSkill.ok, "imagegen skill", report.imagegenSkill.path ?? "not found"));
  lines.push("");
  lines.push("Usage:");
  lines.push('  /codex-image:generate "A watercolor moonlit library, save to images/library.png at 1024x1024"');
  lines.push('  /codex-image:edit input.png "Replace the background with a clean white studio backdrop"');
  lines.push('  /codex-image:style-gen reference.png "A coin in this exact style, transparent bg, save to assets/coin.png at 512x512"');
  lines.push('  /codex-image:asset-pipeline reference.png "RPG mobile game: 5 enemies + 10 items + 4 backgrounds"');
  lines.push("");
  lines.push("Cost note: image generation runs a Codex agent turn and uses the Codex built-in image generation tool.");

  if (report.nextSteps.length > 0) {
    lines.push("");
    lines.push("Next steps:");
    for (const step of report.nextSteps) {
      lines.push(`- ${step}`);
    }
  }

  return lines.join("\n");
}

function splitFirstToken(raw) {
  const text = String(raw ?? "").trim();
  if (!text) {
    return { input: null, prompt: null };
  }
  const quoted = text.match(/^(['"])((?:\\.|(?!\1).)+)\1(?:\s+([\s\S]+))?$/);
  if (quoted) {
    return { input: quoted[2], prompt: (quoted[3] ?? "").trim() };
  }
  const unquoted = text.match(/^(\S+)(?:\s+([\s\S]+))?$/);
  if (unquoted) {
    return { input: unquoted[1], prompt: (unquoted[2] ?? "").trim() };
  }
  return { input: null, prompt: null };
}

const GENERATE_INSTRUCTION_PREFIX = `Use the imagegen skill. Built-in image_gen tool path only — do not use the CLI fallback (no OPENAI_API_KEY required).

If the user did not specify an output path, save under ./codex-images/<UTC-timestamp>-<n>.png (n=1,2,... per image).

For each saved image, print exactly one line:
SAVED: <absolute path>

User request:

`;

const EDIT_INSTRUCTION_PREFIX = `Use the imagegen skill. Built-in image_gen tool path only — do not use the CLI fallback (no OPENAI_API_KEY required).

The image attached via --image is the edit target. Preserve unrelated parts unless the user request says otherwise.

If the user did not specify an output path, save under ./codex-images/<UTC-timestamp>-edit-<n>.png (n=1,2,... per image).

For each saved image, print exactly one line:
SAVED: <absolute path>

User edit request:

`;

const STYLE_GEN_INSTRUCTION_PREFIX = `Use the imagegen skill. Built-in image_gen tool path only — do not use the CLI fallback (no OPENAI_API_KEY required).

The image attached via --image is a STYLE REFERENCE ONLY, not an edit target. Per the imagegen skill's role classification, treat it as a "supporting style input". DO NOT save, return, modify, or output the reference image itself — it is never the artifact.

Treat the request as GENERATE: produce a brand-new image whose visual style (palette, line weight, shading, composition language, mood, level of detail) matches the attached reference. The subject/content comes from the user request below; the visual style comes from the reference.

If the user did not specify an output path, save under ./codex-images/<UTC-timestamp>-stylegen-<n>.png (n=1,2,... per image).

For each saved image, print exactly one line:
SAVED: <absolute path>

User generate request (visual style must match the attached reference):

`;

function spawnCodex(args, cwd) {
  return new Promise((resolve, reject) => {
    const inv = codexInvocation();
    const child = spawn(inv.cmd, [...inv.prefixArgs, ...args], {
      cwd,
      env: process.env,
      stdio: ["ignore", "inherit", "inherit"],
      windowsHide: true
    });
    child.on("error", reject);
    child.on("close", (status, signal) => {
      resolve({ status: status ?? (signal ? 1 : 0) });
    });
  });
}

async function handleGenerate(argv) {
  const prompt = (argv.join(" ") || "").trim();
  if (!prompt) {
    console.error("Usage: /codex-image:generate <natural-language image request>");
    process.exitCode = 1;
    return;
  }
  const cwd = process.cwd();
  const codexArgs = [
    "exec",
    "--full-auto",
    "--skip-git-repo-check",
    "-C",
    cwd,
    "--",
    GENERATE_INSTRUCTION_PREFIX + prompt
  ];
  const result = await spawnCodex(codexArgs, cwd);
  if (result.status !== 0) {
    process.exitCode = result.status;
  }
}

async function handleEdit(argv) {
  const raw = argv.join(" ").trim();
  const { input, prompt } = splitFirstToken(raw);
  if (!input || !prompt) {
    console.error("Usage: /codex-image:edit <input-path> <edit instructions>");
    process.exitCode = 1;
    return;
  }
  const cwd = process.cwd();
  const inputPath = path.resolve(cwd, input);
  if (!fs.existsSync(inputPath)) {
    console.error(`Input image not found: ${inputPath}`);
    process.exitCode = 1;
    return;
  }
  const codexArgs = [
    "exec",
    "--full-auto",
    "--skip-git-repo-check",
    "--image",
    inputPath,
    "-C",
    cwd,
    "--",
    EDIT_INSTRUCTION_PREFIX + prompt
  ];
  const result = await spawnCodex(codexArgs, cwd);
  if (result.status !== 0) {
    process.exitCode = result.status;
  }
}

function handleParseArgs(argv) {
  const raw = argv.join(" ").trim();
  const { input, prompt } = splitFirstToken(raw);
  if (!input || !prompt) {
    console.error("Usage: /codex-image:asset-pipeline <reference-path> <project context description>");
    process.exitCode = 1;
    return;
  }
  const cwd = process.cwd();
  const inputPath = path.resolve(cwd, input);
  if (!fs.existsSync(inputPath)) {
    console.error(`Reference image not found: ${inputPath}`);
    process.exitCode = 1;
    return;
  }
  console.log(`REF: ${inputPath}`);
  console.log(`CONTEXT: ${prompt}`);
}

async function handleStyleGen(argv) {
  const raw = argv.join(" ").trim();
  const { input, prompt } = splitFirstToken(raw);
  if (!input || !prompt) {
    console.error("Usage: /codex-image:style-gen <reference-path> <generate instructions>");
    process.exitCode = 1;
    return;
  }
  const cwd = process.cwd();
  const inputPath = path.resolve(cwd, input);
  if (!fs.existsSync(inputPath)) {
    console.error(`Reference image not found: ${inputPath}`);
    process.exitCode = 1;
    return;
  }
  const codexArgs = [
    "exec",
    "--full-auto",
    "--skip-git-repo-check",
    "--image",
    inputPath,
    "-C",
    cwd,
    "--",
    STYLE_GEN_INSTRUCTION_PREFIX + prompt
  ];
  const result = await spawnCodex(codexArgs, cwd);
  if (result.status !== 0) {
    process.exitCode = result.status;
  }
}

function handleOrganize(argv) {
  const scriptPath = path.join(path.dirname(fileURLToPath(import.meta.url)), "organize.py");
  const py = process.platform === "win32" ? "python" : "python3";
  const result = spawnSync(py, [scriptPath, ...argv], {
    stdio: "inherit",
    windowsHide: true,
  });
  if (result.error && result.error.code === "ENOENT") {
    console.error(
      "organize: Python interpreter not found.\n" +
      "Install Python 3:\n" +
      "  Windows: https://www.python.org/downloads/\n" +
      "  macOS:   `brew install python3`\n" +
      "  Linux:   `apt install python3`"
    );
    process.exitCode = 2;
    return;
  }
  process.exitCode = result.status ?? 0;
}

function handleSlice(argv) {
  // Manifest mode: --manifest <path> [--output-dir <dir>] [--only <name,name,...>]
  //   Reads the manifest, iterates items with kind == "atlas", and slices each
  //   using its grid/cells fields. Output written to <output-dir>/<atlas-name>/
  //   (defaults to manifest-dir/<atlas-name>_sliced/).
  const manifestIdx = argv.findIndex((a) => a === "--manifest" || a.startsWith("--manifest="));
  if (manifestIdx === -1) {
    return runPythonSlice(argv, /* verifyOnly */ false);
  }
  return runManifestSlice(argv);
}

function runManifestSlice(argv) {
  // Parse flags.
  let manifestPath = null;
  let baseOutDir = null;
  let onlyFilter = null;
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === "--manifest") { manifestPath = argv[++i]; continue; }
    if (a.startsWith("--manifest=")) { manifestPath = a.slice("--manifest=".length); continue; }
    if (a === "--output-dir") { baseOutDir = argv[++i]; continue; }
    if (a.startsWith("--output-dir=")) { baseOutDir = a.slice("--output-dir=".length); continue; }
    if (a === "--only") { onlyFilter = argv[++i].split(",").map((s) => s.trim()).filter(Boolean); continue; }
    if (a.startsWith("--only=")) { onlyFilter = a.slice("--only=".length).split(",").map((s) => s.trim()).filter(Boolean); continue; }
  }
  if (!manifestPath || !fs.existsSync(manifestPath)) {
    console.error(`slice --manifest: manifest file not found: ${manifestPath}`);
    process.exitCode = 1;
    return;
  }

  let manifest;
  try {
    manifest = JSON.parse(fs.readFileSync(manifestPath, "utf8"));
  } catch (err) {
    console.error(`slice --manifest: failed to parse manifest JSON: ${err.message}`);
    process.exitCode = 1;
    return;
  }

  const manifestDir = path.dirname(path.resolve(manifestPath));
  const items = Array.isArray(manifest.items) ? manifest.items : [];
  const atlasItems = items.filter((it) => it && it.kind === "atlas");
  const filtered = onlyFilter ? atlasItems.filter((it) => onlyFilter.includes(it.name)) : atlasItems;

  if (filtered.length === 0) {
    console.error(
      `slice --manifest: no atlas items to slice` +
      (onlyFilter ? ` (filter --only=${onlyFilter.join(",")})` : "")
    );
    process.exitCode = 1;
    return;
  }

  const results = [];
  for (const item of filtered) {
    if (!item.path || !item.grid || !Array.isArray(item.cells)) {
      console.error(`slice --manifest: skipping ${item.name}: missing path/grid/cells`);
      results.push({ name: item.name, status: "skipped", reason: "missing-fields" });
      continue;
    }
    const inputPath = path.resolve(manifestDir, item.path);
    const outDir = baseOutDir
      ? path.resolve(baseOutDir, item.name)
      : path.join(manifestDir, `${item.name}_sliced`);
    const { cols, rows, cellW, cellH } = item.grid;
    const namesCsv = item.cells.join(",");
    const safeMargin = item.safe_margin ?? 8;

    console.error(`\n--- slicing ${item.name} (${cols}x${rows}) -> ${outDir} ---`);
    const sliceArgs = [
      inputPath,
      "--output-dir", outDir,
      "--grid", `${cols}x${rows}`,
      "--names", namesCsv,
      "--safe-margin", String(safeMargin),
    ];
    if (cellW != null) sliceArgs.push("--cell-w", String(cellW));
    if (cellH != null) sliceArgs.push("--cell-h", String(cellH));
    runPythonSlice(sliceArgs, /* verifyOnly */ false);
    results.push({
      name: item.name,
      status: process.exitCode === 0 ? "ok" : "failed",
      output_dir: outDir,
      cells: item.cells.length,
    });
    // Reset exit code so subsequent items still run; we summarize at the end.
    if (process.exitCode !== 0) process.exitCode = 0;
  }

  const failed = results.filter((r) => r.status === "failed").length;
  console.error(`\n=== slice --manifest summary ===`);
  for (const r of results) {
    console.error(`  ${r.status.padEnd(7)} ${r.name}  ${r.output_dir ?? ""}`);
  }
  console.error(`Total: ${results.length}  ok: ${results.length - failed}  failed: ${failed}`);
  process.exitCode = failed > 0 ? 1 : 0;
}

function handleVerifyAtlas(argv) {
  // Force --verify; user shouldn't have to pass it.
  return runPythonSlice([...argv, "--verify"], /* verifyOnly */ true);
}

function runPythonSlice(argv, verifyOnly) {
  const scriptPath = path.join(path.dirname(fileURLToPath(import.meta.url)), "slice.py");
  const py = process.platform === "win32" ? "python" : "python3";
  const result = spawnSync(py, [scriptPath, ...argv], {
    stdio: "inherit",
    windowsHide: true,
  });
  if (result.error && result.error.code === "ENOENT") {
    console.error(
      `${verifyOnly ? "verify-atlas" : "slice"}: Python interpreter not found.\n` +
      "Install Python 3 and Pillow:\n" +
      "  Windows: https://www.python.org/downloads/  then `pip install Pillow`\n" +
      "  macOS:   `brew install python3` then `pip3 install Pillow`\n" +
      "  Linux:   `apt install python3 python3-pip` then `pip3 install Pillow`"
    );
    process.exitCode = 2;
    return;
  }
  process.exitCode = result.status ?? 0;
}

function handleStatus(argv) {
  const options = parseStatusOptions(argv);
  if (options.help) {
    console.log("Usage: /codex-image:status");
    return;
  }
  const report = buildStatusReport(options);
  if (options.json) {
    console.log(JSON.stringify(report, null, 2));
  } else {
    console.log(renderStatusReport(report));
  }
  if (!report.ready) {
    process.exitCode = 1;
  }
}

function usage() {
  return [
    "Usage: node scripts/codex-image.mjs <command> [args]",
    "",
    "Commands:",
    "  status [--json] [--cwd <dir>]                       Report Codex CLI prerequisites and login state",
    "  generate <natural-language image request>           Dispatch a generate request to Codex's imagegen skill",
    "  edit <input-path> <edit instructions>               Dispatch an edit request to Codex's imagegen skill (codex exec --image)",
    "  style-gen <reference-path> <generate instructions>  Generate a new image whose visual style matches an attached reference",
    "  parse-args <reference-path> <context>               Validate asset-pipeline arguments (prints REF/CONTEXT lines)",
    "  slice <input.png> --output-dir <dir> --grid CxR [--names ...] [--safe-margin N]",
    "                                                      Slice ONE atlas sheet into per-cell PNGs + atlas.json (uses Python+Pillow)",
    "  slice --manifest <manifest.json> [--output-dir <base-dir>] [--only name1,name2,...]",
    "                                                      Slice ALL atlas-kind items from a manifest. Reads each item's grid+cells+safe_margin",
    "                                                      and writes per-atlas output dirs (one PNG per cell + atlas.json sidecar each).",
    "  verify-atlas <input.png> --grid CxR --safe-margin N [--cell-w N --cell-h N]",
    "                                                      Verify atlas sheet contents respect safe margin; reports violations",
    "  organize <manifest.json> --output-dir <dir> [--no-sliced]",
    "                                                      Reorganize an asset-pipeline manifest into kind-first layout",
    "                                                      (atlas/<name>/, sprite-sheet/, tileset/{floor,objects}/, vfx-sheet/,",
    "                                                      font-sheet/, fill-texture/, single/<sub>/). Writes new manifest.",
    "",
    "Each command is also exposed as a Claude Code plugin skill:",
    "  /codex-image:status",
    "  /codex-image:generate <...>",
    "  /codex-image:edit <input-path> <...>",
    "  /codex-image:style-gen <reference-path> <...>",
    "  /codex-image:asset-pipeline <reference-path> <project context>   (orchestrates style-gen for a planned asset batch)",
    "  /codex-image:slice <input.png> <output-dir> <grid spec>          (slice atlas sheet into per-cell PNGs)",
    "  /codex-image:organize <manifest.json> <target-dir>               (reorganize manifest into kind-first engine layout)"
  ].join("\n");
}

async function main(argv = process.argv.slice(2)) {
  const [command, ...rest] = argv;

  if (!command || command === "help" || command === "--help" || command === "-h") {
    console.log(usage());
    return;
  }

  // `setup` kept as backwards-compatible alias for the renamed `status` command.
  if (command === "status" || command === "setup") {
    handleStatus(rest);
    return;
  }

  if (command === "generate") {
    await handleGenerate(rest);
    return;
  }

  if (command === "edit") {
    await handleEdit(rest);
    return;
  }

  if (command === "style-gen") {
    await handleStyleGen(rest);
    return;
  }

  if (command === "parse-args") {
    handleParseArgs(rest);
    return;
  }

  if (command === "slice") {
    handleSlice(rest);
    return;
  }

  if (command === "verify-atlas") {
    handleVerifyAtlas(rest);
    return;
  }

  if (command === "organize") {
    handleOrganize(rest);
    return;
  }

  throw new Error(`Unknown command "${command}".\n${usage()}`);
}

if (import.meta.url === pathToFileURL(process.argv[1]).href) {
  main().catch((error) => {
    console.error(`Error: ${error.message}`);
    process.exit(1);
  });
}

export {
  buildStatusReport,
  compareSemver,
  parseSemver,
  renderStatusReport,
  splitFirstToken,
  timestampForFile
};
