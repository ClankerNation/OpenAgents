/**
 * @fix-author kejuunuy
 * @fix-date 2026-05-30
 * @fix-issue 196
 * @fix-description Tests for event subscription: subscribe, receive, filter, reconnect
 */

import {
  EventSubscriptionManager,
  computeEventTopic,
  decodeEventLog,
  decodeSingleValue,
  decodeAbiData,
  AbiEventEntry,
  RawLog,
  DecodedEventLog,
} from "../src/events";

// ──────────────────────────────────────────────────────
//  Test Helpers — mock WebSocket provider
// ──────────────────────────────────────────────────────

type MockCallback = (data: unknown) => void;

class MockWebSocketProvider {
  public subscriptions = new Map<string, MockCallback>();
  private listeners: Record<string, Array<(...args: unknown[]) => void>> = {};
  public connected = false;
  public sendCalls: Array<{ method: string; params: unknown[] }> = [];
  public disconnectCalls = 0;
  private nextSubId = 1;
  private _reconnectHandler: (() => void) | null = null;

  on(event: string, cb: (...args: unknown[]) => void) {
    if (!this.listeners[event]) this.listeners[event] = [];
    this.listeners[event].push(cb);
  }

  emit(event: string, ...args: unknown[]) {
    (this.listeners[event] || []).forEach((cb) => cb(...args));
  }

  async connect(): Promise<void> {
    this.connected = true;
    this.emit("connected");
  }

  async send(method: string, params: unknown[] = []): Promise<string> {
    this.sendCalls.push({ method, params });
    const subId = `0x${this.nextSubId++}`;
    return subId;
  }

  async unsubscribe(subscriptionId: string): Promise<boolean> {
    this.subscriptions.delete(subscriptionId);
    return true;
  }

  disconnect(): void {
    this.connected = false;
    this.disconnectCalls++;
    this.subscriptions.clear();
  }

  // Helper to simulate an incoming log from the node
  simulateLog(subscriptionId: string, log: unknown) {
    const cb = this.subscriptions.get(subscriptionId);
    if (cb) cb(log);
  }

  // Helper to simulate reconnect
  simulateReconnect() {
    this.connected = false;
    this.emit("disconnected");
    this.connected = true;
    this.emit("connected");
  }
}

// Patch EventSubscriptionManager to accept mock provider
function createManagerWithMock(mock: MockWebSocketProvider): EventSubscriptionManager {
  const manager = new EventSubscriptionManager({});
  // Inject mock provider directly
  (manager as any).wsProvider = mock;
  (manager as any)._connected = mock.connected;

  // Wire up the mock's event listeners to manager's resubscribe logic
  mock.on("connected", async () => {
    (manager as any)._connected = true;
    // Trigger resubscribe
    await (manager as any).resubscribeAll();
  });
  mock.on("disconnected", () => {
    (manager as any)._connected = false;
  });

  return manager;
}

// ──────────────────────────────────────────────────────
//  Test ABI definitions
// ──────────────────────────────────────────────────────

const TRANSFER_EVENT: AbiEventEntry = {
  type: "event",
  name: "Transfer",
  inputs: [
    { name: "from", type: "address", indexed: true },
    { name: "to", type: "address", indexed: true },
    { name: "value", type: "uint256", indexed: false },
  ],
};

const TASK_ASSIGNED_EVENT: AbiEventEntry = {
  type: "event",
  name: "TaskAssigned",
  inputs: [
    { name: "taskId", type: "uint256", indexed: true },
    { name: "agentId", type: "bytes32", indexed: true },
    { name: "reward", type: "uint256", indexed: false },
  ],
};

const APPROVAL_EVENT: AbiEventEntry = {
  type: "event",
  name: "Approval",
  inputs: [
    { name: "owner", type: "address", indexed: true },
    { name: "spender", type: "address", indexed: true },
    { name: "value", type: "uint256", indexed: false },
  ],
};

