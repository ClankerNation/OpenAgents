const { expect } = require("chai");
const { ethers } = require("hardhat");

const EXECUTE_TYPES = {
  ExecuteOnBehalf: [
    { name: "agent", type: "address" },
    { name: "data", type: "bytes" },
    { name: "nonce", type: "uint256" },
  ],
};

describe("TaskRouter gas sponsorship relay", function () {
  let registry;
  let router;
  let creator;
  let agent;
  let relayer;
  let outsider;
  let agentId;

  async function domain() {
    const network = await ethers.provider.getNetwork();
    return {
      name: "TaskRouter",
      version: "1",
      chainId: network.chainId,
      verifyingContract: await router.getAddress(),
    };
  }

  async function signExecute(signer, data, nonce) {
    return signer.signTypedData(await domain(), EXECUTE_TYPES, {
      agent: signer.address,
      data,
      nonce,
    });
  }

  async function createOpenTask(reward = ethers.parseEther("1")) {
    const deadline = BigInt((await ethers.provider.getBlock("latest")).timestamp) + 3600n;
    const tx = await router.connect(creator).createTask("index docs", deadline, { value: reward });
    await tx.wait();
    return (await router.taskCount()) - 1n;
  }

  beforeEach(async function () {
    [creator, agent, relayer, outsider] = await ethers.getSigners();

    const AgentRegistry = await ethers.getContractFactory("AgentRegistry");
    registry = await AgentRegistry.deploy(0);
    await registry.waitForDeployment();

    const TaskRouter = await ethers.getContractFactory("TaskRouter");
    router = await TaskRouter.deploy(await registry.getAddress(), 250);
    await router.waitForDeployment();

    const tx = await registry.connect(agent).registerAgent("indexer", "https://agent.example");
    const receipt = await tx.wait();
    const registered = receipt.logs
      .map((log) => {
        try {
          return registry.interface.parseLog(log);
        } catch {
          return null;
        }
      })
      .find((parsed) => parsed && parsed.name === "AgentRegistered");
    agentId = registered.args.agentId;

    await router.connect(agent).stake({ value: ethers.parseEther("2") });
  });

  it("lets an agent submit task actions without holding ETH (sponsored execution)", async function () {
    const taskId = await createOpenTask();

    const data = router.interface.encodeFunctionData("assignTask", [taskId, agentId]);
    const nonce = await router.nonces(agent.address);
    const signature = await signExecute(agent, data, nonce);

    const relayerBefore = await ethers.provider.getBalance(relayer.address);
    const stakeBefore = await router.stakedBalance(agent.address);

    const exec = await router.connect(relayer).executeOnBehalf(agent.address, data, signature);
    const receipt = await exec.wait();

    const task = await router.tasks(taskId);
    expect(task.status).to.equal(1n); // Assigned
    expect(task.assignedAgent).to.equal(agentId);
    expect(await router.nonces(agent.address)).to.equal(nonce + 1n);

    const stakeAfter = await router.stakedBalance(agent.address);
    const reimbursement = stakeBefore - stakeAfter;
    expect(reimbursement).to.be.gt(0n);

    const relayerAfter = await ethers.provider.getBalance(relayer.address);
    const gasPaid = receipt.gasUsed * receipt.gasPrice;
    expect(relayerAfter).to.equal(relayerBefore - gasPaid + reimbursement);

    const reimbursed = receipt.logs.find(
      (log) => log.fragment && log.fragment.name === "RelayerReimbursed"
    );
    expect(reimbursed.args.relayer).to.equal(relayer.address);
    expect(reimbursed.args.amount).to.equal(reimbursement);
  });

  it("reimburses the relayer from agent stake on sponsored createTask", async function () {
    const deadline = BigInt((await ethers.provider.getBlock("latest")).timestamp) + 3600n;
    const reward = ethers.parseEther("0.5");
    const data = router.interface.encodeFunctionData("createTask", ["summarize", deadline]);
    const nonce = await router.nonces(agent.address);
    const signature = await signExecute(agent, data, nonce);

    const stakeBefore = await router.stakedBalance(agent.address);
    await router
      .connect(relayer)
      .executeOnBehalf(agent.address, data, signature, { value: reward });

    const taskId = (await router.taskCount()) - 1n;
    const task = await router.tasks(taskId);
    expect(task.creator).to.equal(agent.address);
    expect(task.reward).to.equal(reward);
    expect(await router.stakedBalance(agent.address)).to.be.lt(stakeBefore);
  });

  it("pays task completion to the agent, not the relayer", async function () {
    const reward = ethers.parseEther("1");
    const taskId = await createOpenTask(reward);

    const assignData = router.interface.encodeFunctionData("assignTask", [taskId, agentId]);
    await router
      .connect(relayer)
      .executeOnBehalf(
        agent.address,
        assignData,
        await signExecute(agent, assignData, await router.nonces(agent.address))
      );

    const completeData = router.interface.encodeFunctionData("completeTask", [
      taskId,
      ethers.hexlify(ethers.toUtf8Bytes("done")),
    ]);
    const agentBefore = await ethers.provider.getBalance(agent.address);

    await router
      .connect(relayer)
      .executeOnBehalf(
        agent.address,
        completeData,
        await signExecute(agent, completeData, await router.nonces(agent.address))
      );

    const fee = (reward * 250n) / 10000n;
    const agentAfter = await ethers.provider.getBalance(agent.address);
    expect(agentAfter - agentBefore).to.equal(reward - fee);
  });

  it("rejects replayed signatures", async function () {
    const taskId = await createOpenTask();
    const data = router.interface.encodeFunctionData("assignTask", [taskId, agentId]);
    const nonce = await router.nonces(agent.address);
    const signature = await signExecute(agent, data, nonce);

    await router.connect(relayer).executeOnBehalf(agent.address, data, signature);

    await expect(
      router.connect(relayer).executeOnBehalf(agent.address, data, signature)
    ).to.be.revertedWith("Invalid signature");
  });

  it("rejects signatures that do not match the agent address", async function () {
    const taskId = await createOpenTask();
    const data = router.interface.encodeFunctionData("assignTask", [taskId, agentId]);
    const nonce = await router.nonces(agent.address);
    const signature = await signExecute(outsider, data, nonce);

    await expect(
      router.connect(relayer).executeOnBehalf(agent.address, data, signature)
    ).to.be.revertedWith("Invalid signature");
  });

  it("reverts when agent stake cannot cover relayer reimbursement", async function () {
    await router.connect(agent).unstake(await router.stakedBalance(agent.address));
    await router.connect(agent).stake({ value: 1n });

    const taskId = await createOpenTask();
    const data = router.interface.encodeFunctionData("assignTask", [taskId, agentId]);
    const signature = await signExecute(agent, data, await router.nonces(agent.address));

    await expect(
      router.connect(relayer).executeOnBehalf(agent.address, data, signature)
    ).to.be.revertedWith("Insufficient stake");

    const task = await router.tasks(taskId);
    expect(task.status).to.equal(0n); // Open — inner assign rolled back
    expect(await router.nonces(agent.address)).to.equal(0n);
  });

  it("still allows direct (non-sponsored) calls from the agent", async function () {
    const taskId = await createOpenTask();
    await router.connect(agent).assignTask(taskId, agentId);
    const task = await router.tasks(taskId);
    expect(task.status).to.equal(1n);
  });
});
