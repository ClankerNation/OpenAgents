/**
 * @fix-author scotia1973-bot
 *
 * Tests for the event subscription and decoding module (bounty #196).
 *
 * Tests cover:
 * - Event signature and hash computation
 * - Single and multiple event log decoding
 * - Indexed and non-indexed parameter decoding
 * - Dynamic types (string, bytes) from log data
 * - Event filtering (by name, by address)
 * - Subscription manager construction and lifecycle
 * - Error cases (missing topics, mismatched signature)
 * - Edge cases (zero values, empty data, addresses)
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import {
  decodeEventLog,
  decodeEventLogs,
  filterEventsByName,
  filterEventsByAddress,
  findEventByName,
  eventSignature,
  eventSignatureHash,
  buildEventMap,
  type AbiEvent,
  type DecodedEvent,
  type LogEntry,
} from "../src/events/decoder";
import {
  EventSubscriptionManager,
  createEventFilter,
} from "../src/events/subscription";

// ── Test fixtures ───────────────────────────────────────────────────────────

const TRANSFER_EVENT: AbiEvent = {
  type: "event",
  name: "Transfer",
  inputs: [
    { name: "from", type: "address", indexed: true },
    { name: "to", type: "address", indexed: true },
    { name: "value", type: "uint256", indexed: false },
  ],
};

const APPROVAL_EVENT: AbiEvent = {
  type: "event",
  name: "Approval",
  inputs: [
    { name: "owner", type: "address", indexed: true },
    { name: "spender", type: "address", indexed: true },
    { name: "value", type: "uint256", indexed: false },
  ],
};

const TASK_CREATED_EVENT: AbiEvent = {
  type: "event",
  name: "TaskCreated",
  inputs: [
    { name: "taskId", type: "uint256", indexed: true },
    { name: "creator", type: "address", indexed: true },
    { name: "description", type: "string", indexed: false },
    { name: "reward", type: "uint256", indexed: false },
  ],
};

const BOOL_EVENT: AbiEvent = {
  type: "event",
  name: "StatusChanged",
  inputs: [
    { name: "active", type: "bool", indexed: true },
    { name: "count", type: "uint256", indexed: false },
  ],
};

const ALL_ABIS: readonly AbiEvent[] = [
  TRANSFER_EVENT,
  APPROVAL_EVENT,
  TASK_CREATED_EVENT,
  BOOL_EVENT,
];

// Helper: create a minimal LogEntry for testing
function makeLog(
  address: string,
  eventAbi: AbiEvent,
  indexedValues: string[],
  dataHex: string,
  overrides: Partial<LogEntry> = {}
): LogEntry {
  const inputTypes = eventAbi.inputs.map((i) => i.type);
  const sigHash = eventSignatureHash(eventAbi.name, inputTypes);

  const topics = [sigHash];
  for (const val of indexedValues) {
    topics.push(val);
  }

  return {
    address,
    topics,
    data: dataHex,
    blockNumber: "0x1",
    transactionHash: "0xabc",
    logIndex: "0x0",
    blockHash: "0xblock",
    ...overrides,
  };
}

function addressTopic(addr: string): string {
  const clean = addr.startsWith("0x") ? addr.slice(2) : addr;
  return "0x" + clean.toLowerCase().padStart(64, "0");
}

function uint256Topic(value: bigint | number): string {
  return "0x" + BigInt(value).toString(16).padStart(64, "0");
}

// ── Tests ───────────────────────────────────────────────────────────────────

describe("Event Signature Utilities", () => {
  it("should compute event signature string", () => {
    expect(eventSignature("Transfer", ["address", "address", "uint256"])).toBe(
      "Transfer(address,address,uint256)"
    );
  });

  it("should compute event signature hash", () => {
    const hash = eventSignatureHash("Transfer", [
      "address",
      "address",
      "uint256",
    ]);
    expect(hash).toBeTruthy();
    expect(hash.startsWith("0x")).toBe(true);
    expect(hash.length).toBe(66); // 0x + 64 hex chars
  });

  it("should produce consistent hashes", () => {
    const h1 = eventSignatureHash("Transfer", ["address", "address", "uint256"]);
    const h2 = eventSignatureHash("Transfer", ["address", "address", "uint256"]);
    expect(h1).toBe(h2);
  });

  it("should build event map from ABIs", () => {
    const map = buildEventMap(ALL_ABIS);
    expect(map.size).toBe(4);

    const transferHash = eventSignatureHash("Transfer", [
      "address",
      "address",
      "uint256",
    ]);
    expect(map.has(transferHash)).toBe(true);
    expect(map.get(transferHash)?.name).toBe("Transfer");
  });
});

describe("decodeEventLog", () => {
  it("should decode a Transfer event with indexed addresses and uint256 value", () => {
    const from = "0x1234567890abcdef1234567890abcdef12345678";
    const to = "0xabcdef1234567890abcdef1234567890abcdef12";

    const log = makeLog(
      "0xContract",
      TRANSFER_EVENT,
      [addressTopic(from), addressTopic(to)],
      uint256Topic(1000n)
    );

    const decoded = decodeEventLog(TRANSFER_EVENT, log);

    expect(decoded.name).toBe("Transfer");
    expect(decoded.address).toBe("0xContract");
    expect(decoded.blockNumber).toBe(1);
    expect(decoded.transactionHash).toBe("0xabc");
    expect(decoded.args.from).toBe(from.toLowerCase());
    expect(decoded.args.to).toBe(to.toLowerCase());
    expect(decoded.args.value).toBe(1000n);
  });

  it("should decode a TaskCreated event with string description", () => {
    const taskId = uint256Topic(42n);
    const creator = addressTopic("0xdeadbeefdeadbeefdeadbeefdeadbeefdeadbeef");

    // For event data, ABI-encoding of (string, uint256) uses abi.encode:
    // offset(32) of string pointer | reward(32) | string_length(32) | string_data(padded)
    // The string offset points to position 64 (0x40) since there are 2 static slots (64 bytes)
    const desc = "Process data";
    const descHex = Buffer.from(desc).toString("hex");
    const descLen = descHex.length / 2;
    const paddedLen = Math.ceil(descLen / 32) * 32;
    const dataHex =
      "0x" +
      // offset to string data (0x40 = 64 bytes from start, past two 32-byte static slots)
      "0000000000000000000000000000000000000000000000000000000000000040" +
      // reward (uint256 second non-indexed param, inline)
      BigInt(500).toString(16).padStart(64, "0") +
      // length of string
      BigInt(descLen).toString(16).padStart(64, "0") +
      // string data padded to 32 bytes
      descHex.padEnd(paddedLen * 2, "0");

    const log = makeLog(
      "0xTaskRouter",
      TASK_CREATED_EVENT,
      [taskId, creator],
      dataHex
    );

    const decoded = decodeEventLog(TASK_CREATED_EVENT, log);
    expect(decoded.name).toBe("TaskCreated");
    expect(decoded.args.taskId).toBe(42n);
    expect(decoded.args.creator).toBe(
      "0xdeadbeefdeadbeefdeadbeefdeadbeefdeadbeef"
    );
    expect(decoded.args.description).toBe(desc);
    expect(decoded.args.reward).toBe(500n);
  });

  it("should decode a bool indexed parameter", () => {
    const activeTopic = "0x" + "0".repeat(63) + "1"; // true

    const log = makeLog(
      "0xContract",
      BOOL_EVENT,
      [activeTopic],
      "0x" + BigInt(99).toString(16).padStart(64, "0")
    );

    const decoded = decodeEventLog(BOOL_EVENT, log);
    expect(decoded.args.active).toBe(true);
    expect(decoded.args.count).toBe(99n);
  });

  it("should throw on signature hash mismatch", () => {
    const log = makeLog(
      "0xContract",
      TRANSFER_EVENT,
      [addressTopic("0x1234"), addressTopic("0x5678")],
      uint256Topic(100n)
    );
    // Use Approval event's ABI — different signature hash
    expect(() => decodeEventLog(APPROVAL_EVENT, log)).toThrow(
      /Event signature mismatch/
    );
  });

  it("should throw on missing topics for indexed params", () => {
    // Use the correct event signature hash so we pass the hash check
    const transferHash = eventSignatureHash("Transfer", ["address", "address", "uint256"]);
    const log: LogEntry = {
      address: "0xContract",
      topics: [transferHash], // Only topic[0], no indexed params
      data: "0x",
      blockNumber: "0x1",
      transactionHash: "0xabc",
      logIndex: "0x0",
    };

    expect(() => decodeEventLog(TRANSFER_EVENT, log)).toThrow(
      /Missing topic for indexed parameter/
    );
  });

  it("should handle zero value uint256", () => {
    const from = "0x1111111111111111111111111111111111111111";
    const to = "0x2222222222222222222222222222222222222222";

    const log = makeLog(
      "0xContract",
      TRANSFER_EVENT,
      [addressTopic(from), addressTopic(to)],
      "0x" + "0".repeat(64) // zero value
    );

    const decoded = decodeEventLog(TRANSFER_EVENT, log);
    expect(decoded.args.value).toBe(0n);
  });
});

describe("decodeEventLogs (batch)", () => {
  it("should decode multiple logs from a receipt", () => {
    const from = "0x1111111111111111111111111111111111111111";
    const to = "0x2222222222222222222222222222222222222222";

    const logs: LogEntry[] = [
      makeLog(
        "0xToken",
        TRANSFER_EVENT,
        [addressTopic(from), addressTopic(to)],
        uint256Topic(500n)
      ),
      makeLog(
        "0xToken",
        APPROVAL_EVENT,
        [addressTopic(from), addressTopic(to)],
        uint256Topic(1000n)
      ),
    ];

    const decoded = decodeEventLogs(ALL_ABIS, logs);
    expect(decoded).toHaveLength(2);
    expect(decoded[0].name).toBe("Transfer");
    expect(decoded[1].name).toBe("Approval");
  });

  it("should skip unknown events gracefully", () => {
    const log = makeLog(
      "0xToken",
      TRANSFER_EVENT,
      [addressTopic("0x1111"), addressTopic("0x2222")],
      uint256Topic(100n)
    );
    // Use a different signature by hacking the topic
    const badLog: LogEntry = {
      ...log,
      topics: ["0x" + "deadbeef".padStart(64, "0")],
    };

    const decoded = decodeEventLogs(ALL_ABIS, [badLog]);
    expect(decoded).toHaveLength(0);
  });

  it("should throw on unknown event in strict mode", () => {
    const log = makeLog(
      "0xToken",
      TRANSFER_EVENT,
      [addressTopic("0x1111"), addressTopic("0x2222")],
      uint256Topic(100n)
    );
    const badLog: LogEntry = {
      ...log,
      topics: ["0x" + "deadbeef".padStart(64, "0")],
    };

    expect(() =>
      decodeEventLogs(ALL_ABIS, [badLog], { strict: true })
    ).toThrow(/No ABI event definition/);
  });
});

describe("Event Filtering", () => {
  let decodedEvents: DecodedEvent[];

  beforeEach(() => {
    const from = "0x1111111111111111111111111111111111111111";
    const to = "0x2222222222222222222222222222222222222222";

    decodedEvents = [
      decodeEventLog(
        TRANSFER_EVENT,
        makeLog("0xTokenA", TRANSFER_EVENT, [addressTopic(from), addressTopic(to)], uint256Topic(100n))
      ),
      decodeEventLog(
        TRANSFER_EVENT,
        makeLog("0xTokenB", TRANSFER_EVENT, [addressTopic(to), addressTopic(from)], uint256Topic(200n))
      ),
      decodeEventLog(
        APPROVAL_EVENT,
        makeLog("0xTokenA", APPROVAL_EVENT, [addressTopic(from), addressTopic(to)], uint256Topic(500n))
      ),
    ];
  });

  it("filterEventsByName should return only matching events", () => {
    const transfers = filterEventsByName(decodedEvents, "Transfer");
    expect(transfers).toHaveLength(2);
    expect(transfers.every((e) => e.name === "Transfer")).toBe(true);
  });

  it("filterEventsByAddress should return only matching address events", () => {
    const tokenAEvents = filterEventsByAddress(decodedEvents, "0xTokenA");
    expect(tokenAEvents).toHaveLength(2);
    expect(tokenAEvents.every((e) => e.address === "0xTokenA")).toBe(true);
  });

  it("findEventByName should return the first match", () => {
    const found = findEventByName(decodedEvents, "Approval");
    expect(found).toBeDefined();
    expect(found!.name).toBe("Approval");
  });

  it("findEventByName should return undefined for non-existent event", () => {
    const found = findEventByName(decodedEvents, "NonExistent");
    expect(found).toBeUndefined();
  });
});

describe("EventSubscriptionManager", () => {
  let manager: EventSubscriptionManager;
  let mockProvider: any;

  beforeEach(() => {
    mockProvider = {
      getBlockNumber: vi.fn().mockResolvedValue(100),
      on: vi.fn(),
      off: vi.fn(),
    } as any;

    manager = new EventSubscriptionManager(mockProvider, {
      abis: ALL_ABIS,
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("should construct with provider and ABIs", () => {
    expect(manager).toBeInstanceOf(EventSubscriptionManager);
    expect(manager.getSubscriptionCount()).toBe(0);
  });

  it("should track polling state", () => {
    const state = manager.getPollingState();
    expect(state.active).toBe(false);
    expect(state.intervalMs).toBe(4000);
  });

  it("should start and stop polling", () => {
    manager.startPolling(2000);
    let state = manager.getPollingState();
    expect(state.active).toBe(true);
    expect(state.intervalMs).toBe(2000);

    manager.stopPolling();
    state = manager.getPollingState();
    expect(state.active).toBe(false);
  });

  it("should subscribe and return a subscription handle", async () => {
    // Mock ethers Contract
    const mockContract = {
      on: vi.fn(),
      off: vi.fn(),
      removeAllListeners: vi.fn(),
      target: "0xContract",
      interface: {} as any,
    };

    // Mock EventSubscriptionManager's getOrCreateContract
    vi.spyOn(manager as any, "getOrCreateContract").mockReturnValue(mockContract);

    const callback = vi.fn();
    const sub = await manager.subscribe(
      "0xContract",
      [TRANSFER_EVENT],
      "Transfer",
      callback
    );

    expect(sub.id).toBeTruthy();
    expect(sub.eventName).toBe("Transfer");
    expect(sub.contractAddress).toBe("0xContract");
    expect(typeof sub.remove).toBe("function");
    expect(manager.getSubscriptionCount()).toBe(1);
  });

  it("should unsubscribe and reduce subscription count", async () => {
    const mockContract = {
      on: vi.fn(),
      off: vi.fn(),
      removeAllListeners: vi.fn(),
      target: "0xContract",
      interface: {} as any,
    };

    vi.spyOn(manager as any, "getOrCreateContract").mockReturnValue(mockContract);

    const callback = vi.fn();
    const sub = await manager.subscribe(
      "0xContract",
      [TRANSFER_EVENT],
      "Transfer",
      callback
    );

    expect(manager.getSubscriptionCount()).toBe(1);
    sub.remove();
    expect(manager.getSubscriptionCount()).toBe(0);
  });

  it("should get active subscriptions list", async () => {
    const mockContract = {
      on: vi.fn(),
      off: vi.fn(),
      removeAllListeners: vi.fn(),
      target: "0xContract",
      interface: {} as any,
    };

    vi.spyOn(manager as any, "getOrCreateContract").mockReturnValue(mockContract);

    const callback = vi.fn();
    await manager.subscribe("0xContract", [TRANSFER_EVENT], "Transfer", callback);
    await manager.subscribe("0xContract", [APPROVAL_EVENT], "Approval", callback);

    const subs = manager.getActiveSubscriptions();
    expect(subs).toHaveLength(2);
  });

  it("unsubscribeAll should clear all subscriptions", async () => {
    const mockContract = {
      on: vi.fn(),
      off: vi.fn(),
      removeAllListeners: vi.fn(),
      target: "0xContract",
      interface: {} as any,
    };

    vi.spyOn(manager as any, "getOrCreateContract").mockReturnValue(mockContract);

    const callback = vi.fn();
    await manager.subscribe("0xContract", [TRANSFER_EVENT], "Transfer", callback);
    await manager.subscribe("0xContract", [APPROVAL_EVENT], "Approval", callback);

    expect(manager.getSubscriptionCount()).toBe(2);
    await manager.unsubscribeAll();
    expect(manager.getSubscriptionCount()).toBe(0);
  });

  it("should decode transaction logs from raw ethers Log entries", () => {
    const from = "0x1111111111111111111111111111111111111111";
    const to = "0x2222222222222222222222222222222222222222";

    const transferHash = eventSignatureHash("Transfer", ["address", "address", "uint256"]);

    const mockLogs = [
      {
        address: "0xToken",
        topics: [
          transferHash,
          addressTopic(from),
          addressTopic(to),
        ],
        data: uint256Topic(500n),
        blockNumber: 1,
        transactionHash: "0xabc",
        index: 0,
        blockHash: "0xblock",
        transactionIndex: 0,
        removed: false,
      },
    ];

    const decoded = manager.decodeTransactionLogs(mockLogs as any);
    expect(decoded).toHaveLength(1);
    expect(decoded[0].name).toBe("Transfer");
    expect(decoded[0].args.value).toBe(500n);
  });
});

describe("createEventFilter", () => {
  it("should create a filter with the correct event signature hash", () => {
    const filter = createEventFilter("0xToken", TRANSFER_EVENT);
    expect(filter.address).toBe("0xToken");
    expect(filter.topics).toHaveLength(1);
    expect(filter.topics[0]).toBe(
      eventSignatureHash("Transfer", ["address", "address", "uint256"])
    );
  });

  it("should include indexed parameter filters", () => {
    const from = "0x1234567890abcdef1234567890abcdef12345678";
    const filter = createEventFilter("0xToken", TRANSFER_EVENT, {
      0: addressTopic(from), // filter by 'from' (first indexed param)
    });
    expect(filter.topics).toHaveLength(3); // [sigHash, fromPadded, null-for-to]
    expect(filter.topics[1]).toBe(addressTopic(from));
  });
});
