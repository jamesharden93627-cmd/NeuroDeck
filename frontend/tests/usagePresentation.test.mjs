import assert from "node:assert/strict";
import test from "node:test";
import { formatAccountingBoundary, recordedTokenTotals } from "../src/utils/usagePresentation.ts";
import { fetchJson } from "../src/api/dashboard.ts";

// 口径：同一时刻在两种时区可能属于不同日期，展示必须保留服务端传来的原始偏移。
test("accounting boundary preserves date and timezone instead of silently converting", () => {
  assert.equal(formatAccountingBoundary("2026-09-07T19:00:00-07:00"), "2026-09-07 19:00 UTC-07:00");
  assert.equal(formatAccountingBoundary("2026-09-08T02:00:00.123Z"), "2026-09-08 02:00 UTC+00:00");
  assert.equal(formatAccountingBoundary("invalid"), "—");
});

test("chart total follows the ledger endpoint and missing data is not zero", () => {
  assert.equal(recordedTokenTotals([]), null);
  assert.deepEqual(recordedTokenTotals([
    { timestamp: "2026-09-07T07:00:00Z", ollama_tokens: 0, codex_tokens: 0 },
    { timestamp: "2026-09-08T02:00:00Z", ollama_tokens: 10, codex_tokens: 7_970_000 },
  ]), { ollama: 10, codex: 7_970_000, antigravity: 0 });
});

test("hung JSON body times out so the next polling request can proceed", async (t) => {
  t.mock.method(globalThis, "fetch", async (_url, { signal }) => ({
    ok: true,
    json: () => new Promise((_resolve, reject) => signal.addEventListener("abort", () => reject(signal.reason), { once: true })),
  }));
  // Node 的超时信号不会阻止进程退出；测试保留一个短计时器等待取消真正发生。
  const keepAlive = setTimeout(() => {}, 200);
  try { await assert.rejects(fetchJson("/api/test", undefined, 5), { name: "TimeoutError" }); }
  finally { clearTimeout(keepAlive); }
});

test("caller cancellation reaches the data request", async (t) => {
  const controller = new AbortController();
  controller.abort();
  t.mock.method(globalThis, "fetch", async (_url, { signal }) => { signal.throwIfAborted(); });
  await assert.rejects(fetchJson("/api/test", controller.signal), { name: "AbortError" });
});
