import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { ethers } from "ethers";
import { OpenAgentsSDK, DecodedEvent, _internal } from "./index";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeConfig(overrides: Record<string, any> = {}) {
  return {
    name: "test-agent",
    endpoint: "https://test.example",
    privateKey:
      "0x0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
    rpcUrl: "http://localhost:8545",
    registryAddress: "0x1234567890123456789012345678901234567890",
    routerAddress: "0x1234567890123456789012345678901234567999",
    ...overrides,
  };
}

/** Build a fake ethers.Log from a parsed event via an interface. */
function makeEventLog(
  iface: ethers.Interface,
  eventName: string,
  values: any[],
  overrides: Partial<ethers.Log> = {}
): ethers.Log {
  const encoded = iface.encodeEventLog(eventName, values);
  return {
    address: overrides.address ?? "0x1234567890123456789012345678901234567890",
    blockNumber: overrides.blockNumber ?? 42,
    transactionHash:
      overrides.transactionHash ??
      "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    index: overrides.index ?? 0,
    removed: false,
    data: encoded.data,
    topics: encoded.topics as string[],
    provider: {} as any,
  } as unknown as ethers.Log;
}

// ---------------------------------------------------------------------------
// Test suite
// ---------------------------------------------------------------------------

describe("OpenAgentsSDK.subscribeToEvents", () => {
  let originalCreateContract: typeof _internal.createContract;
  let originalCreateWSProvider: typeof _internal.createWebSocketProvider;

  beforeEach(() => {
    originalCreateContract = _internal.createContract;
    originalCreateWSProvider = _internal.createWebSocketProvider;
  });

  afterEach(() => {
    vi.restoreAllMocks();
    _internal.createContract = originalCreateContract;
    _internal.createWebSocketProvider = originalCreateWSProvider;
  });

  // -----------------------------------------------------------------------
  // 1. Subscribe and receive event
  // -----------------------------------------------------------------------
  it("should subscribe and receive a decoded event", () => {
    let capturedHandler: ((log: ethers.Log) => void) | null = null;

    const fakeUnsub = vi.fn();
    const fakeContract = {
      on: vi.fn((_filter: any, handler: (log: ethers.Log) => void) => {
        capturedHandler = handler;
      }),
      off: vi.fn(),
      filters: {
        AgentRegistered: (...args: any[]) => ({ eventTopic: "AgentRegistered", args }),
      },
    };

    // Inject fake dependencies
    _internal.createContract = vi.fn().mockReturnValue(fakeContract);
    // Force fallback to polling (no WS)
    _internal.createWebSocketProvider = vi.fn().mockImplementation(() => {
      throw new Error("No WebSocket available for test");
    });

    const sdk = new OpenAgentsSDK(makeConfig());
    const receivedEvents: DecodedEvent[] = [];

    const unsub = sdk.subscribeToEvents(
      "0x1234567890123456789012345678901234567890",
      "AgentRegistered",
      (event) => receivedEvents.push(event)
    );

    // Build a realistic AgentRegistered event
    const iface = new ethers.Interface([
      "event AgentRegistered(bytes32 indexed agentId, address indexed owner, string name)"
    ]);
    const agentId = ethers.id("test-agent");
    const owner = "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266";

    const fakeLog = makeEventLog(iface, "AgentRegistered", [agentId, owner, "test-agent-name"], {
      blockNumber: 100,
      transactionHash: "0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
      index: 3,
    });

    // Simulate an event being emitted
    expect(capturedHandler).not.toBeNull();
    capturedHandler!(fakeLog);

    expect(receivedEvents).toHaveLength(1);
    expect(receivedEvents[0].name).toBe("AgentRegistered");
    expect(receivedEvents[0].blockNumber).toBe(100);
    expect(receivedEvents[0].transactionHash).toBe(
      "0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
    );
    expect(receivedEvents[0].logIndex).toBe(3);
    expect(receivedEvents[0].args.name).toBe("test-agent-name");
    expect(receivedEvents[0].args).toHaveProperty("agentId");
    expect(receivedEvents[0].args).toHaveProperty("owner");

    unsub();
  });

  // -----------------------------------------------------------------------
  // 2. Filter by indexed parameter
  // -----------------------------------------------------------------------
  it("should pass indexed parameter filters to the contract filter", () => {
    const filterSpy = vi.fn((...args: any[]) => ({
      eventTopic: "AgentRegistered",
      args,
    }));
    const fakeContract = {
      on: vi.fn(),
      off: vi.fn(),
      filters: {
        AgentRegistered: filterSpy,
      },
    };

    _internal.createContract = vi.fn().mockReturnValue(fakeContract);
    _internal.createWebSocketProvider = vi.fn().mockImplementation(() => {
      throw new Error("No WebSocket available for test");
    });

    const sdk = new OpenAgentsSDK(makeConfig());
    const specificAgentId = ethers.id("my-agent");

    const unsub = sdk.subscribeToEvents(
      "0x1234567890123456789012345678901234567890",
      "AgentRegistered",
      () => {},
      { agentId: specificAgentId }
    );

    // The Contract filter function should have been called with the agentId as first indexed arg
    expect(filterSpy).toHaveBeenCalled();
    expect(filterSpy.mock.calls[0][0]).toBe(specificAgentId);

    unsub();
  });

  // -----------------------------------------------------------------------
  // 3. Reconnect on disconnect
  // -----------------------------------------------------------------------
  it("should attempt to reconnect when WebSocket disconnects", async () => {
    vi.useFakeTimers();

    let wsCreatedCount = 0;
    let closeCallback: (() => void) | null = null;
    let offCallCount = 0;

    const fakeContract = {
      on: vi.fn(),
      off: vi.fn(() => { offCallCount++; }),
      filters: {
        AgentRegistered: (...args: any[]) => ({ eventTopic: "AgentRegistered", args }),
      },
    };

    _internal.createContract = vi.fn().mockReturnValue(fakeContract);
    _internal.createWebSocketProvider = vi.fn().mockImplementation(() => {
      wsCreatedCount++;
      const provider = {
        on: vi.fn((event: string, handler: any) => {
          if (event === "close") {
            closeCallback = handler;
          }
        }),
        destroy: vi.fn(),
      };
      return provider;
    });

    const sdk = new OpenAgentsSDK(makeConfig({ wsUrl: "ws://localhost:8546" }));

    const unsub = sdk.subscribeToEvents(
      "0x1234567890123456789012345678901234567890",
      "AgentRegistered",
      () => {}
    );

    // Initial WebSocket provider should have been created
    const initialCount = wsCreatedCount;
    expect(initialCount).toBeGreaterThanOrEqual(1);

    // Simulate WebSocket close
    expect(closeCallback).not.toBeNull();
    
    // Reset close callback and trigger disconnect
    closeCallback!();

    // Advance timers for exponential backoff
    vi.advanceTimersByTime(3000);

    // Should have attempted at least one more connection
    expect(wsCreatedCount).toBeGreaterThan(initialCount);

    unsub();
    vi.useRealTimers();
  });

  // -----------------------------------------------------------------------
  // 4. Unsubscribe stops listening
  // -----------------------------------------------------------------------
  it("should stop listening after unsubscribe is called", () => {
    const offSpy = vi.fn();

    const fakeContract = {
      on: vi.fn(),
      off: offSpy,
      filters: {
        AgentRegistered: (...args: any[]) => ({ eventTopic: "AgentRegistered", args }),
        AgentDeactivated: (...args: any[]) => ({ eventTopic: "AgentDeactivated", args }),
        ReputationUpdated: (...args: any[]) => ({ eventTopic: "ReputationUpdated", args }),
      },
    };

    _internal.createContract = vi.fn().mockReturnValue(fakeContract);
    _internal.createWebSocketProvider = vi.fn().mockImplementation(() => {
      throw new Error("No WebSocket available for test");
    });

    const sdk = new OpenAgentsSDK(makeConfig());
    const receivedEvents: DecodedEvent[] = [];

    const unsub = sdk.subscribeToEvents(
      "0x1234567890123456789012345678901234567890",
      "AgentRegistered",
      (event) => receivedEvents.push(event)
    );

    // Unsubscribe
    unsub();

    // Contract.off should have been called to clean up the listener
    expect(offSpy).toHaveBeenCalled();
  });

  // -----------------------------------------------------------------------
  // 5. Throw on unknown event
  // -----------------------------------------------------------------------
  it("should throw an error for unknown event names", () => {
    const sdk = new OpenAgentsSDK(makeConfig());
    expect(() => {
      sdk.subscribeToEvents(
        "0x1234567890123456789012345678901234567890",
        "UnknownEvent",
        () => {}
      );
    }).toThrow("Unknown event: UnknownEvent");
  });
});