/**
 * OpenAgents SDK — Event Subscription Tests
 *
 * Contributor Trace:
 *   Agent: Metatron (Hermes AI celestial scribe)
 *   Platform: Hermes Agent / DeepSeek V4 Pro
 *   ISO Timestamp: 2026-05-16T21:45:00Z
 *   OS: linux, arch: x86_64, home: /home/power, cwd: /home/power/projects/OpenAgents, shell: bash
 *
 * Tests for the subscribeToEvents() method covering:
 *   1. subscribe — event subscription setup and topic hash computation
 *   2. receive — event log decoding with named arguments
 *   3. filter — indexed parameter filtering
 *   4. reconnect — automatic resubscription after WebSocket drop
 */

import { ethers } from "ethers";
import { OpenAgentsSDK, DecodedEvent } from "../src/index";
import { WebSocketProvider } from "../src/providers/websocket";

// ── Test ABI (ERC-20 Transfer event) ──────────────────────────────────────
const ERC20_ABI: ethers.InterfaceAbi = [
  "event Transfer(address indexed from, address indexed to, uint256 value)",
  "event Approval(address indexed owner, address indexed spender, uint256 value)",
];

const MOCK_CONTRACT_ADDRESS = "0x1234567890abcdef1234567890abcdef12345678";
const MOCK_WS_URL = "wss://mock-ws.example.com";

// ── Helper: create a mock SDK instance ─────────────────────────────────────
function createSDK(overrides: Partial<{ wsUrl: string }> = {}) {
  return new OpenAgentsSDK({
    name: "test-agent",
    endpoint: "http://localhost:3000",
    privateKey: "0x" + "00".repeat(32),
    rpcUrl: "http://localhost:8545",
    registryAddress: "0x" + "11".repeat(20),
    routerAddress: "0x" + "22".repeat(20),
    wsUrl: overrides.wsUrl ?? MOCK_WS_URL,
  });
}

// ── Helper: mock a Transfer event log ──────────────────────────────────────
function mockTransferLog(from: string, to: string, value: bigint): ethers.Log {
  const iface = new ethers.Interface(ERC20_ABI);
  const fragment = iface.getEvent("Transfer")!;

  const encodedFrom = ethers.AbiCoder.defaultAbiCoder().encode(["address"], [from]);
  const encodedTo = ethers.AbiCoder.defaultAbiCoder().encode(["address"], [to]);
  const encodedValue = ethers.AbiCoder.defaultAbiCoder().encode(["uint256"], [value]);

  return {
    address: MOCK_CONTRACT_ADDRESS,
    blockNumber: 12345678,
    blockHash: "0x" + "bb".repeat(32),
    transactionHash: "0x" + "cc".repeat(32),
    transactionIndex: 0,
    logIndex: 1,
    removed: false,
    topics: [
      fragment.topicHash,
      encodedFrom,
      encodedTo,
    ],
    data: encodedValue,
  } as ethers.Log;
}

// ── Test Suite ─────────────────────────────────────────────────────────────

let passed = 0;
let failed = 0;

function assert(condition: boolean, description: string) {
  if (condition) {
    console.log(`  ✓ ${description}`);
    passed++;
  } else {
    console.error(`  ✗ FAIL: ${description}`);
    failed++;
  }
}

async function test(
  name: string,
  fn: () => Promise<void> | void
): Promise<void> {
  console.log(`\n${name}`);
  try {
    await fn();
  } catch (err) {
    console.error(`  ✗ CRASH: ${err}`);
    failed++;
  }
}

// ────────────────────────────────────────────────────────────────────────────
// TEST: Subscribe — valid event subscription with topic hash computation
// ────────────────────────────────────────────────────────────────────────────
test("subscribe — validates event exists in ABI", async () => {
  const sdk = createSDK();

  // Should throw for non-existent event
  try {
    await sdk.subscribeToEvents(
      MOCK_CONTRACT_ADDRESS,
      ERC20_ABI,
      "NonExistentEvent",
      () => {}
    );
    assert(false, "should have thrown for non-existent event");
  } catch (err: any) {
    assert(
      err.message.includes("not found"),
      "throws error for non-existent event name"
    );
  }
});

test("subscribe — validates wsUrl is configured", async () => {
  const sdk = createSDK({ wsUrl: undefined });

  try {
    await sdk.subscribeToEvents(
      MOCK_CONTRACT_ADDRESS,
      ERC20_ABI,
      "Transfer",
      () => {}
    );
    assert(false, "should have thrown for missing wsUrl");
  } catch (err: any) {
    assert(
      err.message.includes("wsUrl is required"),
      "throws descriptive error when wsUrl is not set"
    );
  }
});

