require("ts-node/register/transpile-only");
const hre = require("hardhat");
const chai = require("chai");
const { OpenAgentsSDK } = require("../sdk/src/index.ts");

const { ethers } = hre;
const { expect } = chai;

const ZERO = "0x0000000000000000000000000000000000000000";
// hardhat account #0, funded by the default fixture
const PK = "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80";

function sdk() {
  return new OpenAgentsSDK({
    name: "test",
    endpoint: "http://localhost",
    privateKey: PK,
    rpcUrl: "",
    registryAddress: ZERO,
    routerAddress: ZERO,
    provider: ethers.provider,
  });
}

describe("OpenAgentsSDK.deployContract", () => {
  it("deploys with constructor args and returns the address", async () => {
    const client = sdk();
    const art = await ethers.getContractFactory("AgentToken");
    const { contract, receipt } = await client.deployContract(
      art.interface.fragments,
      art.bytecode,
      ["Deployed", "DEP", ethers.parseEther("1000")],
    );

    expect(receipt.address).to.equal(await contract.getAddress());
    expect(ethers.isAddress(receipt.address)).to.equal(true);

    const token = new ethers.Contract(receipt.address, art.interface, ethers.provider);
    expect(await token.name()).to.equal("Deployed");
    expect(await token.totalSupply()).to.equal(ethers.parseEther("1000"));
  });

  it("returns a receipt with full deployment metadata", async () => {
    const client = sdk();
    const art = await ethers.getContractFactory("AgentToken");
    const { receipt } = await client.deployContract(art.interface.fragments, art.bytecode, [
      "Meta",
      "MET",
      1n,
    ]);

    expect(receipt.txHash).to.match(/^0x[0-9a-f]{64}$/);
    expect(receipt.gasUsed).to.be.greaterThan(0n);
    expect(receipt.blockNumber).to.be.greaterThan(0);
    expect(receipt.confirmations).to.be.greaterThan(0);
  });

  it("honours the requested confirmation depth", async () => {
    const client = sdk();
    const art = await ethers.getContractFactory("AgentToken");
    const pending = client.deployContract(
      art.interface.fragments,
      art.bytecode,
      ["Conf", "CNF", 1n],
      { confirmations: 3 },
    );

    // the in-process node only advances when told to, so keep mining until it settles
    let settled = false;
    pending.finally(() => {
      settled = true;
    });
    for (let i = 0; i < 120 && !settled; i++) {
      await ethers.provider.send("evm_mine", []);
      await new Promise((r) => setTimeout(r, 25));
    }

    const { receipt } = await pending;
    expect(receipt.confirmations).to.be.greaterThanOrEqual(3);
  }).timeout(60000);

  it("rejects empty bytecode and bad confirmation counts", async () => {
    const client = sdk();
    const art = await ethers.getContractFactory("AgentToken");
    await expect(client.deployContract([], "0x", [])).to.be.rejectedWith("bytecode is required");
    await expect(
      client.deployContract(art.interface.fragments, art.bytecode, ["a", "b", 1n], {
        confirmations: 0,
      }),
    ).to.be.rejectedWith("confirmations must be >= 1");
  });
});
