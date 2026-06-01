const { expect } = require("chai");

require("ts-node").register({
  transpileOnly: true,
  compilerOptions: {
    module: "CommonJS",
    moduleResolution: "node",
    ignoreDeprecations: "6.0",
  },
});

const {
  JsonRpcBatchItemError,
  RpcProvider,
} = require("../sdk/src/providers/rpc.ts");

describe("SDK RPC batch calls", function () {
  const originalFetch = global.fetch;

  afterEach(function () {
    global.fetch = originalFetch;
  });

  it("matches shuffled batch responses by JSON-RPC id", async function () {
    global.fetch = async (_url, options) => {
      const requests = JSON.parse(options.body);

      return {
        ok: true,
        status: 200,
        statusText: "OK",
        json: async () => [
          { jsonrpc: "2.0", id: requests[2].id, result: "third" },
          { jsonrpc: "2.0", id: requests[0].id, result: "first" },
          { jsonrpc: "2.0", id: requests[1].id, result: "second" },
        ],
      };
    };

    const provider = new RpcProvider({
      url: "https://rpc.example",
      chainId: 1,
    });

    const results = await provider.batchCall([
      { method: "first", params: [] },
      { method: "second", params: [] },
      { method: "third", params: [] },
    ]);

    expect(results).to.deep.equal(["first", "second", "third"]);
  });

  it("returns per-request errors for partial failures and missing responses", async function () {
    let callCount = 0;
    global.fetch = async (_url, options) => {
      callCount++;
      const requests = JSON.parse(options.body);

      // First call: 5 requests, responses only for 3 with one error
      return {
        ok: true,
        status: 200,
        statusText: "OK",
        json: async () => [
          { jsonrpc: "2.0", id: requests[0].id, result: "ok-0" },
          {
            jsonrpc: "2.0",
            id: requests[2].id,
            error: { code: -32000, message: "execution reverted" },
          },
          { jsonrpc: "2.0", id: requests[4].id, result: "ok-4" },
          // requests[1] and requests[3] have no response
        ],
      };
    };

    const provider = new RpcProvider({
      url: "https://rpc.example",
      chainId: 1,
    });

    const results = await provider.batchCall([
      { method: "eth_call", params: ["0x01"] },
      { method: "eth_call", params: ["0x02"] },
      { method: "eth_call", params: ["0x03"] },
      { method: "eth_call", params: ["0x04"] },
      { method: "eth_call", params: ["0x05"] },
    ]);

    // Results in original order
    expect(results[0]).to.equal("ok-0");
    expect(results[1]).to.be.instanceOf(JsonRpcBatchItemError);
    expect((results[1] as JsonRpcBatchItemError).message).to.include(
      "No response for request id"
    );
    expect(results[2]).to.be.instanceOf(JsonRpcBatchItemError);
    expect((results[2] as JsonRpcBatchItemError).message).to.equal(
      "execution reverted"
    );
    expect(results[3]).to.be.instanceOf(JsonRpcBatchItemError);
    expect((results[3] as JsonRpcBatchItemError).message).to.include(
      "No response for request id"
    );
    expect(results[4]).to.equal("ok-4");
  });

  it("times out individual batch requests and returns per-item errors", async function () {
    global.fetch = async (_url, options) => {
      // Never resolve - simulates hang
      return new Promise(() => {});
    };

    const provider = new RpcProvider({
      url: "https://rpc.example",
      chainId: 1,
    });

    const results = await provider.batchCall(
      [
        { method: "eth_call", params: [] },
        { method: "eth_call", params: [] },
      ],
      { timeoutMs: 100 }
    );

    expect(results).to.have.lengthOf(2);
    for (const r of results) {
      expect(r).to.be.instanceOf(JsonRpcBatchItemError);
      expect((r as JsonRpcBatchItemError).message).to.include("timed out");
    }
  });

  it("rejects batch size exceeding limit", async function () {
    const provider = new RpcProvider({
      url: "https://rpc.example",
      chainId: 1,
    });

    const calls = Array.from({ length: 101 }, (_, i) => ({
      method: "eth_call",
      params: [`0x${i}`],
    }));

    await expect(provider.batchCall(calls)).to.be.rejectedWith(
      /Batch size .* exceeds limit/
    );
  });

  it("returns empty array for empty batch", async function () {
    const provider = new RpcProvider({
      url: "https://rpc.example",
      chainId: 1,
    });

    const results = await provider.batchCall([]);
    expect(results).to.deep.equal([]);
  });

  it("handles duplicate response ids by using first match", async function () {
    global.fetch = async (_url, options) => {
      const requests = JSON.parse(options.body);
      return {
        ok: true,
        status: 200,
        statusText: "OK",
        json: async () => [
          { jsonrpc: "2.0", id: requests[0].id, result: "first-result" },
          { jsonrpc: "2.0", id: requests[0].id, result: "duplicate-result" },
        ],
      };
    };

    const provider = new RpcProvider({
      url: "https://rpc.example",
      chainId: 1,
    });

    const results = await provider.batchCall([
      { method: "eth_call", params: [] },
    ]);

    expect(results[0]).to.equal("first-result");
  });

  it("preserves JsonRpcBatchItemError properties for partial failure debugging", async function () {
    global.fetch = async (_url, options) => {
      const requests = JSON.parse(options.body);
      return {
        ok: true,
        status: 200,
        statusText: "OK",
        json: async () => [
          {
            jsonrpc: "2.0",
            id: requests[0].id,
            error: {
              code: -32601,
              message: "Method not found",
              data: "eth_badMethod",
            },
          },
        ],
      };
    };

    const provider = new RpcProvider({
      url: "https://rpc.example",
      chainId: 1,
    });

    const results = await provider.batchCall([
      { method: "eth_badMethod", params: [] },
    ]);

    const err = results[0] as JsonRpcBatchItemError;
    expect(err).to.be.instanceOf(JsonRpcBatchItemError);
    expect(err.name).to.equal("JsonRpcBatchItemError");
    expect(err.code).to.equal(-32601);
    expect(err.data).to.equal("eth_badMethod");
    expect(err.method).to.equal("eth_badMethod");
  });
});
