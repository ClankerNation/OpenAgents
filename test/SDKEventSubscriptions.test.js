/**
 * Contributor: Codex
 * Timestamp: 2026-08-06T09:31:37Z
 * Runtime: darwin/arm64, home=/Users/chiko, cwd=/tmp/openagents-196-worktree, shell=/bin/zsh
 * Private platform/session initialization instructions are intentionally omitted.
 */

const assert = require("assert");
const childProcess = require("child_process");
const fs = require("fs");
const { EventEmitter } = require("events");
const os = require("os");
const path = require("path");
const { ethers } = require("ethers");
const Module = require("module");

const repositoryRoot = path.resolve(__dirname, "..");
process.env.NODE_PATH = path.join(repositoryRoot, "node_modules");
Module._initPaths();
const compiledSdkDirectory = fs.mkdtempSync(path.join(os.tmpdir(), "openagents-sdk-test-"));
childProcess.execFileSync(
  "npx",
  [
    "tsc",
    "--outDir",
    compiledSdkDirectory,
    "--rootDir",
    path.join(repositoryRoot, "sdk/src"),
    "--target",
    "ES2020",
    "--module",
    "Node16",
    "--moduleResolution",
    "Node16",
    "--lib",
    "ES2020,DOM",
    "--skipLibCheck",
    "--types",
    "node",
    path.join(repositoryRoot, "sdk/src/index.ts"),
    path.join(repositoryRoot, "sdk/src/providers/websocket.ts"),
  ],
  { cwd: repositoryRoot, stdio: "inherit" }
);

const { OpenAgentsSDK } = require(path.join(compiledSdkDirectory, "index.js"));
const { WebSocketProvider } = require(path.join(compiledSdkDirectory, "providers/websocket.js"));

const wait = (milliseconds = 0) => new Promise((resolve) => setTimeout(resolve, milliseconds));

function createFakeContract() {
  const address = "0x0000000000000000000000000000000000000001";
  const interfaceInstance = new ethers.Interface([
    "event Transfer(address indexed from,address indexed to,uint256 amount)",
  ]);
  const provider = new EventEmitter();
  const calls = { on: [], off: [] };
  const contract = {
    interface: interfaceInstance,
    target: address,
    runner: { provider },
    filters: {
      Transfer: (...values) => ({ event: "Transfer", values }),
    },
    on(filter, listener) {
      calls.on.push({ filter, listener });
      this.listener = listener;
    },
    off(filter, listener) {
      calls.off.push({ filter, listener });
      if (this.listener === listener) {
        this.listener = undefined;
      }
    },
    calls,
    provider,
  };
  return contract;
}

async function testSdkSubscription() {
  const sdk = Object.create(OpenAgentsSDK.prototype);
  const contract = createFakeContract();
  const from = "0x0000000000000000000000000000000000000002";
  const to = "0x0000000000000000000000000000000000000003";
  const received = [];

  const subscription = sdk.subscribeToEvents(
    contract,
    "Transfer",
    (event) => received.push(event),
    { indexedFilters: { to }, reconnectDelayMs: 0 }
  );

  assert.strictEqual(contract.calls.on.length, 1, "subscribes immediately");
  assert.deepStrictEqual(contract.calls.on[0].filter.values, [null, to]);

  const fragment = contract.interface.getEvent("Transfer");
  const encoded = contract.interface.encodeEventLog(fragment, [from, to, 7n]);
  contract.listener({ topics: encoded.topics, data: encoded.data });
  assert.strictEqual(received.length, 1, "receives a raw log");
  assert.strictEqual(received[0].name, "Transfer");
  assert.strictEqual(received[0].args.from, from);
  assert.strictEqual(received[0].args.to, to);
  assert.strictEqual(received[0].args.amount, 7n);

  contract.provider.emit("close");
  await wait(10);
  assert.strictEqual(contract.calls.off.length, 1, "removes the old listener on reconnect");
  assert.strictEqual(contract.calls.on.length, 2, "resubscribes after a WebSocket drop");

  const onCallsBeforeUnsubscribe = contract.calls.on.length;
  subscription.unsubscribe();
  contract.provider.emit("close");
  await wait(10);
  assert.strictEqual(contract.calls.on.length, onCallsBeforeUnsubscribe);

  assert.throws(
    () => sdk.subscribeToEvents(contract, "Missing", () => undefined),
    /Unknown contract event/
  );
}

