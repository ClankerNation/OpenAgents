const assert = require("assert");
const fs = require("fs");
const path = require("path");
const test = require("node:test");
const ts = require("typescript");

require.extensions[".ts"] = function loadTypeScript(module, filename) {
  const source = fs.readFileSync(filename, "utf8");
  const output = ts.transpileModule(source, {
    compilerOptions: {
      target: ts.ScriptTarget.ES2020,
      module: ts.ModuleKind.CommonJS,
      esModuleInterop: true,
    },
  });
  module._compile(output.outputText, filename);
};

const { Wallet } = require(path.resolve("sdk/src/auth/wallet.ts"));

class MockProvider {
  constructor(responses) {
    this.responses = responses;
    this.calls = [];
  }

  async call(method, params = []) {
    this.calls.push({ method, params });
    const response = this.responses[method];
    if (response instanceof Error) throw response;
    return typeof response === "function" ? response(params) : response;
  }

  async getBalance() {
    return 0n;
  }

  getChainId() {
    return 1;
  }
}

const privateKey = "1".padStart(64, "0");
const baseTx = {
  to: "0x000000000000000000000000000000000000dEaD",
  value: 1n,
  data: "0x1234",
};

test("prepareTransaction estimates gas with a 20% margin and caps at block gas limit", async () => {
  const provider = new MockProvider({
    eth_estimateGas: "0x2710",
    eth_getBlockByNumber: { gasLimit: "0x2ee0", baseFeePerGas: "0x64" },
    eth_maxPriorityFeePerGas: "0x2",
  });
  const wallet = new Wallet({ privateKey, provider });

  const prepared = await wallet.prepareTransaction(baseTx);

  assert.equal(prepared.gasLimit, 12_000n);
  assert.equal(prepared.maxPriorityFeePerGas, 2n);
  assert.equal(prepared.maxFeePerGas, 202n);
  assert.deepEqual(provider.calls.slice(0, 3).map((call) => call.method), [
    "eth_estimateGas",
    "eth_getBlockByNumber",
    "eth_getBlockByNumber",
  ]);
});

test("prepareTransaction respects manual gas and fee overrides", async () => {
  const provider = new MockProvider({});
  const wallet = new Wallet({ privateKey, provider });

  const prepared = await wallet.prepareTransaction({
    ...baseTx,
    gasLimit: 50_000n,
    maxFeePerGas: 100n,
    maxPriorityFeePerGas: 3n,
  });

  assert.equal(prepared.gasLimit, 50_000n);
  assert.equal(prepared.maxFeePerGas, 100n);
  assert.equal(prepared.maxPriorityFeePerGas, 3n);
  assert.equal(provider.calls.length, 0);
});

test("prepareTransaction falls back to legacy gasPrice when EIP-1559 data is unavailable", async () => {
  const provider = new MockProvider({
    eth_estimateGas: "0x5208",
    eth_getBlockByNumber: (params) => {
      if (params[0] === "latest") return { gasLimit: "0x100000" };
      return {};
    },
    eth_gasPrice: "0x9",
  });
  const wallet = new Wallet({ privateKey, provider });

  const prepared = await wallet.prepareTransaction(baseTx);

  assert.equal(prepared.gasLimit, 25_200n);
  assert.equal(prepared.gasPrice, 9n);
});
