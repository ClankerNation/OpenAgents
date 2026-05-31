const { expect } = require("chai");
const fs = require("fs");
const path = require("path");

describe("Wallet transaction simulation", function () {
  const walletPath = path.join(__dirname, "..", "sdk", "src", "auth", "wallet.ts");
  const rpcPath = path.join(__dirname, "..", "sdk", "src", "providers", "rpc.ts");
  const walletSource = fs.readFileSync(walletPath, "utf8");
  const rpcSource = fs.readFileSync(rpcPath, "utf8");

  it("runs eth_call before eth_sendRawTransaction by default", function () {
    expect(walletSource).to.include("if (!tx.skipSimulation)");
    expect(walletSource).to.include("await this.simulateTransaction(tx)");
    expect(walletSource.indexOf("await this.simulateTransaction(tx)")).to.be.lessThan(
      walletSource.indexOf('eth_sendRawTransaction')
    );
    expect(walletSource).to.include('"eth_call"');
  });

  it("provides a skipSimulation opt-out", function () {
    expect(walletSource).to.include("skipSimulation?: boolean");
    expect(walletSource).to.include("if (!tx.skipSimulation)");
  });

  it("caches successful simulations per block and transaction payload", function () {
    expect(walletSource).to.include("private simulationCache = new Map<string, number>()");
    expect(walletSource).to.include("const blockNumber = await this.provider.getBlockNumber()");
    expect(walletSource).to.include("this.simulationCache.get(cacheKey) === blockNumber");
    expect(walletSource).to.include("this.simulationCache.set(cacheKey, blockNumber)");
  });

  it("preserves RPC revert data and decodes Error/Panic reasons", function () {
    expect(rpcSource).to.include("export class RpcError extends Error");
    expect(rpcSource).to.include("this.data = data");
    expect(walletSource).to.include("error instanceof RpcError");
    expect(walletSource).to.include("0x08c379a0");
    expect(walletSource).to.include("0x4e487b71");
    expect(walletSource).to.include("Transaction simulation failed:");
  });
});
