const assert = require("assert");
const fs = require("fs");
const path = require("path");
const os = require("os");
const { execFileSync } = require("child_process");

function loadSdk() {
  const outputDir = fs.mkdtempSync(path.join(os.tmpdir(), "openagents-sdk-events-"));
  execFileSync(
    process.platform === "win32" ? "npx.cmd" : "npx",
    [
      "tsc",
      "--target",
      "ES2022",
      "--module",
      "Node16",
      "--moduleResolution",
      "Node16",
      "--skipLibCheck",
      "--types",
      "node",
      "--outDir",
      outputDir,
      "sdk/src/index.ts",
      "sdk/src/providers/websocket.ts",
    ],
    { cwd: path.join(__dirname, ".."), stdio: "inherit" },
  );
  process.env.NODE_PATH = path.join(__dirname, "..", "node_modules");
  require("module").Module._initPaths();
  return {
    sdk: require(path.join(outputDir, "index.js")),
    websocket: require(path.join(outputDir, "providers", "websocket.js")),
  };
}

function createProvider() {
  const provider = {
    subscriptions: new Map(),
    subscribeCalls: [],
    unsubscribeCalls: [],
    async subscribe(event, callback, params) {
      const id = `subscription-${this.subscribeCalls.length + 1}`;
      this.subscribeCalls.push({ id, event, callback, params });
      this.subscriptions.set(id, callback);
      return id;
    },
    async unsubscribe(id) {
      this.unsubscribeCalls.push(id);
      this.subscriptions.delete(id);
      return true;
    },
    async emit(id, log) {
      await this.subscriptions.get(id)?.(log);
    },
  };
  return provider;
}

async function main() {
  const loaded = loadSdk();
  const { OpenAgentsSDK } = loaded.sdk;
  const sdk = new OpenAgentsSDK({
    name: "agent",
    endpoint: "https://agent.example",
    privateKey: "0x" + "11".repeat(32),
    rpcUrl: "https://rpc.example",
    registryAddress: "0x" + "22".repeat(20),
    routerAddress: "0x" + "33".repeat(20),
  });
  const provider = createProvider();
  const contract = {
    address: "0x" + "44".repeat(20),
    abi: [
      "event TaskUpdated(address indexed user,uint256 indexed taskId,string status)",
    ],
  };
  const events = [];
  const subscription = await sdk.subscribeToEvents(
    contract,
    "TaskUpdated",
    (event) => events.push(event),
    {
      provider,
      indexedFilters: { user: "0x" + "55".repeat(20), taskId: 7n },
    },
  );

  assert.strictEqual(provider.subscribeCalls.length, 1);
  assert.deepStrictEqual(provider.subscribeCalls[0].event, "logs");
  assert.deepStrictEqual(provider.subscribeCalls[0].params[0].address, contract.address);
  assert.strictEqual(provider.subscribeCalls[0].params[0].topics.length, 3);
  assert.strictEqual(provider.subscribeCalls[0].params[0].topics[1], "0x" + "55".repeat(20).padStart(64, "0"));

  const iface = new (require("ethers").Interface)(contract.abi);
  const encoded = iface.encodeEventLog(iface.getEvent("TaskUpdated"), ["0x" + "55".repeat(20), 7n, "complete"]);
  await provider.emit(subscription.id, {
    address: contract.address,
    topics: encoded.topics,
    data: encoded.data,
    transactionHash: "0x" + "66".repeat(32),
  });
  assert.strictEqual(events.length, 1);
  assert.strictEqual(events[0].name, "TaskUpdated");
  assert.strictEqual(events[0].args.user, "0x" + "55".repeat(20));
  assert.strictEqual(events[0].args.taskId, 7n);
  assert.strictEqual(events[0].args.status, "complete");

  assert.strictEqual(await subscription.unsubscribe(), true);
  assert.strictEqual(await subscription.unsubscribe(), false);
  assert.deepStrictEqual(provider.unsubscribeCalls, [subscription.id]);

  const wildcardSubscription = await sdk.subscribeToEvents(
    contract,
    "TaskUpdated",
    () => undefined,
    { provider, indexedFilters: { taskId: 7n } },
  );
  assert.strictEqual(provider.subscribeCalls[1].params[0].topics.length, 3);
  assert.strictEqual(provider.subscribeCalls[1].params[0].topics[1], null);
  await wildcardSubscription.unsubscribe();

  await testWebSocketProvider(loaded.websocket.WebSocketProvider);
  console.log("SDK event subscription tests passed");
}

async function testWebSocketProvider(WebSocketProvider) {
  const originalWebSocket = global.WebSocket;
  class FakeWebSocket {
    static instances = [];
    static nextSubscriptionId = 1;

    constructor(url) {
      this.url = url;
      this.sent = [];
      FakeWebSocket.instances.push(this);
      queueMicrotask(() => this.onopen?.());
    }

    send(payload) {
      const request = JSON.parse(payload);
      this.sent.push(request);
      if (request.method === "eth_subscribe") {
        const result = `remote-${FakeWebSocket.nextSubscriptionId++}`;
        queueMicrotask(() => this.onmessage?.({
          data: JSON.stringify({ jsonrpc: "2.0", id: request.id, result }),
        }));
      } else if (request.method === "eth_unsubscribe") {
        queueMicrotask(() => this.onmessage?.({
          data: JSON.stringify({ jsonrpc: "2.0", id: request.id, result: true }),
        }));
      }
    }

    close() {
      this.onclose?.();
    }

    emitSubscription(subscription, result) {
      this.onmessage?.({
        data: JSON.stringify({
          jsonrpc: "2.0",
          method: "eth_subscription",
          params: { subscription, result },
        }),
      });
    }
  }

  global.WebSocket = FakeWebSocket;
  try {
    const provider = new WebSocketProvider({ url: "wss://rpc.example", reconnectIntervalMs: 0 });
    const received = [];
    const subscription = await provider.subscribe(
      "logs",
      (log) => received.push(log),
      [{ address: "0x" + "44".repeat(20) }],
    );
    assert.strictEqual(FakeWebSocket.instances.length, 1);
    assert.deepStrictEqual(FakeWebSocket.instances[0].sent[0].params, [
      "logs",
      { address: "0x" + "44".repeat(20) },
    ]);

    FakeWebSocket.instances[0].emitSubscription("remote-1", { blockNumber: "0x1" });
    assert.deepStrictEqual(received, [{ blockNumber: "0x1" }]);

    FakeWebSocket.instances[0].close();
    await waitFor(() => FakeWebSocket.instances.length === 2);
    await waitFor(() => FakeWebSocket.instances[1].sent.length === 1);
    assert.deepStrictEqual(FakeWebSocket.instances[1].sent[0].params, [
      "logs",
      { address: "0x" + "44".repeat(20) },
    ]);
    FakeWebSocket.instances[1].emitSubscription("remote-2", { blockNumber: "0x2" });
    assert.deepStrictEqual(received, [
      { blockNumber: "0x1" },
      { blockNumber: "0x2" },
    ]);

    assert.strictEqual(await provider.unsubscribe(subscription), true);
    assert.deepStrictEqual(FakeWebSocket.instances[1].sent[1].params, ["remote-2"]);
    provider.disconnect();
  } finally {
    global.WebSocket = originalWebSocket;
  }
}

async function waitFor(predicate) {
  for (let attempt = 0; attempt < 50; attempt += 1) {
    if (predicate()) return;
    await new Promise((resolve) => setTimeout(resolve, 0));
  }
  throw new Error("Timed out waiting for WebSocket provider state");
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
