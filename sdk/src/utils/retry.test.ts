/**
 * Tests for retry.ts — conditional retry based on error type.
 *
 * Run with: tsx sdk/src/utils/retry.test.ts
 */
import { RetryHandler, withRetry, isRetryable, defaultRetryCondition } from "./retry";

let testsRun = 0;
let testsPassed = 0;

function assert(condition: boolean, msg: string): void {
  testsRun++;
  if (condition) {
    testsPassed++;
    console.log(`  ✓ ${msg}`);
  } else {
    console.error(`  ✗ FAIL: ${msg}`);
  }
}

function assertRejects(fn: () => Promise<unknown>, expectedMsg?: string): Promise<void> {
  testsRun++;
  return fn().then(
    () => {
      console.error(`  ✗ FAIL: Expected rejection but promise resolved`);
    },
    (err) => {
      if (expectedMsg && !String(err).includes(expectedMsg)) {
        console.error(`  ✗ FAIL: Expected error containing "${expectedMsg}" but got "${err}"`);
      } else {
        testsPassed++;
        console.log(`  ✓ Rejected with: ${err}`);
      }
    }
  );
}

function assertResolves(fn: () => Promise<unknown>, expected?: unknown): Promise<void> {
  testsRun++;
  return fn().then(
    (val) => {
      if (expected !== undefined && val !== expected) {
        console.error(`  ✗ FAIL: Expected ${expected} but got ${val}`);
      } else {
        testsPassed++;
        console.log(`  ✓ Resolved with: ${val}`);
      }
    },
    (err) => {
      console.error(`  ✗ FAIL: Expected resolution but promise rejected: ${err}`);
    }
  );
}

function assertApprox(actual: number, expected: number, tolerance: number, msg: string): void {
  testsRun++;
  if (Math.abs(actual - expected) <= tolerance) {
    testsPassed++;
    console.log(`  ✓ ${msg} (${actual})`);
  } else {
    console.error(`  ✗ FAIL: ${msg} — expected ~${expected}, got ${actual}`);
  }
}

// ============================================================
// Test Suite
// ============================================================

async function testDefaultRetryCondition() {
  console.log("\n--- testDefaultRetryCondition ---");

  // Network errors should be retryable
  assert(defaultRetryCondition(new Error("ETIMEDOUT"), 0) === true, "ETIMEDOUT is retryable");
  assert(defaultRetryCondition(new Error("ECONNRESET"), 0) === true, "ECONNRESET is retryable");
  assert(defaultRetryCondition(new Error("ECONNREFUSED"), 0) === true, "ECONNREFUSED is retryable");
  assert(defaultRetryCondition(new Error("ENOTFOUND"), 0) === true, "ENOTFOUND is retryable");
  assert(defaultRetryCondition(new Error("EAI_AGAIN"), 0) === true, "EAI_AGAIN is retryable");

  // 5xx should be retryable
  assert(defaultRetryCondition(new Error("HTTP 500 Internal Server Error"), 0) === true, "500 is retryable");
  assert(defaultRetryCondition(new Error("HTTP 502 Bad Gateway"), 0) === true, "502 is retryable");
  assert(defaultRetryCondition(new Error("503 Service Unavailable"), 0) === true, "503 is retryable");
  assert(defaultRetryCondition(new Error("HTTP 504 Gateway Timeout"), 0) === true, "504 is retryable");

  // 429 should be retryable
  assert(defaultRetryCondition(new Error("429 Too Many Requests"), 0) === true, "429 is retryable");
  assert(defaultRetryCondition(new Error("too many requests"), 0) === true, "'too many requests' is retryable");

  // 4xx (except 429) should NOT be retryable
  assert(defaultRetryCondition(new Error("HTTP 400 Bad Request"), 0) === false, "400 is NOT retryable");
  assert(defaultRetryCondition(new Error("HTTP 401 Unauthorized"), 0) === false, "401 is NOT retryable");
  assert(defaultRetryCondition(new Error("HTTP 403 Forbidden"), 0) === false, "403 is NOT retryable");
  assert(defaultRetryCondition(new Error("HTTP 404 Not Found"), 0) === false, "404 is NOT retryable");
  assert(defaultRetryCondition(new Error("HTTP 422 Unprocessable Entity"), 0) === false, "422 is NOT retryable");

  // RPC server errors should be retryable
  assert(defaultRetryCondition(new Error("RPC error -32000: server error"), 0) === true, "RPC -32000 is retryable");
  assert(defaultRetryCondition(new Error("RPC error -32099: execution reverted"), 0) === true, "RPC -32099 is retryable");

  // Unknown errors should be retried conservatively
  assert(defaultRetryCondition(new Error("some unknown error"), 0) === true, "Unknown error defaults to retryable");
}

