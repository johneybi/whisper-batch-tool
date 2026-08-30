const test = require("node:test");
const assert = require("node:assert/strict");
const { PRODUCT_NAME } = require("./productIdentity.cjs");

test("current desktop product identity is Whisper Studio", () => {
  assert.equal(PRODUCT_NAME, "Whisper Studio");
});
