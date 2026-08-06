import assert from "node:assert/strict";
import { test } from "node:test";
import { RetryHandler, withRetry } from "../sdk/src/utils/retry.ts";

async function withDeterministicTimers(randomValue, callback) {
  const originalRandom = Math.random;
  const originalSetTimeout = globalThis.setTimeout;
  const delays = [];

  Math.random = () => randomValue;
  globalThis.setTimeout = (handler, delay, ...args) => {
    delays.push(delay);
    handler(...args);
    return 0;
  };

  try {
    await callback(delays);
  } finally {
    Math.random = originalRandom;
    globalThis.setTimeout = originalSetTimeout;
  }
}

test("defaults to five retries and never retries forever", async () => {
  await withDeterministicTimers(0, async (delays) => {
    let attempts = 0;

    await assert.rejects(
      withRetry(async () => {
        attempts += 1;
        throw new Error("ETIMEDOUT");
      }),
      { message: "ETIMEDOUT" },
    );

    assert.equal(attempts, 6);
    assert.deepEqual(delays, [500, 1_000, 2_000, 4_000, 8_000]);
  });
});

test("honors explicit retry counts and resets failures after success", async () => {
  await withDeterministicTimers(0, async () => {
    const handler = new RetryHandler({ maxRetries: 2, baseDelayMs: 0 });
    let attempts = 0;

    const result = await handler.execute(async () => {
      attempts += 1;
      if (attempts < 3) {
        throw new Error("ECONNRESET");
      }
      return "ok";
    });

    assert.equal(result, "ok");
    assert.equal(attempts, 3);
    assert.equal(handler.getFailureCount(), 0);

    await assert.rejects(
      handler.execute(async () => {
        throw new Error("429");
      }),
      { message: "429" },
    );
    assert.equal(handler.getFailureCount(), 3);
  });
});

test("applies 0-25% jitter and enforces the 60-second hard cap", async () => {
  await withDeterministicTimers(1, async (delays) => {
    const handler = new RetryHandler({
      maxRetries: 2,
      baseDelayMs: 500,
      maxDelayMs: 10_000,
    });
    let attempts = 0;

    await handler.execute(async () => {
      attempts += 1;
      if (attempts < 3) {
        throw new Error("ETIMEDOUT");
      }
      return "ok";
    });

    assert.deepEqual(delays, [625, 1_250]);
  });

  await withDeterministicTimers(1, async (delays) => {
    const handler = new RetryHandler({
      maxRetries: 1,
      baseDelayMs: 60_000,
      maxDelayMs: 120_000,
    });
    let attempts = 0;

    await handler.execute(async () => {
      attempts += 1;
      if (attempts === 1) {
        throw new Error("ETIMEDOUT");
      }
      return "ok";
    });

    assert.deepEqual(delays, [60_000]);
  });
});

test("normalizes infinite retry input to the bounded default", async () => {
  await withDeterministicTimers(0, async () => {
    const handler = new RetryHandler({ maxRetries: Infinity, baseDelayMs: 0 });
    let attempts = 0;

    await assert.rejects(
      handler.execute(async () => {
        attempts += 1;
        throw new Error("429");
      }),
      { message: "429" },
    );

    assert.equal(attempts, 6);
  });
});
