/**
 * Standalone verification script for rpc.ts batchCall ID-matching fix (Bounty #116).
 * Run with: npx tsx sdk/test/rpc.test.js
 * @timestamp: 2026-09-07
 * @contributor: Hermes Agent (hummern)
 */

const { RpcProvider } = require("../src/providers/rpc");

function assert(condition, message) {
  if (!condition) throw new Error(`FAIL: ${message}`);
  console.log(`  PASS: ${message}`);
}

async function runTests() {
  console.log("\n=== RpcProvider batchCall tests (issue #116) ===\n");

  // Test 1: out-of-order responses correctly matched by id
  console.log("Test 1: out-of-order response matching");
  {
    global.fetch = async () =>
      new Response(
        JSON.stringify([
          { jsonrpc: "2.0", id: 3, result: "result_C" },
          { jsonrpc: "2.0", id: 1, result: "result_A" },
          { jsonrpc: "2.0", id: 2, result: "result_B" },
        ]),
        { status: 200, headers: { "Content-Type": "application/json" } }
      );
    const provider = new RpcProvider({ url: "http://localhost", chainId: 1 });
    const results = await provider.batchCall([
      { method: "A", params: [] },
      { method: "B", params: [] },
      { method: "C", params: [] },
    ]);
    assert(results[0] === "result_A", "position 0 = result_A");
    assert(results[1] === "result_B", "position 1 = result_B");
    assert(results[2] === "result_C", "position 2 = result_C");
    delete global.fetch;
  }

  // Test 2: partial failures — one call errors, others succeed
  // Per acceptance criteria: individual failures don't fail the entire batch.
  // Error is stored in the array slot and throws only on access.
  console.log("\nTest 2: partial batch failure handling");
  {
    global.fetch = async () =>
      new Response(
        JSON.stringify([
          { jsonrpc: "2.0", id: 1, result: "ok" },
          { jsonrpc: "2.0", id: 2, error: { code: -32000, message: "execution reverted" } },
          { jsonrpc: "2.0", id: 3, result: "also_ok" },
        ]),
        { status: 200, headers: { "Content-Type": "application/json" } }
      );
    const provider = new RpcProvider({ url: "http://localhost", chainId: 1 });
    const results = await provider.batchCall([
      { method: "success1", params: [] },
      { method: "fail", params: [] },
      { method: "success2", params: [] },
    ]);
    // Successful slots return their result without throwing
    assert(results[0] === "ok", "position 0 = ok");
    assert(results[2] === "also_ok", "position 2 = also_ok");
    // Errored slot throws when accessed
    let threw = false;
    try { results[1]; } catch (e) { threw = true; }
    assert(threw, "position 1 throws individual error on access");
    delete global.fetch;
  }

  // Test 3: batch request timeout — entire HTTP POST times out
  // (one POST = one timeout boundary). Mock respects AbortController signal.
  console.log("\nTest 3: batch timeout");
  {
    const slowMs = 100;
    global.fetch = async (url, init) => {
      const signal = init?.signal;
      // Respect abort signal — reject if aborted during the wait
      const wait = new Promise((resolve, reject) => {
        const tid = setTimeout(resolve, slowMs);
        if (signal?.aborted) { clearTimeout(tid); const e = new Error("aborted"); e.name = "AbortError"; reject(e); }
        signal?.addEventListener("abort", () => { clearTimeout(tid); const e = new Error("aborted"); e.name = "AbortError"; reject(e); });
      });
      await wait;
      return new Response(JSON.stringify([{ jsonrpc: "2.0", id: 1, result: "late" }]), {
        status: 200, headers: { "Content-Type": "application/json" },
      });
    };
    const provider = new RpcProvider({ url: "http://localhost", chainId: 1, requestTimeoutMs: 50 });
    let threw = false;
    const start = Date.now();
    try {
      await provider.batchCall([{ method: "slow", params: [] }]);
    } catch (e) {
      threw = true;
      const elapsed = Date.now() - start;
      assert(e.message.includes("timed out"), `got timeout error: ${e.message} after ${elapsed}ms`);
    }
    assert(threw, "batchCall rejects on timeout");
    delete global.fetch;
  }

  // Test 4: empty calls returns empty array, no HTTP request made
  console.log("\nTest 4: empty calls");
  {
    let called = false;
    global.fetch = async () => { called = true; throw new Error("fetch should not be called"); };
    const provider = new RpcProvider({ url: "http://localhost", chainId: 1 });
    const results = await provider.batchCall([]);
    assert(Array.isArray(results) && results.length === 0, "empty batch returns empty array");
    assert(!called, "fetch not called for empty batch");
    delete global.fetch;
  }

  // Test 5: missing response for a request id — throws when that slot is accessed
  console.log("\nTest 5: missing response for a request id");
  {
    global.fetch = async () =>
      new Response(
        JSON.stringify([
          { jsonrpc: "2.0", id: 1, result: "ok" },
          // id=2 is missing — server didn't include it in the response
        ]),
        { status: 200, headers: { "Content-Type": "application/json" } }
      );
    const provider = new RpcProvider({ url: "http://localhost", chainId: 1 });
    const results = await provider.batchCall([
      { method: "success", params: [] },
      { method: "missing", params: [] },
    ]);
    assert(results[0] === "ok", "position 0 = ok");
    let threw = false;
    try { results[1]; } catch (e) {
      threw = true;
      assert(e.message.includes("no response for request id"), `got: ${e.message}`);
    }
    assert(threw, "position 1 throws when accessing missing response slot");
    delete global.fetch;
  }

  console.log("\n=== All tests passed ===\n");
}

runTests().catch(e => { console.error(e); process.exit(1); });