const EVENT_WITH_BOOL: AbiEventEntry = {
  type: "event",
  name: "StatusChanged",
  inputs: [
    { name: "account", type: "address", indexed: true },
    { name: "active", type: "bool", indexed: false },
  ],
};

// ──────────────────────────────────────────────────────
//  Tests
// ──────────────────────────────────────────────────────

describe("computeEventTopic", () => {
  it("should compute correct topic for Transfer event", () => {
    const topic = computeEventTopic(TRANSFER_EVENT);
    expect(topic).toMatch(/^0x[0-9a-f]{64}$/);
    // Known Transfer event topic: keccak256("Transfer(address,address,uint256)")
    expect(topic).toBe(
      "0x" +
        require("crypto")
          .createHash("sha3-256")
          .update("Transfer(address,address,uint256)")
          .digest("hex")
    );
  });

  it("should compute correct topic for TaskAssigned event", () => {
    const topic = computeEventTopic(TASK_ASSIGNED_EVENT);
    const expected =
      "0x" +
      require("crypto")
        .createHash("sha3-256")
        .update("TaskAssigned(uint256,bytes32,uint256)")
        .digest("hex");
    expect(topic).toBe(expected);
  });

  it("should normalize uint → uint256", () => {
    const event: AbiEventEntry = {
      type: "event",
      name: "Test",
      inputs: [{ name: "val", type: "uint", indexed: false }],
    };
    const event2: AbiEventEntry = {
      type: "event",
      name: "Test",
      inputs: [{ name: "val", type: "uint256", indexed: false }],
    };
    expect(computeEventTopic(event)).toBe(computeEventTopic(event2));
  });
});

describe("decodeSingleValue", () => {
  it("should decode address", () => {
    const addr = "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045";
    const word = "0x" + "0".repeat(24) + addr.slice(2).toLowerCase();
    expect(decodeSingleValue("address", word)).toBe(addr.toLowerCase());
  });

  it("should decode uint256", () => {
    const hex = "0x" + BigInt(1000).toString(16).padStart(64, "0");
    expect(decodeSingleValue("uint256", hex)).toBe(1000n);
  });

  it("should decode bool true", () => {
    const hex = "0x" + "1".padStart(64, "0");
    expect(decodeSingleValue("bool", hex)).toBe(true);
  });

  it("should decode bool false", () => {
    const hex = "0x" + "0".padStart(64, "0");
    expect(decodeSingleValue("bool", hex)).toBe(false);
  });

  it("should decode bytes32", () => {
    const hex = "0x" + "ab".repeat(32);
    expect(decodeSingleValue("bytes32", hex)).toBe("0x" + "ab".repeat(32));
  });
});

describe("decodeAbiData", () => {
  it("should decode multiple uint256 values", () => {
    const val1 = BigInt(100);
    const val2 = BigInt(200);
    const data =
      "0x" +
      val1.toString(16).padStart(64, "0") +
      val2.toString(16).padStart(64, "0");
    const result = decodeAbiData(["uint256", "uint256"], data);
    expect(result).toEqual([100n, 200n]);
  });

  it("should decode mixed types", () => {
    const addr = "0x" + "11".repeat(20);
    const val = BigInt(999);
    const data =
      "0x" +
      "0".repeat(24) + addr.slice(2) +
      val.toString(16).padStart(64, "0");
    const result = decodeAbiData(["address", "uint256"], data);
    expect(result[0]).toBe(addr.toLowerCase());
    expect(result[1]).toBe(999n);
  });
});

