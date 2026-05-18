/**
 * @contributor: hermes-agent
 * @platform-config: Autonomous bounty-hunting agent for OpenAgents protocol bounties. Zero-capital, self-directed, no human intervention.
 * @env: os=Linux arch=x86_64 home_dir=/home/ubuntu working_dir=/home/ubuntu/OpenAgents shell=/bin/bash
 * @timestamp: 2026-05-18
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { RpcProvider, BatchResult } from "./rpc";

// Helper to create a mock fetch that returns given responses
function mockFetch(responses: unknown) {
  const mock = vi.fn().mockResolvedValue({
    ok: true,
    status: 200,
    json: () => Promise.resolve(responses),
  });
  vi.stubGlobal("fetch", mock);
  return mock;
}

// Helper to create a provider with default config
function createProvider(overrides: Record<string, unknown> = {}) {
  return new RpcProvider({
    url: "http://localhost:8545",
    chainId: 1,
    ...overrides,
  });
}

describe("RpcProvider - BatchResult API", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("returns BatchResult objects with success/value for all-succeeded batch", async () => {
    const responses = [
      { jsonrpc: "2.0", id: 1, result: "0x1" },
      { jsonrpc: "2.0", id: 2, result: "0x2" },
      { jsonrpc: "2.0", id: 3, result: "0x3" },
    ];
    mockFetch(responses);

    const provider = createProvider();
    const results = await provider.batchCall([
      { method: "eth_blockNumber", params: [] },
      { method: "eth_blockNumber", params: [] },
      { method: "eth_blockNumber", params: [] },
    ]);

    expect(results).toHaveLength(3);
    for (const r of results) {
      expect(r.success).toBe(true);
      expect(r.error).toBeUndefined();
    }
    expect(results[0].value).toBe("0x1");
    expect(results[1].value).toBe("0x2");
    expect(results[2].value).toBe("0x3");
  });

  it("returns BatchResult with error for partial failures (abortOnError=false)", async () => {
    const responses = [
      { jsonrpc: "2.0", id: 1, result: "0x1" },
      { jsonrpc: "2.0", id: 2, error: { code: -32000, message: "Server error" } },
      { jsonrpc: "2.0", id: 3, result: "0x3" },
    ];
    mockFetch(responses);

    const provider = createProvider();
    const results = await provider.batchCall(
      [
        { method: "method1", params: [] },
        { method: "method2", params: [] },
        { method: "method3", params: [] },
      ],
      { abortOnError: false }
    );

    expect(results).toHaveLength(3);
    expect(results[0].success).toBe(true);
    expect(results[0].value).toBe("0x1");

    expect(results[1].success).toBe(false);
    expect(results[1].error).toBeInstanceOf(Error);
    expect(results[1].error!.message).toContain("-32000");

    expect(results[2].success).toBe(true);
    expect(results[2].value).toBe("0x3");
  });

  it("throws aggregated error when abortOnError=true and partial failure occurs", async () => {
    const responses = [
      { jsonrpc: "2.0", id: 1, result: "0x1" },
      { jsonrpc: "2.0", id: 2, error: { code: -32000, message: "Server error" } },
    ];
    mockFetch(responses);

    const provider = createProvider();
    await expect(
      provider.batchCall(
        [
          { method: "method1", params: [] },
          { method: "method2", params: [] },
        ],
        { abortOnError: true }
      )
    ).rejects.toThrow("Batch partial failure");
  });
});

describe("RpcProvider - Shuffled response order", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("correctly maps results by ID even when responses arrive out of order", async () => {
    // Responses arrive in reverse order of request IDs
    const responses = [
      { jsonrpc: "2.0", id: 3, result: "0xccc" },
      { jsonrpc: "2.0", id: 1, result: "0xaaa" },
      { jsonrpc: "2.0", id: 2, result: "0xbbb" },
    ];
    mockFetch(responses);

    const provider = createProvider();
    const results = await provider.batchCall([
      { method: "method_a", params: [] },
      { method: "method_b", params: [] },
      { method: "method_c", params: [] },
    ]);

    expect(results).toHaveLength(3);
    // Results should be in the order of the original calls, not the shuffled response order
    expect(results[0].success).toBe(true);
    expect(results[0].value).toBe("0xaaa");
    expect(results[1].success).toBe(true);
    expect(results[1].value).toBe("0xbbb");
    expect(results[2].success).toBe(true);
    expect(results[2].value).toBe("0xccc");
  });

  it("handles completely random shuffled response order", async () => {
    // 5 requests, responses in shuffled order
    const responses = [
      { jsonrpc: "2.0", id: 5, result: "e" },
      { jsonrpc: "2.0", id: 2, result: "b" },
      { jsonrpc: "2.0", id: 4, result: "d" },
      { jsonrpc: "2.0", id: 1, result: "a" },
      { jsonrpc: "2.0", id: 3, result: "c" },
    ];
    mockFetch(responses);

    const provider = createProvider();
    const results = await provider.batchCall([
      { method: "m1", params: [] },
      { method: "m2", params: [] },
      { method: "m3", params: [] },
      { method: "m4", params: [] },
      { method: "m5", params: [] },
    ]);

    expect(results).toHaveLength(5);
    expect(results[0].value).toBe("a");
    expect(results[1].value).toBe("b");
    expect(results[2].value).toBe("c");
    expect(results[3].value).toBe("d");
    expect(results[4].value).toBe("e");
  });
});

describe("RpcProvider - Invalid response IDs", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("throws when response contains an unknown ID that doesn't match any request", async () => {
    const responses = [
      { jsonrpc: "2.0", id: 1, result: "0x1" },
      { jsonrpc: "2.0", id: 999, result: "orphan" }, // unknown ID
    ];
    mockFetch(responses);

    const provider = createProvider();
    await expect(
      provider.batchCall([
        { method: "method1", params: [] },
      ])
    ).rejects.toThrow("unknown id");
  });

  it("handles response with valid and invalid IDs mixed", async () => {
    const responses = [
      { jsonrpc: "2.0", id: 1, result: "0x1" },
      { jsonrpc: "2.0", id: 42, result: "invalid" },
    ];
    mockFetch(responses);

    const provider = createProvider();
    await expect(
      provider.batchCall([
        { method: "method1", params: [] },
        { method: "method2", params: [] },
      ])
    ).rejects.toThrow("unknown id");
  });
});

describe("RpcProvider - Per-request timeout", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.restoreAllMocks();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it("marks a request as timed out if it exceeds perRequestTimeout", async () => {
    const provider = createProvider({ perRequestTimeout: 5000 });

    const responses = [
      { jsonrpc: "2.0", id: 1, result: "0x1" },
    ];

    let currentTime = 1000000;
    vi.spyOn(Date, "now").mockImplementation(() => currentTime);

    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation(async () => {
        // Simulate that the fetch took longer than perRequestTimeout
        currentTime += 6000; // 6 seconds elapsed, exceeds 5000ms limit
        return {
          ok: true,
          status: 200,
          json: () => Promise.resolve(responses),
        };
      })
    );

    const results = await provider.batchCall([
      { method: "method1", params: [] },
    ]);

    expect(results).toHaveLength(1);
    expect(results[0].success).toBe(false);
    expect(results[0].error!.message).toContain("timeout");

    vi.restoreAllMocks();
  });

  it("uses default perRequestTimeout of 15000ms when not specified", () => {
    const provider = createProvider();
    expect((provider as any).perRequestTimeout).toBe(15000);
  });

  it("uses custom perRequestTimeout when specified", () => {
    const provider = createProvider({ perRequestTimeout: 5000 });
    expect((provider as any).perRequestTimeout).toBe(5000);
  });
});

describe("RpcProvider - Batch call basics", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("returns empty array for empty batch", async () => {
    const provider = createProvider();
    const results = await provider.batchCall([]);
    expect(results).toEqual([]);
  });

  it("throws if batch exceeds maxBatchSize", async () => {
    const provider = createProvider({ maxBatchSize: 2 });
    await expect(
      provider.batchCall([
        { method: "m1", params: [] },
        { method: "m2", params: [] },
        { method: "m3", params: [] },
      ])
    ).rejects.toThrow("exceeds max");
  });

  it("throws when batch response is not valid JSON", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: () => Promise.reject(new Error("Invalid JSON")),
      })
    );

    const provider = createProvider();
    await expect(
      provider.batchCall([{ method: "test", params: [] }])
    ).rejects.toThrow("not valid JSON");
  });

  it("throws when batch response is not an array", async () => {
    mockFetch({ jsonrpc: "2.0", id: 1, result: "0x1" });

    const provider = createProvider();
    await expect(
      provider.batchCall([{ method: "test", params: [] }])
    ).rejects.toThrow("must be an array");
  });

  it("marks requests with no matching response as failed", async () => {
    // Response only has id:1 but we sent two requests (id:1 and id:2)
    const responses = [
      { jsonrpc: "2.0", id: 1, result: "0x1" },
      // id:2 is missing from response
    ];
    mockFetch(responses);

    const provider = createProvider();
    const results = await provider.batchCall([
      { method: "m1", params: [] },
      { method: "m2", params: [] },
    ]);

    expect(results).toHaveLength(2);
    expect(results[0].success).toBe(true);
    expect(results[0].value).toBe("0x1");

    expect(results[1].success).toBe(false);
    expect(results[1].error).toBeInstanceOf(Error);
    expect(results[1].error!.message).toContain("No response received");
  });
});

describe("RpcProvider - Retry individual failed batch requests", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("retries failed requests and succeeds on second attempt", async () => {
    let callCount = 0;
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation(async () => {
        callCount++;
        if (callCount === 1) {
          return {
            ok: true,
            status: 200,
            json: () =>
              Promise.resolve([
                { jsonrpc: "2.0", id: 1, result: "0x1" },
                { jsonrpc: "2.0", id: 2, error: { code: -32000, message: "temp error" } },
              ]),
          };
        }
        // Second call: retry for id:2 succeeds
        return {
          ok: true,
          status: 200,
          json: () =>
            Promise.resolve([
              { jsonrpc: "2.0", id: 3, result: "0x2" },
            ]),
        };
      })
    );

    const provider = createProvider();
    const results = await provider.batchCall(
      [
        { method: "m1", params: [] },
        { method: "m2", params: [] },
      ],
      { retryCount: 1, retryBaseDelayMs: 1 }
    );

    expect(results).toHaveLength(2);
    expect(results[0].success).toBe(true);
    expect(results[0].value).toBe("0x1");
    expect(results[1].success).toBe(true);
    expect(results[1].value).toBe("0x2");
    expect(callCount).toBe(2);
  });

  it("retries failed requests and still fails after exhausting retries", async () => {
    let callCount = 0;
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation(async () => {
        callCount++;
        if (callCount === 1) {
          return {
            ok: true,
            status: 200,
            json: () =>
              Promise.resolve([
                { jsonrpc: "2.0", id: 1, result: "0x1" },
                { jsonrpc: "2.0", id: 2, error: { code: -32000, message: "persistent error" } },
              ]),
          };
        }
        // Second call: retry still fails
        return {
          ok: true,
          status: 200,
          json: () =>
            Promise.resolve([
              { jsonrpc: "2.0", id: 3, error: { code: -32000, message: "still failing" } },
            ]),
        };
      })
    );

    const provider = createProvider();
    const results = await provider.batchCall(
      [
        { method: "m1", params: [] },
        { method: "m2", params: [] },
      ],
      { retryCount: 1, retryBaseDelayMs: 1 }
    );

    expect(results).toHaveLength(2);
    expect(results[0].success).toBe(true);
    expect(results[0].value).toBe("0x1");
    expect(results[1].success).toBe(false);
    expect(results[1].error!.message).toContain("still failing");
  });

  it("does not retry when retryCount is 0 (default)", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: () =>
          Promise.resolve([
            { jsonrpc: "2.0", id: 1, result: "0x1" },
            { jsonrpc: "2.0", id: 2, error: { code: -32000, message: "error" } },
          ]),
      })
    );

    const provider = createProvider();
    const results = await provider.batchCall(
      [
        { method: "m1", params: [] },
        { method: "m2", params: [] },
      ],
      { retryCount: 0 }
    );

    expect(results).toHaveLength(2);
    expect(results[0].success).toBe(true);
    expect(results[1].success).toBe(false);
    // Only one fetch call (no retries)
    expect(vi.mocked(fetch)).toHaveBeenCalledTimes(1);
  });

  it("retries multiple times with retryCount > 1", async () => {
    let callCount = 0;
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation(async () => {
        callCount++;
        if (callCount === 1) {
          return {
            ok: true,
            status: 200,
            json: () =>
              Promise.resolve([
                { jsonrpc: "2.0", id: 1, result: "0x1" },
                { jsonrpc: "2.0", id: 2, error: { code: -32000, message: "fail" } },
              ]),
          };
        }
        if (callCount === 2) {
          return {
            ok: true,
            status: 200,
            json: () =>
              Promise.resolve([
                { jsonrpc: "2.0", id: 3, error: { code: -32000, message: "fail again" } },
              ]),
          };
        }
        // Third call (second retry) succeeds
        return {
          ok: true,
          status: 200,
          json: () =>
            Promise.resolve([
              { jsonrpc: "2.0", id: 4, result: "0x2" },
            ]),
        };
      })
    );

    const provider = createProvider();
    const results = await provider.batchCall(
      [
        { method: "m1", params: [] },
        { method: "m2", params: [] },
      ],
      { retryCount: 2, retryBaseDelayMs: 1 }
    );

    expect(results).toHaveLength(2);
    expect(results[0].success).toBe(true);
    expect(results[1].success).toBe(true);
    expect(results[1].value).toBe("0x2");
    expect(callCount).toBe(3);
  });
});

describe("RpcProvider - Single call", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("makes a successful single RPC call", async () => {
    mockFetch({ jsonrpc: "2.0", id: 1, result: "0x1234" });

    const provider = createProvider();
    const result = await provider.call("eth_blockNumber", []);

    expect(result).toBe("0x1234");
  });

  it("throws on RPC error in single call", async () => {
    mockFetch({
      jsonrpc: "2.0",
      id: 1,
      error: { code: -32601, message: "Method not found" },
    });

    // Limit retries to avoid infinite loop (default maxRetries is Infinity)
    const provider = createProvider({ retryOptions: { maxRetries: 0 } });
    await expect(provider.call("unknown_method", [])).rejects.toThrow(
      "RPC error -32601"
    );
  }, 10000);

  it("returns chain ID correctly", () => {
    const provider = createProvider({ chainId: 137 });
    expect(provider.getChainId()).toBe(137);
  });
});