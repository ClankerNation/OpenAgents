const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("TaskRouter gas relay", function () {
  let registry;
  let router;
  let creator;
  let agentOwner;
  let relayer;
  let agentId;

  async function signRelayCall(agentSigner, callData) {
    const agent = await agentSigner.getAddress();
    const nonce = await router.nonces(agent);
    const chainId = (await ethers.provider.getNetwork()).chainId;
    const digest = ethers.keccak256(
      ethers.AbiCoder.defaultAbiCoder().encode(
        ["address", "uint256", "address", "uint256", "bytes32"],
        [await router.getAddress(), chainId, agent, nonce, ethers.keccak256(callData)]
      )
    );

    return agentSigner.signMessage(ethers.getBytes(digest));
  }

  async function createOpenTask() {
    const latest = await ethers.provider.getBlock("latest");
    const deadline = BigInt(latest.timestamp + 3600);
    await router.connect(creator).createTask("meta-tx task", deadline, { value: ethers.parseEther("1") });
    return 0n;
  }

  beforeEach(async function () {
    [, creator, agentOwner, relayer] = await ethers.getSigners();

    const AgentRegistry = await ethers.getContractFactory("AgentRegistry");
    registry = await AgentRegistry.deploy(0);
    await registry.waitForDeployment();

    const TaskRouter = await ethers.getContractFactory("TaskRouter");
    router = await TaskRouter.deploy(await registry.getAddress(), 0);
    await router.waitForDeployment();

    const tx = await registry.connect(agentOwner).registerAgent("relay-agent", "https://agent.local");
    const receipt = await tx.wait();
    const parsed = receipt.logs
      .map((log) => {
        try {
          return registry.interface.parseLog(log);
        } catch (e) {
          return null;
        }
      })
      .find((entry) => entry && entry.name === "AgentRegistered");
    agentId = parsed.args.agentId;
  });

  it("executes agent actions through relayer and reimburses from stake", async function () {
    const taskId = await createOpenTask();
    await router.connect(agentOwner).depositStake({ value: ethers.parseEther("1") });

    const callData = router.interface.encodeFunctionData("assignTask", [taskId, agentId]);
    const signature = await signRelayCall(agentOwner, callData);

    const stakedBefore = await router.stakedBalances(await agentOwner.getAddress());
    const tx = await router.connect(relayer).executeOnBehalf(await agentOwner.getAddress(), callData, signature, {
      gasPrice: 1_000_000_000n,
    });
    const receipt = await tx.wait();

    const relayEvent = receipt.logs
      .map((log) => {
        try {
          return router.interface.parseLog(log);
        } catch (e) {
          return null;
        }
      })
      .find((entry) => entry && entry.name === "RelayedExecution");

    expect(relayEvent.args.reimbursement).to.be.gt(0n);

    const stakedAfter = await router.stakedBalances(await agentOwner.getAddress());
    expect(stakedBefore - stakedAfter).to.equal(relayEvent.args.reimbursement);

    const task = await router.tasks(taskId);
    expect(task.status).to.equal(1n);
    expect(task.assignedAgent).to.equal(agentId);
  });

  it("rejects replayed signed payloads via nonce", async function () {
    const taskId = await createOpenTask();
    await router.connect(agentOwner).depositStake({ value: ethers.parseEther("1") });

    const callData = router.interface.encodeFunctionData("assignTask", [taskId, agentId]);
    const signature = await signRelayCall(agentOwner, callData);

    await router.connect(relayer).executeOnBehalf(await agentOwner.getAddress(), callData, signature, {
      gasPrice: 1_000_000_000n,
    });

    await expect(
      router.connect(relayer).executeOnBehalf(await agentOwner.getAddress(), callData, signature, {
        gasPrice: 1_000_000_000n,
      })
    ).to.be.revertedWith("Invalid signature");
  });

  it("reverts when agent stake cannot cover relay reimbursement", async function () {
    const taskId = await createOpenTask();
    await router.connect(agentOwner).depositStake({ value: 1n });

    const callData = router.interface.encodeFunctionData("assignTask", [taskId, agentId]);
    const signature = await signRelayCall(agentOwner, callData);

    await expect(
      router.connect(relayer).executeOnBehalf(await agentOwner.getAddress(), callData, signature, {
        gasPrice: 1_000_000_000n,
      })
    ).to.be.revertedWith("Insufficient stake for gas");
  });
});
