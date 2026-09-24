const { test } = require("node:test");
const assert = require("node:assert/strict");
const { normalizeCaseLensUrl, initialPetBounds } = require("../config.cjs");

test("desktop pet accepts intranet HTTP and HTTPS without storing credentials", () => {
  assert.equal(normalizeCaseLensUrl(" http://192.168.1.4:8080/ "), "http://192.168.1.4:8080");
  assert.equal(normalizeCaseLensUrl("https://case.example.com"), "https://case.example.com");
  for (const address of ["file:///etc/passwd", "javascript:alert(1)", "http://user:secret@localhost", "http://localhost/api", "http://localhost/?x=1"]) {
    assert.throws(() => normalizeCaseLensUrl(address));
  }
});

test("saved desktop pet position stays visible after monitor changes", () => {
  const screen = { x: -1920, y: 30, width: 1920, height: 1050 };
  assert.deepEqual(initialPetBounds({ x: 5000, y: -200 }, screen), { x: -282, y: 30, width: 282, height: 330 });
  assert.deepEqual(initialPetBounds(null, screen), { x: -306, y: 722, width: 282, height: 330 });
});
