const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("TaskRouter Gas Sponsorship", function () {
  let taskRouter, agentRegistry;
  let owner, agent, relayer;

  beforeEach(async function () {
    [owner, agent, relayer] = await ethers.getSigners();

    const AgentRegistry = await ethers.getContractFactory("AgentRegistry");
    agentRegistry = await AgentRegistry.deploy(0);
    await agentRegistry.deployed();

    const TaskRouter = await ethers.getContractFactory("TaskRouter");
    taskRouter = await TaskRouter.deploy(agentRegistry.target, 0);
    await taskRouter.deployed();

    // Register agent
    await agentRegistry.registerAgent("Test Agent", "http://example.com", {
      value: ethers.parseEther("0.1"),
    });
  });

  it("should allow agent to stake ETH", async function () {
    const amount = ethers.parseEther("1");
    await taskRouter.connect(agent).stake({ value: amount });
    expect(await taskRouter.stakes(agent)).to.equal(amount);
  });

  it("should execute sponsored transaction and reimburse relayer", async function () {
    // Agent stakes ETH
    const stakeAmount = ethers.parseEther("1");
    await taskRouter.connect(agent).stake({ value: stakeAmount });

    // Get nonce and build hash
    const nonce = await taskRouter.nonces(agent);
    const data = ethers.solidityPackedKeccak256(["string"], ["test"]);
    const hash = ethers.solidityPackedKeccak256(
      ["address", "bytes", "uint256"],
      [agent, data, nonce]
    );

    // Agent signs the hash
    const signature = await agent.signMessage(ethers.getBytes(hash));

    // Record relayer balance before
    const relayerBalanceBefore = await ethers.provider.getBalance(relayer);

    // Relayer executes on behalf of agent
    const tx = await taskRouter
      .connect(relayer)
      .executeOnBehalf(agent, data, signature, {
        gasLimit: 500000,
      });

    const receipt = await tx.wait();
    const gasUsed = receipt.gasUsed;
    const txCost = gasUsed * (receipt.gasPrice || 0);

    // Nonce should be incremented
    expect(await taskRouter.nonces(agent)).to.equal(nonce + 1);

    // Agent stake should be reduced by gas cost
    expect(await taskRouter.stakes(agent)).to.be.lt(stakeAmount);

    // Relayer should be reimbursed (balance should not decrease by full gas cost)
    const relayerBalanceAfter = await ethers.provider.getBalance(relayer);
    expect(relayerBalanceAfter).to.be.gt(
      relayerBalanceBefore - txCost - 1000000000000000n
    );
  });

  it("should prevent replay attacks via nonce tracking", async function () {
    // Agent stakes ETH
    const stakeAmount = ethers.parseEther("1");
    await taskRouter.connect(agent).stake({ value: stakeAmount });

    // Get nonce and build hash
    const nonce = await taskRouter.nonces(agent);
    const data = ethers.solidityPackedKeccak256(["string"], ["test"]);
    const hash = ethers.solidityPackedKeccak256(
      ["address", "bytes", "uint256"],
      [agent, data, nonce]
    );

    // Agent signs the hash
    const signature = await agent.signMessage(ethers.getBytes(hash));

    // First execution succeeds
    await taskRouter.connect(relayer).executeOnBehalf(agent, data, signature);

    // Second execution with same signature should fail (nonce already consumed)
    await expect(
      taskRouter.connect(relayer).executeOnBehalf(agent, data, signature)
    ).to.be.reverted;
  });

  it("should reject execution when agent has insufficient stake", async function () {
    // Agent has no stake
    const data = ethers.solidityPackedKeccak256(["string"], ["test"]);
    const nonce = await taskRouter.nonces(agent);
    const hash = ethers.solidityPackedKeccak256(
      ["address", "bytes", "uint256"],
      [agent, data, nonce]
    );
    const signature = await agent.signMessage(ethers.getBytes(hash));

    await expect(
      taskRouter.connect(relayer).executeOnBehalf(agent, data, signature)
    ).to.be.revertedWith("Insufficient stake");
  });

  it("should reject invalid signature", async function () {
    // Agent stakes ETH
    await taskRouter.connect(agent).stake({ value: ethers.parseEther("1") });

    const data = ethers.solidityPackedKeccak256(["string"], ["test"]);
    const nonce = await taskRouter.nonces(agent);
    const hash = ethers.solidityPackedKeccak256(
      ["address", "bytes", "uint256"],
      [agent, data, nonce]
    );

    // Wrong signer (relayer signs instead of agent)
    const signature = await relayer.signMessage(ethers.getBytes(hash));

    await expect(
      taskRouter.connect(relayer).executeOnBehalf(agent, data, signature)
    ).to.be.reverted;
  });
});