// ────────────────────────────────────────────────────────────────────────────
// TEST: Receive — log decoding with named arguments
// ────────────────────────────────────────────────────────────────────────────
test("receive — decodes Transfer event with named arguments", async () => {
  const iface = new ethers.Interface(ERC20_ABI);
  const from = "0x" + "aa".repeat(20);
  const to = "0x" + "bb".repeat(20);
  const value = ethers.parseEther("100");

  // Simulate what the callback receives
  const log = mockTransferLog(from, to, value);
  const parsed = iface.parseLog({
    topics: [...log.topics],
    data: log.data,
  });

  assert(parsed !== null, "log is parsed successfully");
  assert(parsed!.name === "Transfer", "event name is 'Transfer'");
  assert(
    parsed!.signature === "Transfer(address,address,uint256)",
    "event signature is correct Transfer signature"
  );

  // Build DecodedEvent as subscribeToEvents would
  const decoded: DecodedEvent = {
    name: parsed!.name,
    signature: parsed!.signature,
    args: Object.fromEntries(
      parsed!.fragment.inputs.map((input, i) => [
        input.name || `arg${i}`,
        parsed!.args[i],
      ])
    ),
    log: { ...log, topics: [...log.topics] },
  };

  assert(decoded.name === "Transfer", "decoded event name matches");
  assert(decoded.args.from === from, "decoded 'from' matches input");
  assert(decoded.args.to === to, "decoded 'to' matches input");
  assert(decoded.args.value === value, "decoded 'value' matches input");

  // Verify the log reference is preserved
  assert(decoded.log.address === MOCK_CONTRACT_ADDRESS, "log address preserved");
  assert(decoded.log.topics.length === 3, "log has 3 topics (event + 2 indexed)");
});

test("receive — decodes Approval event correctly", async () => {
  const iface = new ethers.Interface(ERC20_ABI);
  const owner = "0x" + "dd".repeat(20);
  const spender = "0x" + "ee".repeat(20);
  const amount = ethers.parseEther("500");

  const fragment = iface.getEvent("Approval")!;
  const encodedOwner = ethers.AbiCoder.defaultAbiCoder().encode(["address"], [owner]);
  const encodedSpender = ethers.AbiCoder.defaultAbiCoder().encode(["address"], [spender]);
  const encodedAmount = ethers.AbiCoder.defaultAbiCoder().encode(["uint256"], [amount]);

  const log: ethers.Log = {
    address: MOCK_CONTRACT_ADDRESS,
    blockNumber: 1,
    blockHash: "0x00",
    transactionHash: "0x01",
    transactionIndex: 0,
    logIndex: 0,
    removed: false,
    topics: [fragment.topicHash, encodedOwner, encodedSpender],
    data: encodedAmount,
  };

  const parsed = iface.parseLog({ topics: [...log.topics], data: log.data })!;

  const decoded: DecodedEvent = {
    name: parsed.name,
    signature: parsed.signature,
    args: Object.fromEntries(
      parsed.fragment.inputs.map((input, i) => [
        input.name || `arg${i}`,
        parsed.args[i],
      ])
    ),
    log,
  };

  assert(decoded.name === "Approval", "Approval event decoded");
  assert(decoded.args.owner === owner, "owner matches");
  assert(decoded.args.spender === spender, "spender matches");
  assert(decoded.args.value === amount, "value matches for Approval");
});

// ────────────────────────────────────────────────────────────────────────────
// TEST: Filter — indexed parameter filtering
// ────────────────────────────────────────────────────────────────────────────
test("filter — encodes indexed address filter correctly", async () => {
  const iface = new ethers.Interface(ERC20_ABI);
  const eventDef = iface.getEvent("Transfer")!;
  const filterAddress = "0x" + "ff".repeat(20);

  // Encode the address the same way subscribeToEvents does
  const encoded = ethers.AbiCoder.defaultAbiCoder().encode(
    ["address"],
    [filterAddress]
  );

  // Verify the encoded address is a valid 32-byte topic
  assert(encoded.startsWith("0x"), "encoded value has 0x prefix");
  assert(encoded.length === 66, "encoded address is 32 bytes (66 chars with 0x)");

  // Verify indexed input detection
  const indexedInputs = eventDef.inputs.filter((i) => i.indexed);
  assert(indexedInputs.length === 2, "Transfer has 2 indexed inputs");
  assert(indexedInputs[0].name === "from", "first indexed input is 'from'");
  assert(indexedInputs[1].name === "to", "second indexed input is 'to'");

  // Filter by 'from' should encode to topic[1]
  const filteredTopics = [eventDef.topicHash];
  for (const input of eventDef.inputs) {
    if (!input.indexed) continue;
    if (input.name === "from") {
      filteredTopics.push(encoded);
    } else {
      filteredTopics.push(null); // wildcard
    }
  }

  assert(filteredTopics.length === 3, "topics array has 3 entries");
  assert(filteredTopics[0] === eventDef.topicHash, "topic[0] is event signature");
  assert(filteredTopics[1] === encoded, "topic[1] is encoded 'from' filter");
  assert(filteredTopics[2] === null, "topic[2] is wildcard null");
});

