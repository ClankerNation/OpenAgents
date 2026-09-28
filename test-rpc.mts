// Test runner for rpc.ts batchCall fix.
// Run with: node --experimental-strip-types test-rpc.mts
import { RpcProvider } from "./sdk/src/providers/rpc.ts";

let passed = 0, failed = 0;
function assert(cond, msg) {
  if (cond) { passed++; console.log("  ok -", msg); }
  else { failed++; console.log("  FAIL -", msg); }
}

function makeProvider(handler) {
  const p = new RpcProvider({ url: "http://x", chainId: 1, timeoutMs: 2000, retryOptions: { maxRetries: 0 } });
  globalThis.fetch = handler;
  return p;
}

// 1. Out-of-order responses must be remapped by id, not by array position
{
  console.log("test 1: out-of-order responses remapped by id");
  const p = makeProvider(async (url, opts) => {
    const reqs = JSON.parse(opts.body);
    // Respond in REVERSE order
    const resps = [...reqs].reverse().map((r) => ({
      jsonrpc: "2.0", id: r.id, result: `result-for-${r.method}`,
    }));
    return { ok: true, json: async () => resps };
  });
  const out = await p.batchCall([
    { method: "a", params: [] },
    { method: "b", params: [] },
    { method: "c", params: [] },
  ]);
  assert(out[0] === "result-for-a", "first call result returned first");
  assert(out[1] === "result-for-b", "second call result returned second");
  assert(out[2] === "result-for-c", "third call result returned third");
}

// 2. Error response in a batch must throw, not silently return undefined
{
  console.log("test 2: error response throws");
  const p = makeProvider(async (url, opts) => {
    const reqs = JSON.parse(opts.body);
    const resps = reqs.map((r) =>
      r.method === "b"
        ? { jsonrpc: "2.0", id: r.id, error: { code: -32000, message: "boom" } }
        : { jsonrpc: "2.0", id: r.id, result: "ok" }
    );
    return { ok: true, json: async () => resps };
  });
  let threw = false;
  try {
    await p.batchCall([{ method: "a" }, { method: "b" }, { method: "c" }]);
  } catch (e) { threw = /-32000/.test(e.message); }
  assert(threw, "batch error propagates");
}

// 3. Missing response for a request id must throw (old sort would misalign)
{
  console.log("test 3: missing response id throws");
  const p = makeProvider(async (url, opts) => {
    const reqs = JSON.parse(opts.body);
    // Only respond to first and third, skip middle
    const resps = [reqs[0], reqs[2]].map((r) => ({
      jsonrpc: "2.0", id: r.id, result: "ok",
    }));
    return { ok: true, json: async () => resps };
  });
  let threw = false;
  try {
    await p.batchCall([{ method: "a" }, { method: "b" }, { method: "c" }]);
  } catch (e) { threw = /no response for request id/.test(e.message); }
  assert(threw, "missing response detected");
}

// 4. Batch size cap
{
  console.log("test 4: batch size cap");
  const p = makeProvider(async () => ({ ok: true, json: async () => [] }));
  let threw = false;
  try {
    await p.batchCall(Array.from({ length: 101 }, () => ({ method: "x" })));
  } catch (e) { threw = /exceeds maximum/.test(e.message); }
  assert(threw, "101-call batch rejected");
}

// 5. Empty batch
{
  console.log("test 5: empty batch");
  const p = makeProvider(async () => { throw new Error("fetch should not be called"); });
  const out = await p.batchCall([]);
  assert(Array.isArray(out) && out.length === 0, "empty batch returns []");
}

// 6. Single call still works and throws on error
{
  console.log("test 6: single call error");
  const p = makeProvider(async () => ({
    ok: true,
    json: async () => ({ jsonrpc: "2.0", id: 1, error: { code: -32601, message: "nope" } }),
  }));
  let threw = false;
  try { await p.call("nope"); } catch (e) { threw = /-32601/.test(e.message); }
  assert(threw, "single call error throws");
}

console.log(`\n${passed} passed, ${failed} failed`);
process.exit(failed ? 1 : 0);
