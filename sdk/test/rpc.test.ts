import test from "node:test";
import assert from "node:assert/strict";
import { RpcProvider } from "../src/providers/rpc";

test("RpcProvider batchCall", async (t) => {
  await t.test("matches out-of-order responses by id", async () => {
    const provider = new RpcProvider({ url: "http://localhost:8545", chainId: 1 });
    
    // Mock fetch
    global.fetch = async (url, options) => {
      // The provider sends requests with IDs 1 and 2
      // We will shuffle the response array
      return {
        json: async () => [
          { jsonrpc: "2.0", id: 2, result: "second" },
          { jsonrpc: "2.0", id: 1, result: "first" }
        ]
      };
    };

    const results = await provider.batchCall([
      { method: "eth_call", params: [] },
      { method: "eth_call", params: [] }
    ]);

    assert.deepEqual(results, ["first", "second"]);
  });

  await t.test("handles partial failures by returning Error objects", async () => {
    const provider = new RpcProvider({ url: "http://localhost:8545", chainId: 1 });
    
    global.fetch = async () => {
      return {
        json: async () => [
          { jsonrpc: "2.0", id: 1, result: "success" },
          { jsonrpc: "2.0", id: 2, error: { code: -32000, message: "Server error" } }
        ]
      };
    };

    const results = await provider.batchCall([
      { method: "eth_call", params: [] },
      { method: "eth_call", params: [] }
    ]);

    assert.equal(results[0], "success");
    assert.ok(results[1] instanceof Error);
    assert.equal((results[1] as Error).message, "RPC error -32000: Server error");
  });

  await t.test("handles missing responses (timeouts) by returning Error objects", async () => {
    const provider = new RpcProvider({ url: "http://localhost:8545", chainId: 1 });
    
    global.fetch = async () => {
      return {
        // Node dropped response id: 2
        json: async () => [
          { jsonrpc: "2.0", id: 1, result: "success" }
        ]
      };
    };

    const results = await provider.batchCall([
      { method: "eth_call", params: [] },
      { method: "eth_call", params: [] }
    ]);

    assert.equal(results[0], "success");
    assert.ok(results[1] instanceof Error);
    assert.equal((results[1] as Error).message, "Request timed out or missing from batch");
  });
});
