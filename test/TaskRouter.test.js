const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("TaskRouter Gas Sponsorship & executeOnBehalf", function () {
  let agentRegistry, taskRouter;
  let owner, agentSigner, relayer, other;

  beforeEach(async function () {
    [owner, agentSigner, relayer, other] = await ethers.getSigners();

    const AgentRegistry = await ethers.getContractFactory("AgentRegistry");
    agentRegistry = await AgentRegistry.deploy(0);
    await agentRegistry.waitForDeployment();

    const TaskRouter = await ethers.getContractFactory("TaskRouter");
    taskRouter = await TaskRouter.deploy(await agentRegistry.getAddress(), 100);
    await taskRouter.waitForDeployment();
  });

  it("should allow staking and withdrawing stake", async function () {
    const depositAmount = ethers.parseEther("1.0");
    await taskRouter.connect(agentSigner).depositStake({ value: depositAmount });
    expect(await taskRouter.agentStakes(agentSigner.address)).to.equal(depositAmount);

    const withdrawAmount = ethers.parseEther("0.4");
    await taskRouter.connect(agentSigner).withdrawStake(withdrawAmount);
    expect(await taskRouter.agentStakes(agentSigner.address)).to.equal(depositAmount - withdrawAmount);
  });

  it("should execute task creation on behalf of agent with valid signature and reimburse relayer", async function () {
    const stakeAmount = ethers.parseEther("2.0");
    await taskRouter.connect(agentSigner).depositStake({ value: stakeAmount });

    const description = "Sponsored task";
    const deadline = Math.floor(Date.now() / 1000) + 3600;
    const reward = ethers.parseEther("0.5");

    // Encode createTask(string,uint256,uint256)
    const taskRouterInterface = taskRouter.interface;
    const innerCallData = taskRouterInterface.encodeFunctionData("createTask", [
      description,
      deadline,
      reward
    ]);

    const nonce = await taskRouter.nonces(agentSigner.address);
    const network = await ethers.provider.getNetwork();
    const chainId = network.chainId;

    // Hash matches contract: keccak256(abi.encodePacked(address(this), agent, data, nonce, chainId))
    const messageHash = ethers.solidityPackedKeccak256(
      ["address", "address", "bytes", "uint256", "uint256"],
      [await taskRouter.getAddress(), agentSigner.address, innerCallData, nonce, chainId]
    );

    const signature = await agentSigner.signMessage(ethers.getBytes(messageHash));

    // Relayer executes on behalf
    const tx = await taskRouter.connect(relayer).executeOnBehalf(
      agentSigner.address,
      innerCallData,
      signature
    );
    await tx.wait();

    // Verify task created
    const task = await taskRouter.tasks(0);
    expect(task.creator).to.equal(agentSigner.address);
    expect(task.reward).to.equal(reward);
    expect(await taskRouter.nonces(agentSigner.address)).to.equal(1n);
  });

  it("should fail on replay attack with same nonce", async function () {
    const stakeAmount = ethers.parseEther("2.0");
    await taskRouter.connect(agentSigner).depositStake({ value: stakeAmount });

    const description = "Replay test";
    const deadline = Math.floor(Date.now() / 1000) + 3600;
    const reward = ethers.parseEther("0.1");

    const taskRouterInterface = taskRouter.interface;
    const innerCallData = taskRouterInterface.encodeFunctionData("createTask", [
      description,
      deadline,
      reward
    ]);

    const nonce = await taskRouter.nonces(agentSigner.address);
    const network = await ethers.provider.getNetwork();
    const chainId = network.chainId;

    const messageHash = ethers.solidityPackedKeccak256(
      ["address", "address", "bytes", "uint256", "uint256"],
      [await taskRouter.getAddress(), agentSigner.address, innerCallData, nonce, chainId]
    );

    const signature = await agentSigner.signMessage(ethers.getBytes(messageHash));

    // First execution succeeds
    await taskRouter.connect(relayer).executeOnBehalf(
      agentSigner.address,
      innerCallData,
      signature
    );

    // Second execution with same signature/nonce should fail
    await expect(
      taskRouter.connect(relayer).executeOnBehalf(
        agentSigner.address,
        innerCallData,
        signature
      )
    ).to.be.revertedWith("Invalid signature");
  });

  it("should fail when agent has insufficient stake", async function () {
    // Zero stake
    const description = "No stake task";
    const deadline = Math.floor(Date.now() / 1000) + 3600;
    const reward = ethers.parseEther("0.1");

    const taskRouterInterface = taskRouter.interface;
    const innerCallData = taskRouterInterface.encodeFunctionData("createTask", [
      description,
      deadline,
      reward
    ]);

    const nonce = await taskRouter.nonces(agentSigner.address);
    const network = await ethers.provider.getNetwork();
    const chainId = network.chainId;

    const messageHash = ethers.solidityPackedKeccak256(
      ["address", "address", "bytes", "uint256", "uint256"],
      [await taskRouter.getAddress(), agentSigner.address, innerCallData, nonce, chainId]
    );

    const signature = await agentSigner.signMessage(ethers.getBytes(messageHash));

    await expect(
      taskRouter.connect(relayer).executeOnBehalf(
        agentSigner.address,
        innerCallData,
        signature
      )
    ).to.be.reverted;
  });
});