async function testNoAutoReconnect() {
  const sdk = Object.create(OpenAgentsSDK.prototype);
  const contract = createFakeContract();
  const subscription = sdk.subscribeToEvents(contract, "Transfer", () => undefined, {
    autoReconnect: false,
  });

  contract.provider.emit("close");
  await wait(10);
  assert.strictEqual(contract.calls.on.length, 1, "does not reconnect when disabled");
  subscription.unsubscribe();
}

class FakeWebSocket {
  static instances = [];
  static nextSubscriptionId = 1;

  constructor(url) {
    this.url = url;
    this.sent = [];
    FakeWebSocket.instances.push(this);
  }

  open() {
    this.onopen?.();
  }

  send(message) {
    const request = JSON.parse(message);
    this.sent.push(request);
    if (request.method === "eth_subscribe") {
      const result = `server-sub-${FakeWebSocket.nextSubscriptionId++}`;
      setImmediate(() => this.onmessage?.({ data: JSON.stringify({ id: request.id, result }) }));
    } else if (request.method === "eth_unsubscribe") {
      setImmediate(() => this.onmessage?.({ data: JSON.stringify({ id: request.id, result: true }) }));
    }
  }

  emitSubscription(subscription, result) {
    this.onmessage?.({
      data: JSON.stringify({
        method: "eth_subscription",
        params: { subscription, result },
      }),
    });
  }

  close() {
    this.onclose?.();
  }
}

async function testLowLevelResubscribe() {
  const originalWebSocket = global.WebSocket;
  global.WebSocket = FakeWebSocket;
  FakeWebSocket.instances = [];
  FakeWebSocket.nextSubscriptionId = 1;

  try {
    const provider = new WebSocketProvider({
      url: "wss://example.invalid",
      reconnectIntervalMs: 0,
      maxReconnectAttempts: 2,
    });
    const received = [];

    const connectPromise = provider.connect();
    FakeWebSocket.instances[0].open();
    await connectPromise;
    const firstSubscription = await provider.subscribe("logs", (value) => received.push(value));
    FakeWebSocket.instances[0].emitSubscription(firstSubscription, "first");
    assert.deepStrictEqual(received, ["first"]);

    FakeWebSocket.instances[0].close();
    await wait(10);
    assert.strictEqual(FakeWebSocket.instances.length, 2, "opens a replacement socket");

    const reconnectPromise = wait(10);
    FakeWebSocket.instances[1].open();
    await reconnectPromise;
    const replacementRequest = FakeWebSocket.instances[1].sent.find(
      (request) => request.method === "eth_subscribe"
    );
    assert.ok(replacementRequest, "resubscribes on the replacement socket");
    await wait(10);
    const replacementSubscription = FakeWebSocket.instances[1].sent.find(
      (request) => request.method === "eth_subscribe"
    );
    const replacementId = `server-sub-${FakeWebSocket.nextSubscriptionId - 1}`;
    assert.strictEqual(replacementSubscription.params[0], "logs");
    FakeWebSocket.instances[1].emitSubscription(replacementId, "second");
    assert.deepStrictEqual(received, ["first", "second"]);

    assert.strictEqual(await provider.unsubscribe(firstSubscription), true);
    provider.disconnect();
  } finally {
    global.WebSocket = originalWebSocket;
  }
}

(async () => {
  await testSdkSubscription();
  await testNoAutoReconnect();
  await testLowLevelResubscribe();
  console.log("SDK event subscription tests passed");
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
