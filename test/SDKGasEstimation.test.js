const assert = require("assert");
process.env.TS_NODE_COMPILER_OPTIONS = JSON.stringify({
  module: "commonjs",
  target: "es2020",
  moduleResolution: "node",
  ignoreDeprecations: "6.0",
});
require("ts-node/register/transpile-only");

const { Wallet } = require("../sdk/src/auth/wallet.ts");

class MockProvider {
  constructor(block = { gasLimit: "0x61a8", baseFeePerGas: "0x64" }) {
    this.block = block;
    this.calls = [];
  }

  async call(method, params = []) {
    this.calls.push({ method, params });
    if (method === "eth_estimateGas") return "0x5208";
    if (method === "eth_getBlockByNumber") return this.block;
    if (method === "eth_maxPriorityFeePerGas") return "0x2";
    if (method === "eth_gasPrice") return "0x5";
    if (method === "eth_getTransactionCount") return "0x7";
    if (method === "eth_sendRawTransaction") return "0xsent";
    throw new Error(`unexpected RPC method: ${method}`);
  }

  async getBalance() {
    return 0n;
  }

  getChainId() {
    return 1;
  }
}

function makeWallet(provider) {
  return new Wallet({
    provider,
    privateKey: "1".padStart(64, "0"),
  });
}

describe("Wallet gas estimation", function () {
  it("estimates gas, adds a 20 percent margin, and caps at block gas limit", async function () {
    const provider = new MockProvider({ gasLimit: "0x61a8", baseFeePerGas: "0x64" });
    const wallet = makeWallet(provider);

    const prepared = await wallet.prepareTransaction({
      to: "0x000000000000000000000000000000000000dEaD",
      value: 1n,
      data: "0x",
    });

    assert.equal(prepared.gasLimit, 25000n);
    assert.equal(prepared.maxPriorityFeePerGas, 2n);
    assert.equal(prepared.maxFeePerGas, 202n);
    assert(provider.calls.some((call) => call.method === "eth_estimateGas"));
  });

  it("uses explicit gasLimit as a manual override", async function () {
    const provider = new MockProvider({ gasLimit: "0x100000", baseFeePerGas: undefined });
    const wallet = makeWallet(provider);

    const prepared = await wallet.prepareTransaction({
      to: "0x000000000000000000000000000000000000dEaD",
      value: 1n,
      data: "0x",
      gasLimit: 12345n,
    });

    assert.equal(prepared.gasLimit, 12345n);
    assert.equal(prepared.gasPrice, 5n);
    assert(!provider.calls.some((call) => call.method === "eth_estimateGas"));
  });

  it("preserves explicit EIP-1559 fee overrides", async function () {
    const provider = new MockProvider();
    const wallet = makeWallet(provider);

    const prepared = await wallet.prepareTransaction({
      to: "0x000000000000000000000000000000000000dEaD",
      value: 1n,
      data: "0x",
      maxFeePerGas: 500n,
      maxPriorityFeePerGas: 10n,
    });

    assert.equal(prepared.maxFeePerGas, 500n);
    assert.equal(prepared.maxPriorityFeePerGas, 10n);
    assert(!provider.calls.some((call) => call.method === "eth_maxPriorityFeePerGas"));
  });
});
