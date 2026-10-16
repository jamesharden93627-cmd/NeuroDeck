import assert from "node:assert/strict";
import test from "node:test";
import { rangeStart } from "../src/utils/timeRanges.ts";

// 功能：服务器自然日边界优先，避免浏览器时区与采集主机不同导致 KPI/图表错位。
test("server boundary takes priority over browser timezone", () => {
  const end = Date.parse("2026-09-04T19:00:00Z");
  const start = "2026-09-04T07:00:00Z";
  assert.equal(rangeStart("24H", end, start), Date.parse(start));
});

test("fallback includes today and preceding local calendar days", () => {
  const end = new Date(2026, 8, 4, 12).getTime();
  assert.equal(rangeStart("24H", end), new Date(2026, 8, 4).getTime());
  assert.equal(rangeStart("7D", end), new Date(2026, 7, 29).getTime());
  assert.equal(rangeStart("30D", end), new Date(2026, 7, 6).getTime());
});

test("invalid server timestamp falls back safely", () => {
  const end = new Date(2026, 8, 4, 12).getTime();
  assert.equal(rangeStart("24H", end, "invalid"), new Date(2026, 8, 4).getTime());
});
