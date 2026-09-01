import assert from "node:assert/strict";
import test from "node:test";

import { BADCASE_AUTO_SCORE_THRESHOLD, shouldAutoMarkBadcase } from "../app/annotation-rules.ts";

test("automatically marks scores below 8 as badcase", () => {
  assert.equal(BADCASE_AUTO_SCORE_THRESHOLD, 8);
  assert.equal(shouldAutoMarkBadcase(1), true);
  assert.equal(shouldAutoMarkBadcase(7), true);
  assert.equal(shouldAutoMarkBadcase(7.9), true);
  assert.equal(shouldAutoMarkBadcase(8), false);
  assert.equal(shouldAutoMarkBadcase(10), false);
});
