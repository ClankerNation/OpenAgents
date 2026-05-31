const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("TaskRouter relay", function () {
  let registry;
  let router;
  let creator;
  let agentOwner;
  let relayer;
  let agentId;

  async function signRelayCall(agentSigner, agentAddress, nonce, data) {
    const network = await ethers.provider.getNetwork();
    const encoded = ethers.AbiCoder.defaultAbiCoder().encode(
      ["address", "uint256", "address", "uint256", "bytes32"],
      [router.target, network.chainId, agentAddress, nonce, ethers.keccak256(data)]
    );
    const relayHash = ethers.keccak256(encoded);

    return agentSigner.signMessage(ethers.getBytes(relayHash));
  }

  beforeEach(async function () {
    [creator, agentOwner, relayer] = await ethers.getSigners();

    const AgentRegistry = await ethers.getContractFactory("AgentRegistry");
    registry = await AgentRegistry.deploy(0);
    await registry.waitForDeployment();

    const TaskRouter = await ethers.getContractFactory("TaskRouter");
    router = await TaskRouter.deploy(registry.target, 0);
    await router.waitForDeployment();

    const tx = await registry.connect(agentOwner).registerAgent("agent-1", "https://agent.local", { value: 0 });
    const receipt = await tx.wait();
    const evt = receipt.logs.find((log) => log.fragment && log.fragment.name === "AgentRegistered");
    agentId = evt.args.agentId;

    const latest = await ethers.provider.getBlock("latest");
    const deadline = Number(latest.timestamp) + 3600;
    await router.connect(creator).createTask("relay task", deadline, { value: ethers.parseEther("1") });
  });

  it("supports sponsored execution and reimburses relayer", async function () {
    await router.connect(agentOwner).depositStake({ value: ethers.parseEther("1") });

    const data = router.interface.encodeFunctionData("assignTask", [0n, agentId]);
    const nonce = await router.nonces(agentOwner.address);
    const signature = await signRelayCall(agentOwner, agentOwner.address, nonce, data);

    const stakeBefore = await router.stakeBalances(agentOwner.address);
    const relayerBalanceBefore = await ethers.provider.getBalance(relayer.address);

    const tx = await router.connect(relayer).executeOnBehalf(agentOwner.address, data, signature);
    const receipt = await tx.wait();

    const relayerBalanceAfter = await ethers.provider.getBalance(relayer.address);
    const stakeAfter = await router.stakeBalances(agentOwner.address);
    const task = await router.tasks(0);

    const relayEvent = receipt.logs.find((log) => log.fragment && log.fragment.name === "RelayExecuted");
    expect(relayEvent).to.not.equal(undefined);

    const reimbursement = relayEvent.args.reimbursement;
    const gasPaid = receipt.gasUsed * receipt.gasPrice;
    const expectedRelayerAfter = relayerBalanceBefore - gasPaid + reimbursement;

    expect(task.status).to.equal(1n);
    expect(task.assignedAgent).to.equal(agentId);
    expect(reimbursement).to.be.gt(0n);
    expect(stakeBefore - stakeAfter).to.equal(reimbursement);
    expect(relayerBalanceAfter).to.equal(expectedRelayerAfter);
  });

  it("prevents replay with nonce-based signature checks", async function () {
    await router.connect(agentOwner).depositStake({ value: ethers.parseEther("1") });

    const data = router.interface.encodeFunctionData("assignTask", [0n, agentId]);
    const nonce = await router.nonces(agentOwner.address);
    const signature = await signRelayCall(agentOwner, agentOwner.address, nonce, data);

    await router.connect(relayer).executeOnBehalf(agentOwner.address, data, signature);

    await expect(
      router.connect(relayer).executeOnBehalf(agentOwner.address, data, signature)
    ).to.be.revertedWith("Invalid signature");
  });

  it("reverts when sponsored account stake cannot cover gas reimbursement", async function () {
    const data = router.interface.encodeFunctionData("assignTask", [0n, agentId]);
    const nonce = await router.nonces(agentOwner.address);
    const signature = await signRelayCall(agentOwner, agentOwner.address, nonce, data);

    await expect(
      router.connect(relayer).executeOnBehalf(agentOwner.address, data, signature)
    ).to.be.revertedWith("Insufficient stake");

    const task = await router.tasks(0);
    expect(task.status).to.equal(0n);
  });
});
