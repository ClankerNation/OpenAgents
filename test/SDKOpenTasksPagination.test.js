process.env.TS_NODE_IGNORE_DIAGNOSTICS = "5102";
process.env.TS_NODE_COMPILER_OPTIONS = JSON.stringify({
  module: "commonjs",
  target: "es2020",
});

require("ts-node/register/transpile-only");

const { expect } = require("chai");
const { OpenAgentsSDK } = require("../sdk/src/index.ts");

const sdkConfig = {
  name: "agent",
  endpoint: "https://agent.example",
  privateKey: "0x".padEnd(66, "1"),
  rpcUrl: "http://127.0.0.1:8545",
  registryAddress: "0x0000000000000000000000000000000000000001",
  routerAddress: "0x0000000000000000000000000000000000000002",
};

function makeTask(id, status = 0) {
  return [
    `0x${String(id + 1).padStart(40, "0")}`,
    `0x${String(id + 100).padStart(64, "0")}`,
    `task-${id}`,
    BigInt(id + 1),
    BigInt(1000 + id),
    status,
    "0x",
  ];
}

class TestSDK extends OpenAgentsSDK {
  constructor(tasks) {
    super(sdkConfig);
    this.blockNumber = 1;
    this.taskCountCalls = 0;
    this.currentTasksCalls = 0;
    this.maxConcurrentTasksCalls = 0;
    this.tasksData = tasks;
  }

  createRouterReader() {
    return {
      taskCount: async () => {
        this.taskCountCalls += 1;
        return BigInt(this.tasksData.length);
      },
      tasks: async (id) => {
        this.currentTasksCalls += 1;
        this.maxConcurrentTasksCalls = Math.max(this.maxConcurrentTasksCalls, this.currentTasksCalls);
        await new Promise((resolve) => setTimeout(resolve, 1));
        this.currentTasksCalls -= 1;
        return this.tasksData[id];
      },
    };
  }

  async getCurrentBlockNumber() {
    return this.blockNumber;
  }
}

describe("OpenAgentsSDK.getOpenTasks", function () {
  it("paginates and fetches tasks with at most 10 concurrent calls", async function () {
    const sdk = new TestSDK(Array.from({ length: 25 }, (_, id) => makeTask(id)));

    const tasks = await sdk.getOpenTasks({ offset: 5, limit: 12 });

    expect(tasks.map((task) => task.id)).to.deep.equal([5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16]);
    expect(sdk.maxConcurrentTasksCalls).to.equal(10);
  });

  it("caches taskCount for one provider block", async function () {
    const sdk = new TestSDK(Array.from({ length: 3 }, (_, id) => makeTask(id)));

    await sdk.getOpenTasks({ limit: 1 });
    await sdk.getOpenTasks({ limit: 1 });
    expect(sdk.taskCountCalls).to.equal(1);

    sdk.blockNumber = 2;
    await sdk.getOpenTasks({ limit: 1 });
    expect(sdk.taskCountCalls).to.equal(2);
  });

  it("filters by task status", async function () {
    const sdk = new TestSDK([
      makeTask(0, 0),
      makeTask(1, 1),
      makeTask(2, 0),
      makeTask(3, 2),
    ]);

    const assigned = await sdk.getOpenTasks({ offset: 0, limit: 4, status: 1 });

    expect(assigned.map((task) => task.id)).to.deep.equal([1]);
    expect(assigned[0].status).to.equal(1);
  });
});
