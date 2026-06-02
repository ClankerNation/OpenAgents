const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("TaskRouter V2 Upgrade", function () {
    let registry;
    let router;
    let badToken;
    let owner;
    let creator;
    let agentOwner;
    let agentId;
    const platformFee = 500; // 5%

    beforeEach(async function () {
        [owner, creator, agentOwner] = await ethers.getSigners();

        const Registry = await ethers.getContractFactory("AgentRegistry");
        registry = await Registry.deploy(0);

        const Router = await ethers.getContractFactory("TaskRouter");
        router = await Router.deploy(await registry.getAddress(), platformFee);

        const BadToken = await ethers.getContractFactory("MockERC20Bad");
        badToken = await BadToken.deploy();

        // Mint tokens to creator
        await badToken.mint(creator.address, ethers.parseEther("1000"));

        // Register agent
        const tx = await registry.connect(agentOwner).registerAgent("Agent 1", "url");
        const receipt = await tx.wait();
        const event = receipt.logs.find(log => log.fragment && log.fragment.name === 'AgentRegistered');
        agentId = event.args[0];
    });

    it("should revert if token.transfer returns false on completeTask", async function () {
        // Setup task
        const reward = ethers.parseEther("100");
        const deadline = Math.floor(Date.now() / 1000) + 3600;
        
        await badToken.connect(creator).approve(await router.getAddress(), reward);
        
        await router.connect(creator).createTaskERC20("Test task", deadline, reward, await badToken.getAddress());
        const taskId = 0; // taskCount starts at 0


        await router.connect(agentOwner).assignTask(taskId, agentId);

        // Force token transfer to return false
        await badToken.setForceFail(true);

        // completeTask should revert because SafeERC20 throws on false return value
        await expect(
            router.connect(agentOwner).completeTask(taskId, "0x1234")
        ).to.be.reverted;
    });

    it("should successfully payout ERC20 on completeTask if token transfer succeeds", async function () {
        const reward = ethers.parseEther("100");
        const deadline = Math.floor(Date.now() / 1000) + 3600;
        
        await badToken.connect(creator).approve(await router.getAddress(), reward);
        await router.connect(creator).createTaskERC20("Test task", deadline, reward, await badToken.getAddress());
        const taskId = 0;


        await router.connect(agentOwner).assignTask(taskId, agentId);

        // Set to normal behavior (forceFail = false)
        await badToken.setForceFail(false);

        await router.connect(agentOwner).completeTask(taskId, "0x1234");
        
        const fee = (reward * BigInt(platformFee)) / 10000n;
        const payout = reward - fee;

        expect(await badToken.balanceOf(agentOwner.address)).to.equal(payout);
    });
});
