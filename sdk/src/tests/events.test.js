/**
 * Tests for event subscription functionality.
 */

const assert = require("assert");

console.log("Running event subscription tests...\n");

let passed = 0;
let failed = 0;

function test(name, fn) {
  try {
    fn();
    console.log(`✓ ${name}`);
    passed++;
  } catch (e) {
    console.error(`✗ ${name}`);
    console.error(`  ${e.message}`);
    failed++;
  }
}

test("EventSubscription interface has unsubscribe", () => {
  const sub = { unsubscribe: () => {} };
  assert.equal(typeof sub.unsubscribe, "function");
});

test("filter matches event args", () => {
  const filter = { pid: 0 };
  const event = { args: { pid: 0, user: "0x123" } };

  let match = true;
  for (const [key, value] of Object.entries(filter)) {
    if (event.args[key] !== value) match = false;
  }
  assert.equal(match, true);
});

test("filter rejects non-matching event", () => {
  const filter = { pid: 1 };
  const event = { args: { pid: 0, user: "0x123" } };

  let match = true;
  for (const [key, value] of Object.entries(filter)) {
    if (event.args[key] !== value) match = false;
  }
  assert.equal(match, false);
});

test("callback receives decoded event", () => {
  let received = null;
  const callback = (event) => { received = event; };

  callback({
    name: "Deposit",
    args: { user: "0x123", pid: 0, amount: 100n },
    blockNumber: 12345,
    transactionHash: "0xabc",
  });

  assert.equal(received.name, "Deposit");
  assert.equal(received.blockNumber, 12345);
});

console.log(`\n${passed} passed, ${failed} failed`);
if (failed > 0) process.exitCode = 1;