async function testRetryOnTransientError() {
  console.log("\n--- testRetryOnTransientError ---");
  let attempts = 0;

  const handler = new RetryHandler({ maxRetries: 3 });
  const result = await handler.execute(async () => {
    attempts++;
    if (attempts < 3) {
      throw new Error("ETIMEDOUT");
    }
    return "success";
  });

  assert(result === "success", `Retry succeeded after ${attempts} attempts`);
  assert(attempts === 3, `Expected 3 attempts, got ${attempts}`);
  assert(handler.getFailureCount() === 0, "Failure count reset after success");
}

async function testNoRetryOnPermanentError() {
  console.log("\n--- testNoRetryOnPermanentError ---");
  let attempts = 0;

  const handler = new RetryHandler({ maxRetries: 3 });

  try {
    await handler.execute(async () => {
      attempts++;
      throw new Error("HTTP 400 Bad Request");
    });
    assert(false, "Should have thrown");
  } catch (err) {
    assert(attempts === 1, `Expected 1 attempt (no retry on 400), got ${attempts}`);
    assert(String(err).includes("400"), `Error mentions 400: ${err}`);
  }
}

async function testCustomRetryCondition() {
  console.log("\n--- testCustomRetryCondition ---");
  let attempts = 0;

  // Only retry on errors containing "SPECIAL"
  const handler = new RetryHandler({
    maxRetries: 3,
    retryCondition: (err) => err.message.includes("SPECIAL"),
  });

  // This should NOT retry
  try {
    await handler.execute(async () => {
      attempts++;
      throw new Error("HTTP 500 error");
    });
    assert(false, "Should have thrown for non-special error");
  } catch (err) {
    assert(attempts === 1, `Custom condition: no retry for non-special, attempts=${attempts}`);
  }

  // This should retry
  attempts = 0;
  const result = await handler.execute(async () => {
    attempts++;
    if (attempts < 3) {
      throw new Error("SPECIAL retryable error");
    }
    return "custom-ok";
  });
  assert(result === "custom-ok", `Custom condition retry succeeded, attempts=${attempts}`);
  assert(attempts === 3, `Custom condition: 3 attempts, got ${attempts}`);
}

async function testOnRetryCallback() {
  console.log("\n--- testOnRetryCallback ---");
  const retryCalls: Array<{ attempt: number; error: string }> = [];

  const handler = new RetryHandler({
    maxRetries: 2,
    onRetry: (attempt, error) => {
      retryCalls.push({ attempt, error: error.message });
    },
  });

  let attempts = 0;
  await handler.execute(async () => {
    attempts++;
    throw new Error("ECONNRESET");
  }).catch(() => {});

  assert(retryCalls.length === 2, `onRetry called ${retryCalls.length} times (expected 2)`);
  assert(retryCalls[0].attempt === 1, `First retry is attempt 1`);
  assert(retryCalls[1].attempt === 2, `Second retry is attempt 2`);
}

async function testMaxRetries() {
  console.log("\n--- testMaxRetries ---");
  let attempts = 0;

  const handler = new RetryHandler({ maxRetries: 2 });

  try {
    await handler.execute(async () => {
      attempts++;
      throw new Error("ETIMEDOUT");
    });
    assert(false, "Should have thrown after max retries");
  } catch (err) {
    // maxRetries=2 means attempt 0,1,2 = 3 total calls
    assert(attempts === 3, `Expected 3 total attempts (0..2), got ${attempts}`);
  }
}

async function testExponentialBackoff() {
  console.log("\n--- testExponentialBackoff ---");
  // With baseDelayMs=100, maxDelayMs=10000, attempt 0 delay ≈ 100-200ms, attempt 1 ≈ 200-300ms
  const handler = new RetryHandler({ baseDelayMs: 10, maxDelayMs: 1000, maxRetries: 3 });
  let prevDelay = 0;

  for (let attempt = 0; attempt < 3; attempt++) {
    const delay = (handler as any).calculateBackoff(attempt, new Error("ETIMEDOUT"));
    assert(delay > 0, `Delay is positive for attempt ${attempt}`);
    // Backoff should generally increase
    console.log(`    Attempt ${attempt} delay: ${Math.round(delay)}ms`);
  }
}

