process.env.TS_NODE_COMPILER_OPTIONS = JSON.stringify({
  module: "nodenext",
  moduleResolution: "nodenext",
  ignoreDeprecations: "6.0",
});
require("ts-node/register/transpile-only");

const { expect } = require("chai");
const { ethers } = require("ethers");
const { OpenAgentsSDK } = require("../sdk/src/index");

class FakeWebSocket {
  static instances = [];

  constructor(url) {
    this.url = url;
    this.sent = [];
    this.readyState = 0;
    this.onopen = null;
    this.onmessage = null;
    this.onclose = null;
    this.onerror = null;
    FakeWebSocket.instances.push(this);
  }

  send(payload) {
    this.sent.push(JSON.parse(payload));
  }

  close() {
    this.readyState = 3;
    if (this.onclose) {
      this.onclose({});
    }
  }

  open() {
    this.readyState = 1;
    if (this.onopen) {
      this.onopen({});
    }
  }

  emitMessage(message) {
    if (this.onmessage) {
      this.onmessage({ data: JSON.stringify(message) });
    }
  }
}

async function waitFor(condition, timeoutMs = 2000) {
  const start = Date.now();
  while (!condition()) {
    if (Date.now() - start > timeoutMs) {
      throw new Error("Timed out waiting for condition");
    }
    await new Promise((resolve) => setTimeout(resolve, 5));
  }
}

describe("OpenAgentsSDK event subscription", function () {
  const originalWebSocket = global.WebSocket;

  const abi = [
    "event TaskAssigned(uint256 indexed taskId, bytes32 indexed agentId)",
  ];
  const contractAddress = "0x00000000000000000000000000000000000000aa";

  beforeEach(function () {
    FakeWebSocket.instances = [];
    global.WebSocket = FakeWebSocket;
  });

  after(function () {
    global.WebSocket = originalWebSocket;
  });

  function buildSdk() {
    return new OpenAgentsSDK({
      name: "agent-1",
      endpoint: "https://agent.example",
      privateKey: "0x" + "11".repeat(32),
      rpcUrl: "http://127.0.0.1:8545",
      registryAddress: "0x0000000000000000000000000000000000000001",
      routerAddress: "0x0000000000000000000000000000000000000002",
    });
  }

  it("subscribes, filters indexed parameters, and decodes logs", async function () {
    const sdk = buildSdk();
    const received = [];
    const iface = new ethers.Interface(abi);
    const fragment = iface.getEvent("TaskAssigned");

    const subscriptionPromise = sdk.subscribeToEvents(
      { address: contractAddress, abi },
      "TaskAssigned",
      (event) => {
        received.push(event);
      },
      {
        indexedFilters: { taskId: 7n },
        wsUrl: "ws://127.0.0.1:8546",
        reconnectIntervalMs: 10,
      }
    );

    await waitFor(() => FakeWebSocket.instances.length === 1);
    const ws = FakeWebSocket.instances[0];
    ws.open();

    await waitFor(() => ws.sent.length === 1);
    expect(ws.sent[0].method).to.equal("eth_subscribe");

    const expectedTopics = iface.encodeFilterTopics(fragment, [7n, null]);
    expect(ws.sent[0].params[0]).to.equal("logs");
    expect(ws.sent[0].params[1].address).to.equal(contractAddress);
    expect(ws.sent[0].params[1].topics).to.deep.equal(expectedTopics);

    ws.emitMessage({ jsonrpc: "2.0", id: ws.sent[0].id, result: "0xsub-1" });
    const subscriptionId = await subscriptionPromise;

    const encoded = iface.encodeEventLog(fragment, [7n, "0x" + "22".repeat(32)]);
    ws.emitMessage({
      jsonrpc: "2.0",
      method: "eth_subscription",
      params: {
        subscription: "0xsub-1",
        result: {
          address: contractAddress,
          data: encoded.data,
          topics: encoded.topics,
        },
      },
    });

    await waitFor(() => received.length === 1);
    expect(received[0].eventName).to.equal("TaskAssigned");
    expect(received[0].signature).to.equal("TaskAssigned(uint256,bytes32)");
    expect(received[0].args.taskId).to.equal(7n);
    expect(received[0].args.agentId).to.equal("0x" + "22".repeat(32));

    const unsubscribePromise = sdk.unsubscribeFromEvents(subscriptionId);
    await waitFor(() => ws.sent.length === 2);
    expect(ws.sent[1].method).to.equal("eth_unsubscribe");
    ws.emitMessage({ jsonrpc: "2.0", id: ws.sent[1].id, result: true });
    expect(await unsubscribePromise).to.equal(true);

    sdk.disconnectEventStream();
  });

  it("reconnects and resubscribes automatically", async function () {
    const sdk = buildSdk();
    const received = [];
    const iface = new ethers.Interface(abi);
    const fragment = iface.getEvent("TaskAssigned");

    const subscriptionPromise = sdk.subscribeToEvents(
      { address: contractAddress, abi },
      "TaskAssigned",
      (event) => {
        received.push(event);
      },
      {
        indexedFilters: { taskId: 99n },
        wsUrl: "ws://127.0.0.1:8546",
        reconnectIntervalMs: 10,
        maxReconnectAttempts: 2,
      }
    );

    await waitFor(() => FakeWebSocket.instances.length === 1);
    const firstSocket = FakeWebSocket.instances[0];
    firstSocket.open();

    await waitFor(() => firstSocket.sent.length === 1);
    firstSocket.emitMessage({ jsonrpc: "2.0", id: firstSocket.sent[0].id, result: "0xsub-old" });
    await subscriptionPromise;

    firstSocket.close();

    await waitFor(() => FakeWebSocket.instances.length === 2);
    const secondSocket = FakeWebSocket.instances[1];
    secondSocket.open();

    await waitFor(() => secondSocket.sent.length === 1);
    expect(secondSocket.sent[0].method).to.equal("eth_subscribe");
    const expectedTopics = iface.encodeFilterTopics(fragment, [99n, null]);
    expect(secondSocket.sent[0].params[1].topics).to.deep.equal(expectedTopics);

    secondSocket.emitMessage({ jsonrpc: "2.0", id: secondSocket.sent[0].id, result: "0xsub-new" });
    await new Promise((resolve) => setTimeout(resolve, 0));

    const encoded = iface.encodeEventLog(fragment, [99n, "0x" + "44".repeat(32)]);
    secondSocket.emitMessage({
      jsonrpc: "2.0",
      method: "eth_subscription",
      params: {
        subscription: "0xsub-new",
        result: {
          address: contractAddress,
          data: encoded.data,
          topics: encoded.topics,
        },
      },
    });

    await waitFor(() => received.length === 1);
    expect(received[0].args.taskId).to.equal(99n);

    sdk.disconnectEventStream();
  });
});