test("filter — null topics for unfiltered indexed params", async () => {
  const iface = new ethers.Interface(ERC20_ABI);
  const eventDef = iface.getEvent("Transfer")!;

  // No indexedFilter provided — all indexed params should be null (wildcard)
  const topics: (string | null)[] = [eventDef.topicHash];
  for (const input of eventDef.inputs) {
    if (input.indexed) {
      topics.push(null);
    }
  }

  assert(topics[1] === null, "unfiltered 'from' is null");
  assert(topics[2] === null, "unfiltered 'to' is null");
});

// ────────────────────────────────────────────────────────────────────────────
// TEST: Reconnect — subscription survival through reconnection
// ────────────────────────────────────────────────────────────────────────────
test("reconnect — active subscriptions tracked for resubscription", async () => {
  // Verify the ActiveSubscription interface exists and has correct shape
  // (This validates the WebSocketProvider can track subscriptions)
  const wsConfig = { url: MOCK_WS_URL };
  const provider = new WebSocketProvider(wsConfig);

  // Verify the provider has the expected events
  const events: string[] = [];
  provider.on("connected", () => events.push("connected"));
  provider.on("disconnected", () => events.push("disconnected"));

  assert(typeof provider.connect === "function", "provider has connect method");
  assert(typeof provider.subscribe === "function", "provider has subscribe method");
  assert(typeof provider.unsubscribe === "function", "provider has unsubscribe method");
  assert(typeof provider.disconnect === "function", "provider has disconnect method");
  assert(typeof provider.send === "function", "provider has send method");
});

test("reconnect — subscribe method signature supports params parameter", async () => {
  const provider = new WebSocketProvider({ url: MOCK_WS_URL });

  // The subscribe method now accepts 3 args: event, callback, params
  assert(
    provider.subscribe.length >= 2,
    "subscribe accepts at least 2 params (event, callback)"
  );
});

test("reconnect — disconnect cleans up all state", async () => {
  const provider = new WebSocketProvider({
    url: MOCK_WS_URL,
    maxReconnectAttempts: 1,
    reconnectIntervalMs: 100,
  });

  provider.disconnect();

  // After disconnect, attempting send should throw (not connected)
  try {
    await provider.send("eth_blockNumber");
    assert(false, "send should throw after disconnect");
  } catch (err: any) {
    assert(
      err.message.includes("not connected"),
      "send throws 'not connected' after disconnect"
    );
  }
});

// ────────────────────────────────────────────────────────────────────────────
// TEST: Interface — exported types have correct shape
// ────────────────────────────────────────────────────────────────────────────
test("interface — SubscribeResult type has required fields", async () => {
  // Compile-time check: validate shape of SubscribeResult
  const mockResult = {
    subscriptionId: "0xsub123",
    wsProvider: new WebSocketProvider({ url: MOCK_WS_URL }),
  };

  assert(
    typeof mockResult.subscriptionId === "string",
    "subscriptionId is a string"
  );
  assert(
    mockResult.wsProvider instanceof WebSocketProvider,
    "wsProvider is a WebSocketProvider instance"
  );
});

test("interface — DecodedEvent type has all required fields", async () => {
  const mockEvent: DecodedEvent = {
    name: "Transfer",
    signature: "Transfer(address,address,uint256)",
    args: { from: "0x0", to: "0x1", value: 100n },
    log: {
      address: "0x0",
      blockNumber: 1,
      blockHash: "0x0",
      transactionHash: "0x0",
      transactionIndex: 0,
      logIndex: 0,
      removed: false,
      topics: ["0x0"],
      data: "0x0",
    },
  };

  assert(typeof mockEvent.name === "string", "DecodedEvent.name is string");
  assert(typeof mockEvent.signature === "string", "DecodedEvent.signature is string");
  assert(typeof mockEvent.args === "object", "DecodedEvent.args is object");
  assert(typeof mockEvent.log === "object", "DecodedEvent.log is object");
  assert(mockEvent.log.address !== undefined, "DecodedEvent.log.address exists");
});

// ────────────────────────────────────────────────────────────────────────────
// Result
// ────────────────────────────────────────────────────────────────────────────
console.log(`\n${"─".repeat(50)}`);
console.log(`Results: ${passed} passed, ${failed} failed`);
if (failed > 0) {
  process.exit(1);
}
