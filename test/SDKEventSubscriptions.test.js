const assert = require("assert");
const path = require("path");
const { execSync } = require("child_process");

// Ensure sdk is compiled
const sdkSrc = path.join(__dirname, "..", "sdk", "src", "index.ts");
const outDir = path.join(__dirname, "..", "sdk", "dist");
try {
  execSync(`npx tsc "${sdkSrc}" --outDir "${outDir}" --target es2020 --module commonjs --skipLibCheck`, {
    cwd: path.join(__dirname, ".."),
    stdio: "pipe",
  });
} catch (e) {
  // If already compiled or tsc succeeds
}

const { OpenAgentsSDK } = require("../sdk/dist/index.js");

function createFakeContract() {
  const calls = { on: [], off: [], filters: [] };
  const websocketHandlers = {};
  const eventFragment = {
    inputs: [
      { name: "user", indexed: true },
      { name: "taskId", indexed: true },
      { name: "status", indexed: false },
    ],
  };
  const filter = { eventName: "TaskUpdated" };
  const contract = {
    interface: {
      getEvent(name) {
        assert.strictEqual(name, "TaskUpdated");
        return eventFragment;
      },
    },
    filters: {
      TaskUpdated(...args) {
        calls.filters.push(args);
        return filter;
      },
    },
    runner: {
      provider: {
        websocket: {
          on(eventName, handler) {
            websocketHandlers[eventName] = handler;
          },
        },
      },
    },
    async on(usedFilter, listener) {
      calls.on.push({ filter: usedFilter, listener });
      contract.listener = listener;
    },
    off(usedFilter, listener) {
      calls.off.push({ filter: usedFilter, listener });
    },
    emitClose() {
      if (websocketHandlers.close) {
        return websocketHandlers.close();
      }
    },
  };
  return { contract, calls, filter };
}

async function testSubscribeDecodeFilterAndReconnect() {
  console.log("Running SDK event subscription tests...");

  const sdk = new OpenAgentsSDK({
    name: "agent",
    endpoint: "https://agent.example",
    privateKey: "0x0123456789012345678901234567890123456789012345678901234567890123",
    rpcUrl: "http://127.0.0.1:8545",
    registryAddress: "0x0000000000000000000000000000000000000001",
    routerAddress: "0x0000000000000000000000000000000000000002",
  });
  const { contract, calls, filter } = createFakeContract();
  const received = [];

  // 1. Subscribe with indexed filters
  const subscription = sdk.subscribeToEvents(
    contract,
    "TaskUpdated",
    (event) => received.push(event),
    {
      indexedFilters: {
        user: "0x0000000000000000000000000000000000000003",
        taskId: 7n,
      },
      reconnectDelayMs: 0,
    }
  );

  // Verify filter construction with indexed arguments
  assert.deepStrictEqual(calls.filters, [["0x0000000000000000000000000000000000000003", 7n]]);
  assert.strictEqual(calls.on.length, 1);
  assert.strictEqual(calls.on[0].filter, filter);
  console.log("✓ Subscribed with indexed filter matching ABI");

  // 2. Receive and decode event
  await contract.listener(
    "0x0000000000000000000000000000000000000003",
    7n,
    "completed",
    { log: { transactionHash: "0xabc", blockNumber: 12345 } }
  );

  assert.strictEqual(received.length, 1);
  assert.strictEqual(received[0].name, "TaskUpdated");
  assert.strictEqual(received[0].args.user, "0x0000000000000000000000000000000000000003");
  assert.strictEqual(received[0].args.taskId, 7n);
  assert.strictEqual(received[0].args.status, "completed");
  assert.strictEqual(received[0].values[0], "0x0000000000000000000000000000000000000003");
  assert.strictEqual(received[0].values[1], 7n);
  assert.strictEqual(received[0].values[2], "completed");
  assert.strictEqual(received[0].log.transactionHash, "0xabc");
  console.log("✓ Received and decoded event with parameter names and values");

  // 3. Test auto-reconnect on WebSocket drop
  await contract.emitClose();
  assert.strictEqual(calls.off.length, 1, "Should unsubscribe on reconnect");
  assert.strictEqual(calls.on.length, 2, "Should resubscribe on reconnect");
  console.log("✓ Reconnected and resubscribed automatically on WebSocket close");

  // 4. Test unsubscribe cleanup
  subscription.unsubscribe();
  assert.strictEqual(calls.off.length, 2, "Should unsubscribe when explicitly requested");
  console.log("✓ Unsubscribe cleans up event listeners");

  console.log("All SDK event subscription tests passed successfully (4/4)!");
}

testSubscribeDecodeFilterAndReconnect().catch((err) => {
  console.error("Test failure:", err);
  process.exit(1);
});