async function testErrorBackoffMultiplier() {
  console.log("\n--- testErrorBackoffMultiplier ---");
  const handler = new RetryHandler({
    baseDelayMs: 100,
    maxDelayMs: 10000,
    maxRetries: 1,
    errorBackoffs: [{ pattern: "429", multiplier: 4 }],
  });

  const normalDelay = (handler as any).calculateBackoff(0, new Error("ETIMEDOUT"));
  const rateLimitDelay = (handler as any).calculateBackoff(0, new Error("429 Too Many Requests"));

  // Rate limit delay should be ~4x normal
  assert(rateLimitDelay > normalDelay * 2, `Rate limit delay (${Math.round(rateLimitDelay)}) > 2x normal (${Math.round(normalDelay)})`);
  assert(rateLimitDelay <= 400 + 100, `Rate limit delay (${Math.round(rateLimitDelay)}) <= base*4 + jitter (500)`);
}

async function testWithRetryFunction() {
  console.log("\n--- testWithRetryFunction ---");
  let attempts = 0;

  const result = await withRetry(async () => {
    attempts++;
    if (attempts < 3) {
      throw new Error("ECONNRESET");
    }
    return "withRetry-ok";
  }, { maxRetries: 3 });

  assert(result === "withRetry-ok", `withRetry returns correct value`);
  assert(attempts === 3, `withRetry: 3 attempts, got ${attempts}`);
}

async function testWithRetryNoRetryOn400() {
  console.log("\n--- testWithRetryNoRetryOn400 ---");
  let attempts = 0;

  try {
    await withRetry(async () => {
      attempts++;
      throw new Error("HTTP 400 Bad Request");
    }, { maxRetries: 3 });
    assert(false, "Should have thrown");
  } catch (err) {
    assert(attempts === 1, `withRetry 400: 1 attempt (no retry), got ${attempts}`);
  }
}

async function testIsRetryable() {
  console.log("\n--- testIsRetryable ---");
  assert(isRetryable(new Error("ETIMEDOUT")) === true, "isRetryable: ETIMEDOUT");
  assert(isRetryable(new Error("HTTP 500 error")) === true, "isRetryable: 500");
  assert(isRetryable(new Error("429 Too Many Requests")) === true, "isRetryable: 429");
  assert(isRetryable(new Error("HTTP 400 Bad Request")) === false, "isRetryable: 400");
  assert(isRetryable(new Error("HTTP 404 Not Found")) === false, "isRetryable: 404");
}

async function testReset() {
  console.log("\n--- testReset ---");
  const handler = new RetryHandler({ maxRetries: 1 });

  try {
    await handler.execute(async () => { throw new Error("ETIMEDOUT"); });
  } catch {}

  assert(handler.getFailureCount() > 0, "Failure count is > 0 after failure");

  handler.reset();
  assert(handler.getFailureCount() === 0, "Failure count reset to 0 after reset()");
}

async function testRestoreAfterPermanentError() {
  console.log("\n--- testRestoreAfterPermanentError ---");
  // A 400 error should not consume retries — subsequent calls should work
  const handler = new RetryHandler({ maxRetries: 3 });
  let firstPhase = true;

  // First call — fails with 400 immediately
  try {
    await handler.execute(async () => {
      if (firstPhase) {
        throw new Error("HTTP 400 Bad Request");
      }
      return "ok";
    });
  } catch {}

  // Second call should still work with full retry budget
  firstPhase = false;
  let attempts = 0;
  const result = await handler.execute(async () => {
    attempts++;
    if (attempts < 2) {
      throw new Error("ECONNRESET");
    }
    return "restored";
  });

  assert(result === "restored", `Recovered after permanent error`);
  assert(attempts === 2, `Recovery took ${attempts} attempts`);
}

async function testSuccessOnFirstAttempt() {
  console.log("\n--- testSuccessOnFirstAttempt ---");
  const handler = new RetryHandler({ maxRetries: 3 });
  const result = await handler.execute(async () => "immediate");
  assert(result === "immediate", "Returns immediately on success");
  assert(handler.getFailureCount() === 0, "Failure count is 0 on immediate success");
}

// ============================================================
// Run all tests
// ============================================================
async function main() {
  console.log("=== retry.ts Test Suite ===");
  console.log(`Node ${process.version}\n`);

  try {
    await testDefaultRetryCondition();
    await testRetryOnTransientError();
    await testNoRetryOnPermanentError();
    await testCustomRetryCondition();
    await testOnRetryCallback();
    await testMaxRetries();
    await testExponentialBackoff();
    await testErrorBackoffMultiplier();
    await testWithRetryFunction();
    await testWithRetryNoRetryOn400();
    await testIsRetryable();
    await testReset();
    await testRestoreAfterPermanentError();
    await testSuccessOnFirstAttempt();
  } catch (err) {
    console.error("\nUNEXPECTED ERROR:", err);
  }

  console.log(`\n=== Results: ${testsPassed}/${testsRun} passed ===`);
  process.exit(testsPassed === testsRun ? 0 : 1);
}

main();
