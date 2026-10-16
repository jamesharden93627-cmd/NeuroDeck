import assert from "node:assert/strict";
import test from "node:test";

import { activityToTokenVolume, niceTokenCeiling, summarizeTokenVolume } from "../src/utils/tokenVolume.ts";

// 功能：双供应商合计与峰值必须来自同一批事件桶。
test("summarizes provider volume and peak bucket", () => {
  const summary = summarizeTokenVolume([
    { timestamp: "2026-09-06T00:00:00Z", ollama_tokens: 30, codex_tokens: 70 },
    { timestamp: "2026-09-06T01:00:00Z", ollama_tokens: 20, codex_tokens: 180 },
  ]);

  assert.deepEqual(summary, {
    total: 300,
    ollama: 50,
    codex: 250,
    antigravity: 0,
    peakIndex: 1,
    peakTotal: 200,
  });
});

test("creates readable non-zero chart ceilings", () => {
  assert.equal(niceTokenCeiling(0), 1);
  assert.equal(niceTokenCeiling(1_201), 2_000);
  assert.equal(niceTokenCeiling(72_000), 100_000);
});

test("derives hourly volume from the same cumulative activity watermark", () => {
  const volume = activityToTokenVolume([
    { timestamp: "2026-09-06T00:00:00Z", ollama_tokens: 0, codex_tokens: 0 },
    { timestamp: "2026-09-06T00:05:00Z", ollama_tokens: 10, codex_tokens: 40 },
    { timestamp: "2026-09-06T00:10:00Z", ollama_tokens: 15, codex_tokens: 100 },
    { timestamp: "2026-09-06T01:05:00Z", ollama_tokens: 30, codex_tokens: 130 },
  ], "24H");

  assert.deepEqual(volume.map(({ ollama_tokens, codex_tokens }) => ({ ollama_tokens, codex_tokens })), [
    { ollama_tokens: 15, codex_tokens: 100 },
    { ollama_tokens: 15, codex_tokens: 30 },
  ]);
  assert.equal(summarizeTokenVolume(volume).total, 160);
});
