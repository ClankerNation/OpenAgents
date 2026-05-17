const assert = require("assert");
const { RpcProvider } = require("../sdk/src/providers/rpc.ts");

// Mock fetch for testing
let mockResponses = [];
let mockFetch;

global.fetch = async (url, options) => {
  const body = JSON.parse(options.body);
  const isBatch = Array.isArray(body);
  
  if (mockResponses.length > 0) {
    const response = mockResponses.shift();
    return {
      ok: true,
      json: async () => isBatch ? response : response[0],
    };
  }
  
  // Default: return in requested order if single, or same order if batch
  if (isBatch) {
    const responses = body.map(req => ({
      jsonrpc: "2.0",
      id: req.id,
      result: `0x${(req.id).toString(16)}`
    }));
    return { ok: true, json: async () => responses };
  }
  
  return {
    ok: true,
    json: async () => ({
      jsonrpc: "2.0",
      id: body.id,
      result: "0x1"
    }),
  };
};

async function testBatchOutOfOrderMatching() {
  console.log("TEST: Batch response out-of-order matching by ID");
  
  const provider = new RpcProvider({ url: "http://test", chainId: 1 });
  
  // Mock: responses come back in REVERSE order of requests
  mockResponses = [
    [
      { jsonrpc: "2.0", id: 2, result: "0x2" },  // block 2
      { jsonrpc: "2.0", id: 1, result: "0x1" },  // block 1
    ]
  ];
  
  const results = await provider.batchCall([
    { method: "eth_blockNumber", params: [] },
    { method: "eth_blockNumber", params: [] }
  ]);
  
  // FIX: Results should be matched by id, NOT by array position
  assert.strictEqual(results[0], "0x1", "First result should be id=1");
  assert.strictEqual(results[1], "0x2", "Second result should be id=2");
  
  console.log("  ✅ PASS: Out-of-order responses correctly matched by id");
}

async function testBatchPartialFailure() {
  console.log("TEST: Partial batch failure handling");
  
  const provider = new RpcProvider({ url: "http://test", chainId: 1 });
  
  mockResponses = [
    [
      { jsonrpc: "2.0", id: 1, result: "0x1234" },
      { jsonrpc: "2.0", id: 2, error: { code: -32000, message: "revert" } },
    ]
  ];
  
  // Without abortOnError: returns mixed array
  const results = await provider.batchCall([
    { method: "eth_call", params: [] },
    { method: "eth_call", params: [] }
  ]);
  
  assert.strictEqual(results[0], "0x1234", "Successful call returns result");
  assert(results[1] instanceof Error, "Failed call returns Error instance");
  
  console.log("  ✅ PASS: Partial failures return mixed array with errors");
  
  // With abortOnError: throws aggregated error
  mockResponses = [
    [
      { jsonrpc: "2.0", id: 3, result: "0x1234" },
      { jsonrpc: "2.0", id: 4, error: { code: -32000, message: "revert" } },
    ]
  ];
  
  try {
    await provider.batchCall(
      [
        { method: "eth_call", params: [] },
        { method: "eth_call", params: [] }
      ],
      { abortOnError: true }
    );
    assert.fail("Should have thrown");
  } catch (e) {
    assert(e.message.includes("Batch partial failure"), "Error should indicate partial failure");
    console.log("  ✅ PASS: abortOnError throws aggregated error");
  }
}

async function testBatchTimeout() {
  console.log("TEST: Batch request timeout");
  
  const provider = new RpcProvider({ 
    url: "http://test", 
    chainId: 1,
    batchRequestTimeout: 100 
  });
  
  // Mock fetch that never resolves (simulates hanging RPC)
  global.fetch = async () => new Promise(() => {}); // never resolves
  
  try {
    await provider.batchCall([
      { method: "eth_blockNumber", params: [] }
    ]);
    assert.fail("Should have timed out");
  } catch (e) {
    assert(e.message.includes("timed out"), "Error should mention timeout");
    console.log("  ✅ PASS: Request times out correctly");
  }
  
  // Restore
  global.fetch = mockFetch;
}

async function testMaxBatchSize() {
  console.log("TEST: Max batch size enforcement");
  
  const provider = new RpcProvider({ 
    url: "http://test", 
    chainId: 1,
    maxBatchSize: 2 
  });
  
  try {
    await provider.batchCall([
      { method: "eth_blockNumber", params: [] },
      { method: "eth_blockNumber", params: [] },
      { method: "eth_blockNumber", params: [] }
    ]);
    assert.fail("Should have rejected oversized batch");
  } catch (e) {
    assert(e.message.includes("exceeds max"), "Error should mention limit");
    console.log("  ✅ PASS: Oversized batch rejected");
  }
}

async function runAll() {
  mockFetch = global.fetch;
  
  console.log("\n=== RpcProvider Fix Tests ===\n");
  
  try {
    await testBatchOutOfOrderMatching();
    await testBatchPartialFailure();
    await testBatchTimeout();
    await testMaxBatchSize();
    
    console.log("\n🎉 ALL TESTS PASSED\n");
    process.exit(0);
  } catch (e) {
    console.error("\n❌ TEST FAILED:", e.message);
    console.error(e.stack);
    process.exit(1);
  }
}

runAll();