describe("decodeEventLog", () => {
  const CONTRACT_ADDRESS = "0x" + "aa".repeat(20);

  it("should decode Transfer event log", () => {
    const from = "0x" + "11".repeat(20);
    const to = "0x" + "22".repeat(20);
    const value = BigInt("1000000000000000000"); // 1 ETH

    const log: RawLog = {
      address: CONTRACT_ADDRESS,
      topics: [
        computeEventTopic(TRANSFER_EVENT),
        "0x" + from.slice(2).toLowerCase().padStart(64, "0"),
        "0x" + to.slice(2).toLowerCase().padStart(64, "0"),
      ],
      data: "0x" + value.toString(16).padStart(64, "0"),
      blockNumber: "0x1",
      transactionHash: "0x" + "ab".repeat(32),
      logIndex: "0x0",
    };

    const args = decodeEventLog(TRANSFER_EVENT, log);
    expect(args.from).toBe(from.toLowerCase());
    expect(args.to).toBe(to.toLowerCase());
    expect(args.value).toBe(value);
  });

  it("should decode TaskAssigned event log", () => {
    const taskId = BigInt(42);
    const agentId = "0x" + "ff".repeat(32);
    const reward = BigInt("5000000000000000000");

    const log: RawLog = {
      address: CONTRACT_ADDRESS,
      topics: [
        computeEventTopic(TASK_ASSIGNED_EVENT),
        "0x" + taskId.toString(16).padStart(64, "0"),
        agentId,
      ],
      data: "0x" + reward.toString(16).padStart(64, "0"),
      blockNumber: "0xa",
      transactionHash: "0x" + "cd".repeat(32),
      logIndex: "0x1",
    };

    const args = decodeEventLog(TASK_ASSIGNED_EVENT, log);
    expect(args.taskId).toBe(taskId);
    expect(args.agentId).toBe(agentId);
    expect(args.reward).toBe(reward);
  });

  it("should decode Approval event log", () => {
    const owner = "0x" + "33".repeat(20);
    const spender = "0x" + "44".repeat(20);
    const value = BigInt(500);

    const log: RawLog = {
      address: CONTRACT_ADDRESS,
      topics: [
        computeEventTopic(APPROVAL_EVENT),
        "0x" + owner.slice(2).toLowerCase().padStart(64, "0"),
        "0x" + spender.slice(2).toLowerCase().padStart(64, "0"),
      ],
      data: "0x" + value.toString(16).padStart(64, "0"),
      blockNumber: "0x5",
      transactionHash: null,
      logIndex: null,
    };

    const args = decodeEventLog(APPROVAL_EVENT, log);
    expect(args.owner).toBe(owner.toLowerCase());
    expect(args.spender).toBe(spender.toLowerCase());
    expect(args.value).toBe(500n);
  });

  it("should decode event with bool parameter", () => {
    const account = "0x" + "55".repeat(20);

    const log: RawLog = {
      address: CONTRACT_ADDRESS,
      topics: [
        computeEventTopic(EVENT_WITH_BOOL),
        "0x" + account.slice(2).toLowerCase().padStart(64, "0"),
      ],
      data: "0x" + "1".padStart(64, "0"),
      blockNumber: "0x3",
      transactionHash: null,
      logIndex: null,
    };

    const args = decodeEventLog(EVENT_WITH_BOOL, log);
    expect(args.account).toBe(account.toLowerCase());
    expect(args.active).toBe(true);
  });
});

