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
  constructor(chainId = 1) {
    this.chainId = chainId;
    this.calls = [];
    this.nextNonce = 7;
  }

  async call(method, params = []) {
    this.calls.push({ method, params });
    if (method === "eth_getTransactionCount") {
      const nonce = this.nextNonce++;
      return `0x${nonce.toString(16)}`;
    }
    if (method === "eth_gasPrice") return "0x5";
    if (method === "eth_sendRawTransaction") return "0xsent";
    throw new Error(`unexpected RPC method: ${method}`);
  }

  async getBalance() {
    return 0n;
  }

  getChainId() {
    return this.chainId;
  }
}

function makeWallet(provider) {
  return new Wallet({
    provider,
    privateKey: "1".padStart(64, "0"),
  });
}

function validTx(overrides = {}) {
  return {
    to: "0x000000000000000000000000000000000000dEaD",
    value: 1n,
    data: "0x",
    gasLimit: 21000n,
    chainId: 1,
    ...overrides,
  };
}

describe("Wallet private key safety", function () {
  it("does not store the private key as an object property", function () {
    const wallet = makeWallet(new MockProvider());

    assert.equal(Object.prototype.hasOwnProperty.call(wallet, "privateKey"), false);
    assert.equal(Object.prototype.hasOwnProperty.call(wallet, "keyStore"), false);
    assert.equal(wallet.privateKey, undefined);
    assert.equal(wallet.exportPrivateKey(), "1".padStart(64, "0"));
  });

  it("zeroes the key after signing", async function () {
    const wallet = makeWallet(new MockProvider());

    await wallet.signTransaction(validTx());

    assert.throws(() => wallet.exportPrivateKey(), /zeroed/);
    await assert.rejects(() => wallet.signTransaction(validTx({ nonce: 8 })), /zeroed/);
  });

  it("rejects mismatched chain IDs before signing", async function () {
    const wallet = makeWallet(new MockProvider(1));

    await assert.rejects(
      () => wallet.signTransaction(validTx({ chainId: 2 })),
      /Chain ID mismatch/
    );
    assert.equal(wallet.exportPrivateKey(), "1".padStart(64, "0"));
  });

  it("fetches a fresh pending nonce for each transaction", async function () {
    const provider = new MockProvider();
    const first = makeWallet(provider);
    const second = makeWallet(provider);

    await first.signTransaction(validTx({ chainId: 1 }));
    await second.signTransaction(validTx({ chainId: 1 }));

    const nonceCalls = provider.calls.filter((call) => call.method === "eth_getTransactionCount");
    assert.equal(nonceCalls.length, 2);
    assert(nonceCalls.every((call) => call.params[1] === "pending"));
  });
});
