const { expect } = require("chai");

require("ts-node").register({
  transpileOnly: true,
  compilerOptions: {
    module: "commonjs",
    moduleResolution: "node",
    target: "es2020",
  },
});

const {
  TransactionSimulationError,
  Wallet,
} = require("../sdk/src/auth/wallet");

const PRIVATE_KEY =
  "0000000000000000000000000000000000000000000000000000000000000001";

const tx = {
  to: "0x0000000000000000000000000000000000000002",
  value: 1n,
  data: "0xabcdef",
  gasLimit: 21000n,
  gasPrice: 1n,
  nonce: 0,
};

function encodeRevertReason(reason) {
  const reasonHex = Buffer.from(reason, "utf8").toString("hex");
  const paddedReason = reasonHex.padEnd(Math.ceil(reasonHex.length / 64) * 64, "0");

  return (
    "0x08c379a0" +
    "20".padStart(64, "0") +
    (reasonHex.length / 2).toString(16).padStart(64, "0") +
    paddedReason
  );
}

function createProvider(handler) {
  const calls = [];
  let blockNumber = 1;

  return {
    calls,
    setBlockNumber(nextBlockNumber) {
      blockNumber = nextBlockNumber;
    },
    async getBlockNumber() {
      calls.push({ method: "eth_blockNumber", params: [] });
      return blockNumber;
    },
    async call(method, params = []) {
      calls.push({ method, params });
      return handler(method, params);
    },
    async getBalance() {
      return 0n;
    },
    getChainId() {
      return 1;
    },
  };
}

function createWallet(provider) {
  return new Wallet({
    privateKey: PRIVATE_KEY,
    provider,
  });
}

describe("Wallet transaction simulation", function () {
  it("runs eth_call before sending a signed transaction", async function () {
    const provider = createProvider((method) => {
      if (method === "eth_call") return "0x";
      if (method === "eth_sendRawTransaction") return "0xsent";
      throw new Error(`unexpected method ${method}`);
    });
    const wallet = createWallet(provider);

    expect(await wallet.sendTransaction(tx)).to.equal("0xsent");

    expect(provider.calls.map((call) => call.method)).to.deep.equal([
      "eth_blockNumber",
      "eth_call",
      "eth_sendRawTransaction",
    ]);
    expect(provider.calls[1].params[0]).to.include({
      to: tx.to,
      value: "0x1",
      data: "0xabcdef",
      gas: "0x5208",
    });
    expect(provider.calls[1].params[1]).to.equal("0x1");
  });

  it("decodes revert reasons and blocks raw transaction submission", async function () {
    const revertData = encodeRevertReason("insufficient stake");
    const provider = createProvider((method) => {
      if (method === "eth_call") {
        const error = new Error("execution reverted");
        error.data = revertData;
        throw error;
      }
      throw new Error(`unexpected method ${method}`);
    });
    const wallet = createWallet(provider);

    try {
      await wallet.sendTransaction(tx);
      throw new Error("expected simulation failure");
    } catch (error) {
      expect(error).to.be.instanceOf(TransactionSimulationError);
      expect(error.reason).to.equal("insufficient stake");
      expect(error.revertData).to.equal(revertData);
      expect(error.blockNumber).to.equal(1);
    }

    expect(provider.calls.map((call) => call.method)).not.to.include(
      "eth_sendRawTransaction"
    );
  });

  it("reuses a successful simulation for the same transaction in the same block", async function () {
    const provider = createProvider((method) => {
      if (method === "eth_call") return "0x";
      if (method === "eth_sendRawTransaction") return "0xsent";
      throw new Error(`unexpected method ${method}`);
    });
    const wallet = createWallet(provider);

    await wallet.sendTransaction(tx);
    await wallet.sendTransaction(tx);

    expect(provider.calls.filter((call) => call.method === "eth_call")).to.have.length(1);
    expect(
      provider.calls.filter((call) => call.method === "eth_sendRawTransaction")
    ).to.have.length(2);
  });

  it("invalidates the simulation cache when the block changes", async function () {
    const provider = createProvider((method) => {
      if (method === "eth_call") return "0x";
      if (method === "eth_sendRawTransaction") return "0xsent";
      throw new Error(`unexpected method ${method}`);
    });
    const wallet = createWallet(provider);

    await wallet.sendTransaction(tx);
    provider.setBlockNumber(2);
    await wallet.sendTransaction(tx);

    expect(provider.calls.filter((call) => call.method === "eth_call")).to.have.length(2);
  });

  it("allows callers to skip simulation explicitly", async function () {
    const provider = createProvider((method) => {
      if (method === "eth_sendRawTransaction") return "0xsent";
      throw new Error(`unexpected method ${method}`);
    });
    const wallet = createWallet(provider);

    expect(await wallet.sendTransaction(tx, { skipSimulation: true })).to.equal("0xsent");
    expect(await wallet.sendTransaction({ ...tx, skipSimulation: true })).to.equal("0xsent");
    expect(provider.calls.map((call) => call.method)).to.deep.equal([
      "eth_sendRawTransaction",
      "eth_sendRawTransaction",
    ]);
  });
});