describe("EventSubscriptionManager", () => {
  let mock: MockWebSocketProvider;
  let manager: EventSubscriptionManager;
  const CONTRACT = "0x" + "aa".repeat(20);

  beforeEach(async () => {
    mock = new MockWebSocketProvider();
    await mock.connect();
    manager = createManagerWithMock(mock);
  });

  afterEach(async () => {
    await manager.disconnect();
  });

  // ── Test: Subscribe ──
  it("should subscribe to events and return a handle", async () => {
    const callback = jest.fn();
    const handle = await manager.subscribeToEvents(
      CONTRACT,
      TRANSFER_EVENT,
      callback
    );

    expect(handle.subscriptionId).toBeDefined();
    expect(typeof handle.unsubscribe).toBe("function");
    expect(mock.sendCalls.length).toBe(1);
    expect(mock.sendCalls[0].method).toBe("eth_subscribe");
    expect(manager.getActiveSubscriptionCount()).toBe(1);
  });

  // ── Test: Receive ──
  it("should receive and decode event logs via callback", async () => {
    const received: DecodedEventLog[] = [];
    const handle = await manager.subscribeToEvents(
      CONTRACT,
      TRANSFER_EVENT,
      (log) => received.push(log)
    );

    const from = "0x" + "11".repeat(20);
    const to = "0x" + "22".repeat(20);
    const value = BigInt("1000000000000000000");

    const rawLog: RawLog = {
      address: CONTRACT,
      topics: [
        computeEventTopic(TRANSFER_EVENT),
        "0x" + from.slice(2).padStart(64, "0"),
        "0x" + to.slice(2).padStart(64, "0"),
      ],
      data: "0x" + value.toString(16).padStart(64, "0"),
      blockNumber: "0xa",
      transactionHash: "0x" + "ab".repeat(32),
      logIndex: "0x0",
    };

    mock.simulateLog(handle.subscriptionId, rawLog);

    expect(received.length).toBe(1);
    expect(received[0].event).toBe("Transfer");
    expect(received[0].args.from).toBe(from.toLowerCase());
    expect(received[0].args.to).toBe(to.toLowerCase());
    expect(received[0].args.value).toBe(value);
    expect(received[0].blockNumber).toBe(10);
    expect(received[0].address).toBe(CONTRACT);
  });

  it("should emit 'event' on the manager when log is received", async () => {
    const eventPromise = new Promise<DecodedEventLog>((resolve) => {
      manager.on("event", resolve);
    });

    const handle = await manager.subscribeToEvents(
      CONTRACT,
      TRANSFER_EVENT,
      () => {}
    );

    const rawLog: RawLog = {
      address: CONTRACT,
      topics: [
        computeEventTopic(TRANSFER_EVENT),
        "0x" + "11".repeat(32),
        "0x" + "22".repeat(32),
      ],
      data: "0x" + "0".repeat(63) + "1",
      blockNumber: "0x1",
      transactionHash: null,
      logIndex: null,
    };

    mock.simulateLog(handle.subscriptionId, rawLog);
    const event = await eventPromise;
    expect(event.event).toBe("Transfer");
  });

  // ── Test: Filter ──
  it("should filter events by indexed parameter", async () => {
    const received: DecodedEventLog[] = [];
    const specificFrom = "0x" + "11".repeat(20);
    const otherFrom = "0x" + "99".repeat(20);
    const to = "0x" + "22".repeat(20);

    const handle = await manager.subscribeToEvents(
      CONTRACT,
      TRANSFER_EVENT,
      (log) => received.push(log),
      { from: specificFrom }
    );

    // Verify the subscribe call includes the filter topic
    const sendCall = mock.sendCalls[0];
    const topics = sendCall.params[1] as { topics: string[] };
    expect(topics.topics[0]).toBe(computeEventTopic(TRANSFER_EVENT));
    // The from filter should be encoded as a topic
    expect(topics.topics[1]).toBe(
      "0x" + specificFrom.toLowerCase().slice(2).padStart(64, "0")
    );

    // Simulate a log from the specific address — should be received
    const matchingLog: RawLog = {
      address: CONTRACT,
      topics: [
        computeEventTopic(TRANSFER_EVENT),
        "0x" + specificFrom.slice(2).toLowerCase().padStart(64, "0"),
        "0x" + to.slice(2).padStart(64, "0"),
      ],
      data: "0x" + BigInt(100).toString(16).padStart(64, "0"),
      blockNumber: "0x1",
      transactionHash: null,
      logIndex: null,
    };
    mock.simulateLog(handle.subscriptionId, matchingLog);
    expect(received.length).toBe(1);

    // Simulate a log from a different address — should be filtered out
    const nonMatchingLog: RawLog = {
      address: CONTRACT,
      topics: [
        computeEventTopic(TRANSFER_EVENT),
        "0x" + otherFrom.slice(2).toLowerCase().padStart(64, "0"),
        "0x" + to.slice(2).padStart(64, "0"),
      ],
      data: "0x" + BigInt(200).toString(16).padStart(64, "0"),
      blockNumber: "0x2",
      transactionHash: null,
      logIndex: null,
    };
    mock.simulateLog(handle.subscriptionId, nonMatchingLog);
    expect(received.length).toBe(1); // Still 1 — the second was filtered
  });

  it("should filter by multiple indexed params", async () => {
    const received: DecodedEventLog[] = [];
    const from = "0x" + "11".repeat(20);
    const to = "0x" + "22".repeat(20);

    const handle = await manager.subscribeToEvents(
      CONTRACT,
      TRANSFER_EVENT,
      (log) => received.push(log),
      { from, to }
    );

    const sendCall = mock.sendCalls[0];
    const topics = sendCall.params[1] as { topics: (string | null)[] };
    expect(topics.topics[1]).toBe(
      "0x" + from.toLowerCase().slice(2).padStart(64, "0")
    );
    expect(topics.topics[2]).toBe(
      "0x" + to.toLowerCase().slice(2).padStart(64, "0")
    );

    // Matching log
    mock.simulateLog(handle.subscriptionId, {
      address: CONTRACT,
      topics: [
        computeEventTopic(TRANSFER_EVENT),
        "0x" + from.slice(2).toLowerCase().padStart(64, "0"),
        "0x" + to.slice(2).toLowerCase().padStart(64, "0"),
      ],
      data: "0x" + BigInt(100).toString(16).padStart(64, "0"),
      blockNumber: "0x1",
      transactionHash: null,
      logIndex: null,
    });
    expect(received.length).toBe(1);

    // Non-matching (different `to`)
    mock.simulateLog(handle.subscriptionId, {
      address: CONTRACT,
      topics: [
        computeEventTopic(TRANSFER_EVENT),
        "0x" + from.slice(2).toLowerCase().padStart(64, "0"),
        "0x" + "33".repeat(32),
      ],
      data: "0x" + BigInt(200).toString(16).padStart(64, "0"),
      blockNumber: "0x2",
      transactionHash: null,
      logIndex: null,
    });
    expect(received.length).toBe(1); // Still 1
  });

  // ── Test: Reconnect and resubscribe ──
  it("should resubscribe after WebSocket reconnect", async () => {
    const received: DecodedEventLog[] = [];
    const handle = await manager.subscribeToEvents(
      CONTRACT,
      TRANSFER_EVENT,
      (log) => received.push(log)
    );

    const originalSubId = handle.subscriptionId;
    expect(manager.getActiveSubscriptionCount()).toBe(1);

    // Simulate reconnect
    mock.simulateReconnect();

    // After resubscribe, there should be a new subscription ID
    // (the mock generates incrementing IDs)
    const newSubId = mock.sendCalls[mock.sendCalls.length - 1];
    expect(newSubId.method).toBe("eth_subscribe");

    // The old subscription should have been cleaned up
    // and a new one registered
    expect(manager.getActiveSubscriptionCount()).toBe(1);

    // Simulate a log on the new subscription
    const rawLog: RawLog = {
      address: CONTRACT,
      topics: [
        computeEventTopic(TRANSFER_EVENT),
        "0x" + "11".repeat(32),
        "0x" + "22".repeat(32),
      ],
      data: "0x" + "0".repeat(63) + "1",
      blockNumber: "0x1",
      transactionHash: null,
      logIndex: null,
    };

    // Find the new subscription ID from the subscriptions map
    const subIds = Array.from(mock.subscriptions.keys());
    const newId = subIds[subIds.length - 1];
    mock.simulateLog(newId, rawLog);

    expect(received.length).toBe(1);
    expect(received[0].event).toBe("Transfer");
  });

  // ── Test: Unsubscribe ──
  it("should unsubscribe from events", async () => {
    const handle = await manager.subscribeToEvents(
      CONTRACT,
      TRANSFER_EVENT,
      () => {}
    );

    expect(manager.getActiveSubscriptionCount()).toBe(1);
    await handle.unsubscribe();
    expect(manager.getActiveSubscriptionCount()).toBe(0);
  });

  // ── Test: Topic mismatch rejection ──
  it("should ignore logs with mismatched topic0", async () => {
    const received: DecodedEventLog[] = [];
    const handle = await manager.subscribeToEvents(
      CONTRACT,
      TRANSFER_EVENT,
      (log) => received.push(log)
    );

    // Simulate a log with wrong topic0 (Approval event instead of Transfer)
    const wrongLog: RawLog = {
      address: CONTRACT,
      topics: [
        computeEventTopic(APPROVAL_EVENT), // Wrong event!
        "0x" + "11".repeat(32),
        "0x" + "22".repeat(32),
      ],
      data: "0x" + "0".repeat(63) + "1",
      blockNumber: "0x1",
      transactionHash: null,
      logIndex: null,
    };

    mock.simulateLog(handle.subscriptionId, wrongLog);
    expect(received.length).toBe(0); // Should be ignored
  });

  // ── Test: Address mismatch rejection ──
  it("should ignore logs from non-matching contract address", async () => {
    const received: DecodedEventLog[] = [];
    const handle = await manager.subscribeToEvents(
      CONTRACT,
      TRANSFER_EVENT,
      (log) => received.push(log)
    );

    const wrongAddress = "0x" + "bb".repeat(20);
    const wrongLog: RawLog = {
      address: wrongAddress,
      topics: [
        computeEventTopic(TRANSFER_EVENT),
        "0x" + "11".repeat(32),
        "0x" + "22".repeat(32),
      ],
      data: "0x" + "0".repeat(63) + "1",
      blockNumber: "0x1",
      transactionHash: null,
      logIndex: null,
    };

    mock.simulateLog(handle.subscriptionId, wrongLog);
    expect(received.length).toBe(0);
  });

  // ── Test: Disconnect ──
  it("should clean up all subscriptions on disconnect", async () => {
    await manager.subscribeToEvents(CONTRACT, TRANSFER_EVENT, () => {});
    await manager.subscribeToEvents(CONTRACT, APPROVAL_EVENT, () => {});
    expect(manager.getActiveSubscriptionCount()).toBe(2);

    await manager.disconnect();
    expect(manager.getActiveSubscriptionCount()).toBe(0);
    expect(mock.disconnectCalls).toBe(1);
  });

  // ── Test: Multiple subscriptions ──
  it("should handle multiple concurrent subscriptions", async () => {
    const transfers: DecodedEventLog[] = [];
    const approvals: DecodedEventLog[] = [];

    const handle1 = await manager.subscribeToEvents(
      CONTRACT,
      TRANSFER_EVENT,
      (log) => transfers.push(log)
    );
    const handle2 = await manager.subscribeToEvents(
      CONTRACT,
      APPROVAL_EVENT,
      (log) => approvals.push(log)
    );

    expect(manager.getActiveSubscriptionCount()).toBe(2);

    // Simulate Transfer log
    mock.simulateLog(handle1.subscriptionId, {
      address: CONTRACT,
      topics: [
        computeEventTopic(TRANSFER_EVENT),
        "0x" + "11".repeat(32),
        "0x" + "22".repeat(32),
      ],
      data: "0x" + BigInt(100).toString(16).padStart(64, "0"),
      blockNumber: "0x1",
      transactionHash: null,
      logIndex: null,
    });

    // Simulate Approval log
    mock.simulateLog(handle2.subscriptionId, {
      address: CONTRACT,
      topics: [
        computeEventTopic(APPROVAL_EVENT),
        "0x" + "33".repeat(32),
        "0x" + "44".repeat(32),
      ],
      data: "0x" + BigInt(500).toString(16).padStart(64, "0"),
      blockNumber: "0x2",
      transactionHash: null,
      logIndex: null,
    });

    expect(transfers.length).toBe(1);
    expect(transfers[0].event).toBe("Transfer");
    expect(approvals.length).toBe(1);
    expect(approvals[0].event).toBe("Approval");
  });
});
