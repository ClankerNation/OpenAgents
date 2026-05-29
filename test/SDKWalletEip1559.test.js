process.env.TS_NODE_IGNORE_DIAGNOSTICS = "5102";
process.env.TS_NODE_COMPILER_OPTIONS = JSON.stringify({
  module: "commonjs",
  target: "es2020",
});

require("ts-node/register/transpile-only");

const { expect } = require("chai");
const { ethers } = require("ethers");
const { Wallet } = require("../sdk/src/auth/wallet.ts");

const privateKey = "0x59c6995e998f97a5a0044966f0945384e6e88c7a84172c5c2d7d8619b6fc0b60";

class ProviderStub {
  constructor() {
    this.calls = [];
  }

  async call(method) {
    this.calls.push(method);
    if (method === "eth_gasPrice") return "0x3b9aca00";
    if (method === "eth_getTransactionCount") return "0x0";
    throw new Error(`unexpected call: ${method}`);
  }

  getChainId() {
    return 31337;
  }

  async getBalance() {
    return 0n;
  }
}

describe("Wallet.signTransaction", function () {
  const baseTx = {
    to: "0x000000000000000000000000000000000000dEaD",
    value: 123n,
    data: "0x",
    gasLimit: 21000n,
    nonce: 7,
    chainId: 31337,
  };

  it("signs EIP-1559 type-2 transactions and matches ethers output", async function () {
    const provider = new ProviderStub();
    const wallet = new Wallet({ privateKey, provider });
    const tx = {
      ...baseTx,
      maxFeePerGas: 2_000_000_000n,
      maxPriorityFeePerGas: 1_000_000_000n,
    };

    const signed = await wallet.signTransaction(tx);
    const expectedRaw = await new ethers.Wallet(privateKey).signTransaction({ ...tx, type: 2 });

    expect(signed.raw).to.equal(expectedRaw);
    expect(signed.hash).to.equal(ethers.keccak256(expectedRaw));
    expect(signed.raw.startsWith("0x02")).to.equal(true);
    expect(provider.calls).to.not.include("eth_gasPrice");
  });

  it("keeps legacy signing when gasPrice is explicitly supplied", async function () {
    const provider = new ProviderStub();
    const wallet = new Wallet({ privateKey, provider });
    const tx = {
      ...baseTx,
      gasPrice: 1_000_000_000n,
    };

    const signed = await wallet.signTransaction(tx);
    const expectedRaw = await new ethers.Wallet(privateKey).signTransaction({ ...tx, type: 0 });

    expect(signed.raw).to.equal(expectedRaw);
    expect(signed.hash).to.equal(ethers.keccak256(expectedRaw));
    expect(signed.raw.startsWith("0x02")).to.equal(false);
  });

  it("auto-detects type 2 when maxFeePerGas is present", async function () {
    const wallet = new Wallet({ privateKey, provider: new ProviderStub() });

    const signed = await wallet.signTransaction({
      ...baseTx,
      maxFeePerGas: 2_000_000_000n,
      maxPriorityFeePerGas: 1_000_000_000n,
    });

    expect(ethers.Transaction.from(signed.raw).type).to.equal(2);
  });
});
