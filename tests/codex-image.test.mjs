import assert from "node:assert/strict";
import test from "node:test";

import {
  applyTransparencyPipeline,
  autoDetectTransparencyMethod,
  compareSemver,
  extractTransparencyFlag,
  splitFirstToken,
  timestampForFile
} from "../scripts/codex-image.mjs";

test("compareSemver handles prefixed command output", () => {
  assert.equal(compareSemver("codex-cli 0.124.0", "0.124.0"), 0);
  assert.equal(compareSemver("v20.10.0", "18.18.0"), 1);
  assert.equal(compareSemver("0.123.9", "0.124.0"), -1);
});

test("timestampForFile is filesystem-safe", () => {
  assert.equal(timestampForFile(new Date("2026-04-24T13:04:05Z")), "20260424-130405Z");
});

test("splitFirstToken splits unquoted path from prompt", () => {
  assert.deepEqual(splitFirstToken("photo.png make it red"), {
    input: "photo.png",
    prompt: "make it red"
  });
});

test("splitFirstToken supports double-quoted path with spaces", () => {
  assert.deepEqual(splitFirstToken('"my photo.png" tint blue'), {
    input: "my photo.png",
    prompt: "tint blue"
  });
});

test("splitFirstToken supports single-quoted path with spaces", () => {
  assert.deepEqual(splitFirstToken("'a b.png' brighten"), {
    input: "a b.png",
    prompt: "brighten"
  });
});

test("splitFirstToken returns nulls for empty input", () => {
  assert.deepEqual(splitFirstToken(""), { input: null, prompt: null });
  assert.deepEqual(splitFirstToken("   "), { input: null, prompt: null });
});

test("splitFirstToken returns input only when prompt is missing", () => {
  assert.deepEqual(splitFirstToken("only-path.png"), {
    input: "only-path.png",
    prompt: ""
  });
});

// ---- Transparency method auto-detection (0.4.8) ----

test("autoDetectTransparencyMethod returns 'none' when prompt does not request transparency", () => {
  assert.equal(autoDetectTransparencyMethod("a gold coin, save to coin.png at 512x512"), "none");
  assert.equal(autoDetectTransparencyMethod("character portrait against a forest"), "none");
});

test("autoDetectTransparencyMethod returns 'luminance' for glow / VFX keywords", () => {
  assert.equal(autoDetectTransparencyMethod("a glowing gold mic button, transparent background"), "luminance");
  assert.equal(autoDetectTransparencyMethod("magical aura ring, transparent bg"), "luminance");
  assert.equal(autoDetectTransparencyMethod("neon sign icon, transparent"), "luminance");
  assert.equal(autoDetectTransparencyMethod("particle sparkle VFX, transparent"), "luminance");
  assert.equal(autoDetectTransparencyMethod("이중 링 글로우 마이크 버튼, 투명 배경"), "luminance");
});

test("autoDetectTransparencyMethod returns 'chroma' for flat transparent content", () => {
  assert.equal(autoDetectTransparencyMethod("a wooden sword icon, transparent background"), "chroma");
  assert.equal(autoDetectTransparencyMethod("orc character sprite, transparent"), "chroma");
});

test("extractTransparencyFlag pulls explicit --transparency=... from the prompt", () => {
  const out = extractTransparencyFlag("a glow button --transparency=chroma, transparent bg");
  assert.equal(out.method, "chroma");
  assert.equal(out.prompt.includes("--transparency"), false);

  const lum = extractTransparencyFlag("a flat icon --transparency=luminance, transparent");
  assert.equal(lum.method, "luminance");
  assert.equal(lum.prompt.includes("--transparency"), false);

  const auto = extractTransparencyFlag("a button --transparency=auto");
  assert.equal(auto.method, "auto");

  const none = extractTransparencyFlag("a button --transparency=none");
  assert.equal(none.method, "none");

  const aliasLuma = extractTransparencyFlag("--transparency=luma button");
  assert.equal(aliasLuma.method, "luminance");

  const aliasMagenta = extractTransparencyFlag("--transparency=magenta button");
  assert.equal(aliasMagenta.method, "chroma");
});

test("extractTransparencyFlag returns null method when no flag is present", () => {
  const out = extractTransparencyFlag("a transparent glow button with halo");
  assert.equal(out.method, null);
  assert.equal(out.prompt, "a transparent glow button with halo");
});

test("applyTransparencyPipeline injects luminance clause for glow content", () => {
  const out = applyTransparencyPipeline("a glowing gold mic button, transparent background, save to mic.png");
  assert.equal(out.method, "luminance");
  assert.equal(out.prompt.includes("LUMINANCE-BASED ALPHA EXTRACTION"), true);
  assert.equal(out.prompt.includes("RENDER ON SOLID BLACK BACKGROUND"), true);
  assert.equal(out.prompt.includes("max(R, G, B)"), true);
});

test("applyTransparencyPipeline injects chroma clause for flat transparent content", () => {
  const out = applyTransparencyPipeline("a wooden sword icon, transparent background, save to sword.png");
  assert.equal(out.method, "chroma");
  assert.equal(out.prompt.includes("CHROMA-KEY ALPHA EXTRACTION"), true);
  assert.equal(out.prompt.includes("MAGENTA #FF00FF"), true);
});

test("applyTransparencyPipeline injects no clause for opaque content", () => {
  const out = applyTransparencyPipeline("a watercolor mountain landscape, save to landscape.png at 1024x1024");
  assert.equal(out.method, "none");
  assert.equal(out.prompt.includes("CHROMA-KEY"), false);
  assert.equal(out.prompt.includes("LUMINANCE"), false);
});

test("applyTransparencyPipeline respects explicit --transparency= flag over auto-detection", () => {
  // Glow content with explicit chroma override
  const forceChroma = applyTransparencyPipeline("a glowing button --transparency=chroma, transparent");
  assert.equal(forceChroma.method, "chroma");
  assert.equal(forceChroma.prompt.includes("CHROMA-KEY"), true);
  assert.equal(forceChroma.prompt.includes("--transparency"), false);

  // Flat content with explicit luminance override
  const forceLum = applyTransparencyPipeline("a flat icon --transparency=luminance, transparent");
  assert.equal(forceLum.method, "luminance");
  assert.equal(forceLum.prompt.includes("LUMINANCE-BASED"), true);
});

test("applyTransparencyPipeline --transparency=none skips pipeline entirely", () => {
  const out = applyTransparencyPipeline("a glowing button --transparency=none, transparent");
  assert.equal(out.method, "none");
  assert.equal(out.prompt.includes("CHROMA-KEY"), false);
  assert.equal(out.prompt.includes("LUMINANCE"), false);
});
