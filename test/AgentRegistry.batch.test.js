const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("AgentRegistry - batchRegister", function () {
  let registry;
  let owner, user;
  const fee = ethers.parseEther("0.01");

  beforeEach(async function () {
    [owner, user] = await ethers.getSigners();
    const Registry = await ethers.getContractFactory("AgentRegistry");
    registry = await Registry.deploy(fee);
    await registry.waitForDeployment();
  });

  it("registers a batch of agents in one transaction", async function () {
    const names = ["Agent1", "Agent2", "Agent3"];
    const endpoints = ["https://agent1.com", "https://agent2.com", "https://agent3.com"];
    const totalFee = fee * 3n;

    const tx = await registry.connect(user).batchRegister(names, endpoints, { value: totalFee });
    const receipt = await tx.wait();

    expect(receipt.logs.length).to.equal(3);
  });

  it("registers up to 50 agents", async function () {
    const names = [];
    const endpoints = [];
    for (let i = 0; i < 50; i++) {
      names.push(`Agent${i}`);
      endpoints.push(`https://agent${i}.com`);
    }
    const totalFee = fee * 50n;

    const tx = await registry.connect(user).batchRegister(names, endpoints, { value: totalFee });
    const receipt = await tx.wait();

    expect(receipt.logs.length).to.equal(50);
  });

  it("reverts on array length mismatch", async function () {
    const names = ["Agent1", "Agent2"];
    const endpoints = ["https://agent1.com"];
    const totalFee = fee * 2n;

    await expect(
      registry.connect(user).batchRegister(names, endpoints, { value: totalFee })
    ).to.be.revertedWith("Array length mismatch");
  });

  it("reverts on insufficient fee", async function () {
    const names = ["Agent1", "Agent2"];
    const endpoints = ["https://agent1.com", "https://agent2.com"];
    const insufficientFee = fee;

    await expect(
      registry.connect(user).batchRegister(names, endpoints, { value: insufficientFee })
    ).to.be.revertedWith("Insufficient fee");
  });

  it("reverts on invalid batch size", async function () {
    const names = [];
    const endpoints = [];
    const totalFee = 0n;

    await expect(
      registry.connect(user).batchRegister(names, endpoints, { value: totalFee })
    ).to.be.revertedWith("Invalid batch size");
  });

  it("emits individual events per registration", async function () {
    const names = ["Alpha", "Beta"];
    const endpoints = ["https://alpha.com", "https://beta.com"];
    const totalFee = fee * 2n;

    await expect(
      registry.connect(user).batchRegister(names, endpoints, { value: totalFee })
    ).to.emit(registry, "AgentRegistered");
  });
});
