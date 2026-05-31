process.env.TS_NODE_TRANSPILE_ONLY = "true";
process.env.TS_NODE_COMPILER_OPTIONS = JSON.stringify({
  module: "commonjs",
  moduleResolution: "node",
  target: "es2020",
  ignoreDeprecations: "6.0",
});
require("ts-node/register/transpile-only");

const { expect } = require("chai");
const { ethers } = require("ethers");
const { OpenAgentsSDK } = require("../sdk/src/index");
const { WebSocketProvider } = require("../sdk/src/providers/websocket");

class FakeWebSocket {
  constructor(onSend) {
    this.onopen = null;
    this.onmessage = null;
    this.onclose = null;
    this.onerror = null;
    this.sent = [];
    this._onSend = onSend;
  }

  send(payload) {
    const parsed = JSON.parse(payload);
    this.sent.push(parsed);
    if (this._onSend) {
      this._onSend(parsed, this);
    }
  }

  close() {
    if (this.onclose) this.onclose();
  }

  open() {
    if (this.onopen) this.onopen();
  }

  emitMessage(payload) {
    if (this.onmessage) {
      this.onmessage({ data: JSON.stringify(payload) });
    }
  }
}

describe("OpenAgentsSDK event subscription", function () {
  it("subscribes with indexed filters and decodes ABI logs", async function () {
    const wallet = ethers.Wallet.createRandom();
    const sdk = new OpenAgentsSDK({
      name: "agent",
      endpoint: "https://example.com",
      privateKey: wallet.privateKey,
      rpcUrl: "http://127.0.0.1:8545",
      registryAddress: "0x0000000000000000000000000000000000000001",
      routerAddress: "0x0000000000000000000000000000000000000002",
    });

    const captured = { event: null, params: null, callback: null };
    sdk.getWebSocketProvider = async () => ({
      subscribe: async (event, callback, params) => {
        captured.event = event;
        captured.params = params;
        captured.callback = callback;
        return "sub-1";
      },
    });

    const abi = [
      "event TaskClaimed(address indexed agent,uint256 indexed taskId,string note)",
    ];
    const contract = new ethers.Contract(
      "0x00000000000000000000000000000000000000AA",
      abi
    );

    const observed = [];
    const filterAgent = "0x00000000000000000000000000000000000000BB";
    const subId = await sdk.subscribeToEvents(
      contract,
      "TaskClaimed",
      (event) => observed.push(event),
      { agent: filterAgent }
    );

    expect(subId).to.equal("sub-1");
    expect(captured.event).to.equal("logs");

    const fragment = contract.interface.getEvent("TaskClaimed");
    const expectedTopics = contract.interface.encodeFilterTopics(fragment, [
      filterAgent,
      null,
    ]);
    expect(captured.params).to.deep.equal({
      address: "0x00000000000000000000000000000000000000AA",
      topics: expectedTopics,
    });

    const logValues = [
      "0x00000000000000000000000000000000000000CC",
      42n,
      "hello",
    ];
    const encoded = contract.interface.encodeEventLog(fragment, logValues);

    captured.callback({
      data: encoded.data,
      topics: encoded.topics,
      blockNumber: "0x1",
    });

    expect(observed).to.have.lengthOf(1);
    expect(observed[0].name).to.equal("TaskClaimed");
    expect(observed[0].args.agent).to.equal(
      "0x00000000000000000000000000000000000000cc"
    );
    expect(observed[0].args.taskId).to.equal(42n);
    expect(observed[0].args.note).to.equal("hello");
  });
});

describe("WebSocketProvider reconnect", function () {
  it("resubscribes automatically after reconnect", async function () {
    let subscribeCall = 0;
    const sockets = [];
    const wsFactory = () => {
      const socket = new FakeWebSocket((message, ws) => {
        if (message.method === "eth_subscribe") {
          subscribeCall += 1;
          const subId = subscribeCall === 1 ? "remote-1" : "remote-2";
          ws.emitMessage({ jsonrpc: "2.0", id: message.id, result: subId });
        }
      });
      sockets.push(socket);
      setTimeout(() => socket.open(), 0);
      return socket;
    };

    const provider = new WebSocketProvider({
      url: "ws://example.test",
      reconnectIntervalMs: 0,
      maxReconnectAttempts: 2,
      webSocketFactory: wsFactory,
    });

    await provider.connect();
    const received = [];
    const subId = await provider.subscribe("logs", (log) => received.push(log), {
      address: "0x00000000000000000000000000000000000000AA",
    });

    expect(subId).to.equal("sub-1");
    expect(subscribeCall).to.equal(1);

    sockets[0].close();
    await new Promise((resolve) => setTimeout(resolve, 30));

    expect(subscribeCall).to.equal(2);

    sockets[1].emitMessage({
      jsonrpc: "2.0",
      method: "eth_subscription",
      params: {
        subscription: "remote-2",
        result: { value: 1 },
      },
    });

    expect(received).to.deep.equal([{ value: 1 }]);
  });
});
