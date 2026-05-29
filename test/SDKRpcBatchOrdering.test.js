const { expect } = require("chai");
require("ts-node").register({
  compilerOptions: {
    ignoreDeprecations: "6.0",
    module: "commonjs",
    moduleResolution: "node",
    target: "es2020",
  },
  skipProject: true,
  transpileOnly: true,
});

const { RpcProvider } = require("../sdk/src/providers/rpc");

describe("RpcProvider batchCall", function () {
  const originalFetch = global.fetch;

  afterEach(function () {
    global.fetch = originalFetch;
  });

  function provider() {
    return new RpcProvider({ url: "https://rpc.example", chainId: 1, timeoutMs: 25 });
  }

  it("matches shuffled batch responses by id", async function () {
    global.fetch = async (_url, init) => {
      const requests = JSON.parse(init.body);
      const responses = requests.map((request, index) => ({
        jsonrpc: "2.0",
        id: request.id,
        result: `result-${index}`,
      }));

      return {
        json: async () => responses.reverse(),
      };
    };

    const results = await provider().batchCall([
      { method: "eth_blockNumber", params: [] },
      { method: "eth_chainId", params: [] },
      { method: "net_version", params: [] },
    ]);

    expect(results).to.deep.equal(["result-0", "result-1", "result-2"]);
  });

  it("returns per-item errors for partial batch failures", async function () {
    global.fetch = async (_url, init) => {
      const [first, second, third] = JSON.parse(init.body);
      return {
        json: async () => [
          { jsonrpc: "2.0", id: third.id, result: "ok-3" },
          {
            jsonrpc: "2.0",
            id: second.id,
            error: { code: -32000, message: "execution reverted" },
          },
          { jsonrpc: "2.0", id: first.id, result: "ok-1" },
        ],
      };
    };

    const results = await provider().batchCall([
      { method: "eth_call", params: ["0x1"] },
      { method: "eth_call", params: ["0x2"] },
      { method: "eth_call", params: ["0x3"] },
    ]);

    expect(results).to.deep.equal([
      "ok-1",
      { error: { code: -32000, message: "execution reverted" } },
      "ok-3",
    ]);
  });

  it("returns per-item timeout errors for missing responses", async function () {
    global.fetch = async (_url, init) => {
      const [first, _second, third] = JSON.parse(init.body);
      return {
        json: async () => [
          { jsonrpc: "2.0", id: third.id, result: "ok-3" },
          { jsonrpc: "2.0", id: first.id, result: "ok-1" },
        ],
      };
    };

    const results = await provider().batchCall([
      { method: "eth_call", params: ["0x1"] },
      { method: "eth_call", params: ["0x2"] },
      { method: "eth_call", params: ["0x3"] },
    ]);

    expect(results[0]).to.equal("ok-1");
    expect(results[1]).to.deep.equal({
      error: {
        code: -32000,
        message: "RPC response timed out for request id 2",
      },
    });
    expect(results[2]).to.equal("ok-3");
  });

  it("returns timeout errors for every item when the batch request times out", async function () {
    global.fetch = (_url, init) =>
      new Promise((_resolve, reject) => {
        init.signal.addEventListener("abort", () => {
          const error = new Error("aborted");
          error.name = "AbortError";
          reject(error);
        });
      });

    const results = await provider().batchCall([
      { method: "eth_call", params: ["0x1"] },
      { method: "eth_call", params: ["0x2"] },
    ]);

    expect(results).to.deep.equal([
      {
        error: {
          code: -32000,
          message: "RPC response timed out for request id 1",
        },
      },
      {
        error: {
          code: -32000,
          message: "RPC response timed out for request id 2",
        },
      },
    ]);
  });
});
