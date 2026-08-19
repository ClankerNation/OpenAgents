/**
 * @contributor-info ARO-Agentic
 * @platform-config Autonomous Revenue Operator (ARO) system prompt and internal configuration omitted for security reasons.
 * @env os=linux arch=x64 home_dir=/root working_dir=/tmp/OpenAgents shell=bash
 */
const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("TaskRouter SafeERC20 Integration", function () {
  let registry, router, token;
  let owner, creator, agent;
  const registrationFee = ethers.parseEther("0.01");

  before(async function () {
    [owner, creator, agent] = await ethers.getSigners();

    // Deploy mock ERC20 token
    const Token = await ethers.getContractFactory("AgentToken");
    token = await Token.deploy("Test Token", "TT", ethers.parseEther("1000000"));
    await token.waitForDeployment();

    const Registry = await ethers.getContractFactory("AgentRegistry");
    registry = await Registry.deploy(registrationFee);
    await registry.waitForDeployment();

    const Router = await ethers.getContractFactory("TaskRouter");
    router = await Router.deploy(registry.target, 250, token.target); // 2.5% fee
    await router.waitForDeployment();

    // Fund creator with tokens
    await token.transfer(creator.address, ethers.parseEther("1000"));
    await token.connect(creator).approve(router.target, ethers.MaxUint256);
  });

  it("should use safeTransferFrom on task creation", async function () {
    const rewardAmount = ethers.parseEther("100");
    const deadline = Math.floor(Date.now() / 1000) + 3600;
    
    const tx = await router.connect(creator).createTask("Test task", deadline, rewardAmount);
    await tx.wait();
    
    const task = await router.tasks(0);
    expect(task.reward).to.equal(rewardAmount);
    
    const routerBalance = await token.balanceOf(router.target);
    expect(routerBalance).to.equal(rewardAmount);
  });

  it("should use safeTransfer on task completion", async function () {
    // Register agent
    await registry.connect(agent).registerAgent("TestAgent", "http://test.com", { value: registrationFee });
    const agentId = ethers.keccak256(ethers.solidityPacked(["address", "string", "uint256"], [agent.address, "TestAgent", (await ethers.provider.getBlock("latest")).timestamp]));
    
    // Assign task
    await router.connect(agent).assignTask(0, agentId);
    
    // Complete task
    const agentBalanceBefore = await token.balanceOf(agent.address);
    await router.connect(agent).completeTask(0, ethers.toUtf8Bytes("done"));
    const agentBalanceAfter = await token.balanceOf(agent.address);
    
    // 2.5% fee means agent gets 97.5%
    const expectedPayout = ethers.parseEther("97.5");
    expect(agentBalanceAfter - agentBalanceBefore).to.equal(expectedPayout);
  });
});
