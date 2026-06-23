const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("OpenAgentsSDK - Event Subscription", function () {
  let sdk, taskRouter, agentRegistry, owner, agent;

  const MOCK_CONFIG = {
    name: "test-agent",
    endpoint: "http://localhost:3000",
    privateKey: "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80",
    rpcUrl: "http://127.0.0.1:8545",
    registryAddress: "0x0",
    routerAddress: "0x0",
  };

  before(async function () {
    [owner, agent] = await ethers.getSigners();

    // Deploy AgentRegistry
    const AgentRegistry = await ethers.getContractFactory("AgentRegistry");
    agentRegistry = await AgentRegistry.deploy();
    await agentRegistry.deployed();

    // Register the agent
    await agentRegistry.registerAgent("test-agent", "http://localhost:3000", {
      value: await agentRegistry.registrationFee(),
    });

    // Deploy TaskRouter
    const TaskRouter = await ethers.getContractFactory("TaskRouter");
    taskRouter = await TaskRouter.deploy(agentRegistry.target, 100);
    await taskRouter.deployed();

    // Create SDK instance
    sdk = new (require("../../sdk/src/index").OpenAgentsSDK)({
      ...MOCK_CONFIG,
      registryAddress: agentRegistry.target,
      routerAddress: taskRouter.target,
    });
  });

  describe("subscribeToEvents", function () {
    it("should return an unsubscribe function", async function () {
      const unsubscribe = sdk.subscribeToEvents(
        {
          eventName: "TaskCreated",
          contractAddress: taskRouter.target,
        },
        () => {}
      );
      expect(typeof unsubscribe).to.equal("function");
      unsubscribe();
    });

    it("should decode event with correct parameter names", async function () {
      let receivedEvent = null;
      const unsubscribe = sdk.subscribeToEvents(
        {
          eventName: "TaskCreated",
          contractAddress: taskRouter.target,
        },
        (event) => {
          receivedEvent = event;
        }
      );

      // Create a task to emit the event
      await taskRouter.connect(owner).createTask("Test task", 9999999999, {
        value: ethers.parseEther("1"),
      });

      // Wait for event
      await new Promise((r) => setTimeout(r, 100));

      expect(receivedEvent).to.not.be.null;
      expect(receivedEvent.eventName).to.equal("TaskCreated");
      expect(receivedEvent.args).to.have.property("taskId");
      expect(receivedEvent.args).to.have.property("creator");
      expect(receivedEvent.args).to.have.property("reward");
      expect(receivedEvent.blockNumber).to.be.greaterThan(0);
      expect(receivedEvent.transactionHash).to.startWith("0x");

      unsubscribe();
    });

    it("should filter by indexed parameters", async function () {
      let receivedEvent = null;
      const unsubscribe = sdk.subscribeToEvents(
        {
          eventName: "TaskCreated",
          contractAddress: taskRouter.target,
          indexedParams: {
            creator: owner.address,
          },
        },
        (event) => {
          receivedEvent = event;
        }
      );

      // Create a task from owner
      await taskRouter.connect(owner).createTask("Filtered task", 9999999999, {
        value: ethers.parseEther("0.5"),
      });

      await new Promise((r) => setTimeout(r, 100));

      expect(receivedEvent).to.not.be.null;
      expect(receivedEvent.args.creator).to.equal(owner.address);

      unsubscribe();
    });
  });

  describe("subscribeAllEvents", function () {
    it("should receive all events from a contract", async function () {
      let receivedEvent = null;
      const unsubscribe = sdk.subscribeAllEvents(
        taskRouter.target,
        (event) => {
          receivedEvent = event;
        }
      );

      await taskRouter.connect(owner).createTask("Wildcard task", 9999999999, {
        value: ethers.parseEther("0.1"),
      });

      await new Promise((r) => setTimeout(r, 100));

      expect(receivedEvent).to.not.be.null;
      expect(receivedEvent.eventName).to.equal("TaskCreated");

      unsubscribe();
    });
  });

  describe("unsubscribeAll", function () {
    it("should clear all subscribers", async function () {
      sdk.subscribeToEvents(
        {
          eventName: "TaskCreated",
          contractAddress: taskRouter.target,
        },
        () => {}
      );
      sdk.subscribeAllEvents(taskRouter.target, () => {});

      sdk.unsubscribeAll();
      // Should not throw
    });
  });
});
