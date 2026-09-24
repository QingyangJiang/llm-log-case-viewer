import assert from "node:assert/strict";
import test from "node:test";
import { CODEX_FRAME_COUNTS, CODEX_SHEET_HEIGHT, CODEX_SHEET_WIDTH } from "../app/pet-codex-export.ts";

test("Codex v1 sprite sheet has the required nine rows and 57 nonempty frames", () => {
  assert.deepEqual([...CODEX_FRAME_COUNTS], [6, 8, 8, 4, 5, 8, 6, 6, 6]);
  assert.equal(CODEX_FRAME_COUNTS.reduce((total, count) => total + count, 0), 57);
  assert.equal(CODEX_SHEET_WIDTH, 1536);
  assert.equal(CODEX_SHEET_HEIGHT, 1872);
});
