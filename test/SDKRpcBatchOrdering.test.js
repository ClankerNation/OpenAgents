const assert = require("assert");
process.env.TS_NODE_COMPILER_OPTIONS = JSON.stringify({
  module: "commonjs",
  target: "es2020",
  moduleResolution: "node",
  ignoreDeprecations: "6.0",
});
require("ts-node/register/transpile-only");

const { RpcProvider } = require("../sdk/src/providers/rpc.ts");

function jsonResponse(payload) {
  return {
    async json() {
      return payload;
    },
  };
}

describe("RpcProvider batch responses", function () {
  let originalFetch;

  beforeEach(function () {
    originalFetch = global.fetch;
  });

  afterEach(function () {
    global.fetch = originalFetch;
  });

  it("matches shuffled responses by request id", async function () {
    global.fetch = async (_url, options) => {
      const requests = JSON.parse(options.body);
      return jsonResponse([
        { jsonrpc: "2.0", id: requests[2].id, result: "third" },
        { jsonrpc: "2.0", id: requests[0].id, result: "first" },
        { jsonrpc: "2.0", id: requests[1].id, result: "second" },
      ]);
    };

    const provider = new RpcProvider({ url: "http://rpc.local", chainId: 1 });
    const results = await provider.batchCall([
      { method: "first", params: [] },
      { method: "second", params: [] },
      { method: "third", params: [] },
    ]);

    assert.deepEqual(results, ["first", "second", "third"]);
  });

  it("returns per-item errors for partial failures", async function () {
    global.fetch = async (_url, options) => {
      const requests = JSON.parse(options.body);
      return jsonResponse([
        { jsonrpc: "2.0", id: requests[0].id, result: "ok" },
        { jsonrpc: "2.0", id: requests[1].id, error: { code: -32602, message: "bad params" } },
        { jsonrpc: "2.0", id: requests[2].id, result: "also ok" },
      ]);
    };

    const provider = new RpcProvider({ url: "http://rpc.local", chainId: 1 });
    const results = await provider.batchCall([
      { method: "ok", params: [] },
      { method: "bad", params: [] },
      { method: "ok2", params: [] },
    ]);

    assert.equal(results[0], "ok");
    assert.deepEqual(results[1], { error: { code: -32602, message: "bad params", data: undefined } });
    assert.equal(results[2], "also ok");
  });

  it("returns a timed-out error for missing batch items", async function () {
    global.fetch = async (_url, options) => {
      const requests = JSON.parse(options.body);
      return jsonResponse([
        { jsonrpc: "2.0", id: requests[1].id, result: "second" },
      ]);
    };

    const provider = new RpcProvider({ url: "http://rpc.local", chainId: 1 });
    const results = await provider.batchCall([
      { method: "missing", params: [] },
      { method: "present", params: [] },
    ]);

    assert.equal(results[1], "second");
    assert.equal(results[0].error.code, -32000);
    assert.match(results[0].error.message, /timed out/);
    assert.equal(results[0].error.data.method, "missing");
  });
});
