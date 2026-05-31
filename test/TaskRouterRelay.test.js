const { expect } = require("chai");
const { ethers } = require("hardhat");

async function signRelayCall(agentSigner, router, agentAddress, nonce, data) {
  const { chainId } = await ethers.provider.getNetwork();
  const encoded = ethers.AbiCoder.defaultAbiCoder().encode(
    ["address", "uint256", "address", "uint256", "bytes32"],
    [router.target, chainId, agentAddress, nonce, ethers.keccak256(data)]
  );
  const messageHash = ethers.keccak256(encoded);
  return agentSigner.signMessage(ethers.getBytes(messageHash));
}

describe("TaskRouter relay sponsorship", function () {
  let registry;
  let router;
  let creator;
  let agentOwner;
  let relayer;
  let agentId;
  const taskId = 0n;

  beforeEach(async function () {
    [creator, agentOwner, relayer] = await ethers.getSigners();

    const Registry = await ethers.getContractFactory("AgentRegistry");
    registry = await Registry.deploy(0);

    const Router = await ethers.getContractFactory("TaskRouter");
    router = await Router.deploy(registry.target, 500);

    const latestBlock = await ethers.provider.getBlock("latest");
    const deadline = BigInt(latestBlock.timestamp + 3600);

    await router.connect(creator).createTask("relay completion", deadline, {
      value: ethers.parseEther("1"),
    });

    const registerTx = await registry
      .connect(agentOwner)
      .registerAgent("relay-agent", "https://agent.local", { value: 0 });
    const receipt = await registerTx.wait();
    for (const log of receipt.logs) {
      try {
        const parsed = registry.interface.parseLog(log);
        if (parsed && parsed.name === "AgentRegistered") {
          agentId = parsed.args.agentId;
          break;
        }
      } catch (_) {}
    }

    await router.connect(agentOwner).assignTask(taskId, agentId);
  });

  it("executes sponsored completion and reimburses relayer from agent stake", async function () {
    await router.connect(agentOwner).depositStake({ value: ethers.parseEther("1") });

    const data = router.interface.encodeFunctionData("completeTask", [
      taskId,
      ethers.toUtf8Bytes("done"),
    ]);
    const nonce = await router.nonces(agentOwner.address);
    const signature = await signRelayCall(
      agentOwner,
      router,
      agentOwner.address,
      nonce,
      data
    );

    const stakeBefore = await router.stakeBalances(agentOwner.address);
    const relayerBalanceBefore = await ethers.provider.getBalance(relayer.address);

    const tx = await router
      .connect(relayer)
      .executeOnBehalf(agentOwner.address, data, signature);
    const receipt = await tx.wait();

    const stakeAfter = await router.stakeBalances(agentOwner.address);
    const relayerBalanceAfter = await ethers.provider.getBalance(relayer.address);

    let reimbursement = 0n;
    for (const log of receipt.logs) {
      try {
        const parsed = router.interface.parseLog(log);
        if (parsed && parsed.name === "RelayExecuted") {
          reimbursement = parsed.args.reimbursement;
          break;
        }
      } catch (_) {}
    }

    const task = await router.tasks(taskId);

    expect(task.status).to.equal(2n); // Completed
    expect(reimbursement).to.be.gt(0n);
    expect(stakeBefore - stakeAfter).to.equal(reimbursement);
    expect(relayerBalanceAfter).to.equal(relayerBalanceBefore - receipt.fee + reimbursement);
  });

  it("prevents replay with nonce-based signature checks", async function () {
    await router.connect(agentOwner).depositStake({ value: ethers.parseEther("1") });

    const data = router.interface.encodeFunctionData("completeTask", [
      taskId,
      ethers.toUtf8Bytes("done"),
    ]);
    const nonce = await router.nonces(agentOwner.address);
    const signature = await signRelayCall(
      agentOwner,
      router,
      agentOwner.address,
      nonce,
      data
    );

    await router
      .connect(relayer)
      .executeOnBehalf(agentOwner.address, data, signature);

    await expect(
      router.connect(relayer).executeOnBehalf(agentOwner.address, data, signature)
    ).to.be.revertedWith("Invalid signature");
  });

  it("reverts when stake cannot cover gas reimbursement", async function () {
    const data = router.interface.encodeFunctionData("completeTask", [
      taskId,
      ethers.toUtf8Bytes("done"),
    ]);
    const nonce = await router.nonces(agentOwner.address);
    const signature = await signRelayCall(
      agentOwner,
      router,
      agentOwner.address,
      nonce,
      data
    );

    await expect(
      router.connect(relayer).executeOnBehalf(agentOwner.address, data, signature)
    ).to.be.revertedWith("Insufficient stake");
  });
});
