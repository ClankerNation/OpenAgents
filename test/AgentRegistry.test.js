const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("AgentRegistry batchRegister", function () {
  let registry, owner, user;

  beforeEach(async function () {
    [owner, user] = await ethers.getSigners();
    const AgentRegistry = await ethers.getContractFactory("AgentRegistry");
    registry = await AgentRegistry.deploy(ethers.parseEther("0.01"));
  });

  it("should register multiple agents in one tx", async function () {
    const names = ["Agent1", "Agent2", "Agent3"];
    const endpoints = ["http://a1.com", "http://a2.com", "http://a3.com"];
    const fee = ethers.parseEther("0.01") * 3n;

    const tx = await registry.connect(user).batchRegister(names, endpoints, { value: fee });
    const receipt = await tx.wait();

    // Should emit 3 AgentRegistered events
    const events = receipt.logs.filter(
      log => log.fragment && log.fragment.name === "AgentRegistered"
    );
    expect(events.length).to.equal(3);
  });

  it("should revert if array lengths mismatch", async function () {
    const names = ["Agent1"];
    const endpoints = ["http://a1.com", "http://a2.com"];
    const fee = ethers.parseEther("0.01");

    await expect(
      registry.connect(user).batchRegister(names, endpoints, { value: fee })
    ).to.be.revertedWith("Array length mismatch");
  });

  it("should revert if batch size > 50", async function () {
    const names = Array(51).fill("Agent");
    const endpoints = Array(51).fill("http://a.com");
    const fee = ethers.parseEther("0.01") * 51n;

    await expect(
      registry.connect(user).batchRegister(names, endpoints, { value: fee })
    ).to.be.revertedWith("Batch size must be 1-50");
  });

  it("should revert if total fee insufficient", async function () {
    const names = ["Agent1", "Agent2"];
    const endpoints = ["http://a1.com", "http://a2.com"];
    const fee = ethers.parseEther("0.001"); // Too low

    await expect(
      registry.connect(user).batchRegister(names, endpoints, { value: fee })
    ).to.be.revertedWith("Insufficient total fee");
  });
});
