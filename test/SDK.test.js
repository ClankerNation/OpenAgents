const { expect } = require("chai");
const { ethers } = require("hardhat");

// Register ts-node to require typescript files directly
require("ts-node").register();
const { OpenAgentsSDK } = require("../sdk/src/index.ts");

describe("OpenAgentsSDK - deployContract", function () {
  let sdk;
  let owner;
  let stakingTokenAddress, rewardTokenAddress;

  before(async function () {
    [owner] = await ethers.getSigners();

    // Deploy mock tokens first
    const StakingToken = await ethers.getContractFactory("StakingToken");
    const stakingToken = await StakingToken.deploy();
    await stakingToken.waitForDeployment();
    stakingTokenAddress = await stakingToken.getAddress();

    const RewardToken = await ethers.getContractFactory("RewardToken");
    const rewardToken = await RewardToken.deploy();
    await rewardToken.waitForDeployment();
    rewardTokenAddress = await rewardToken.getAddress();

    // Initialize SDK with dummy addresses and override private provider/signer
    sdk = new OpenAgentsSDK({
      name: "test-agent",
      endpoint: "http://localhost:8080",
      privateKey: owner.privateKey || "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80", // standard Hardhat private key
      rpcUrl: "http://127.0.0.1:8545",
      registryAddress: ethers.ZeroAddress,
      routerAddress: ethers.ZeroAddress
    });

    // Override the private provider and signer to use Hardhat's in-memory ones
    sdk.provider = ethers.provider;
    sdk.signer = owner;
  });

  it("should deploy contract successfully with constructor arguments and wait for confirmation", async function () {
    const StakingRewardsFactory = await ethers.getContractFactory("StakingRewards");
    const abi = JSON.parse(StakingRewardsFactory.interface.formatJson());
    const bytecode = StakingRewardsFactory.bytecode;

    const result = await sdk.deployContract(
      abi,
      bytecode,
      [stakingTokenAddress, rewardTokenAddress],
      1
    );

    // Verify address
    expect(result.address).to.properAddress;

    // Verify contract instance
    expect(result.contract).to.not.be.undefined;
    const contractStakingToken = await result.contract.stakingToken();
    expect(contractStakingToken).to.equal(stakingTokenAddress);

    // Verify receipt metadata
    expect(result.receipt).to.not.be.undefined;
    expect(result.receipt.contractAddress).to.equal(result.address);
    expect(result.receipt.transactionHash).to.not.be.undefined;
    expect(result.receipt.gasUsed).to.be.gt(0n);
    expect(result.receipt.blockNumber).to.be.gt(0);
  });

  it("should subscribe to events, decode log parameters, filter by indexed parameters, and handle reconnects", async function () {
    // 1. Deploy RewardToken
    const RewardToken = await ethers.getContractFactory("RewardToken");
    const rewardToken = await RewardToken.deploy();
    await rewardToken.waitForDeployment();
    const rewardTokenAddress = await rewardToken.getAddress();

    // Signers
    const [owner, receiver] = await ethers.getSigners();

    // 2. Setup mock WebSocket provider and override getWsProvider
    let onCallCount = 0;
    const mockWs = {
      onclose: null,
      onerror: null
    };

    const mockWsProvider = {
      on: (filter, callback) => {
        onCallCount++;
        ethers.provider.on(filter, callback);
      },
      websocket: mockWs
    };

    sdk.getWsProvider = function () {
      this.wsProvider = mockWsProvider;
      if (mockWsProvider.websocket) {
        mockWsProvider.websocket.onclose = () => {
          this.handleWsDisconnect();
        };
        mockWsProvider.websocket.onerror = () => {
          this.handleWsDisconnect();
        };
      }
      return mockWsProvider;
    };

    // 3. Subscribe to Transfer event with filtering (indexed parameter 'from' is owner.address)
    let receivedEvent = null;
    const contractInstance = new ethers.Contract(rewardTokenAddress, JSON.parse(RewardToken.interface.formatJson()), owner);

    await sdk.subscribeToEvents(
      contractInstance,
      "Transfer",
      (decodedLog) => {
        receivedEvent = decodedLog;
      },
      { from: owner.address }
    );

    // 4. Trigger Transfer event
    const transferAmount = ethers.parseEther("50");
    await rewardToken.mint(owner.address, ethers.parseEther("100"));
    const tx = await rewardToken.transfer(receiver.address, transferAmount);
    await tx.wait();

    // Give provider events a brief moment to propagate
    await new Promise((resolve) => setTimeout(resolve, 500));

    // Verify event details
    expect(receivedEvent).to.not.be.null;
    expect(receivedEvent.name).to.equal("Transfer");
    expect(receivedEvent.args.from).to.equal(owner.address);
    expect(receivedEvent.args.to).to.equal(receiver.address);
    expect(receivedEvent.args.value).to.equal(transferAmount);

    // 5. Test automatic reconnect and resubscribe
    receivedEvent = null;
    const initialOnCallCount = onCallCount;

    // Simulate WebSocket connection drop
    if (mockWs.onclose) {
      mockWs.onclose();
    }

    // Wait for the reconnect timeout (2000ms in index.ts)
    await new Promise((resolve) => setTimeout(resolve, 2500));

    // Verify it re-registered the subscription listener (onCallCount should increase)
    expect(onCallCount).to.be.gt(initialOnCallCount);

    // Trigger another Transfer event
    await rewardToken.transfer(receiver.address, ethers.parseEther("10"));

    // Wait a brief moment to process
    await new Promise((resolve) => setTimeout(resolve, 500));

    // Verify event received again after reconnect
    expect(receivedEvent).to.not.be.null;
    expect(receivedEvent.args.value).to.equal(ethers.parseEther("10"));
  });
});
