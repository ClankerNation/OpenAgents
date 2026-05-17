/**
 * Tests for RetryHandler with conditional retry support.
 * Run with: npx ts-node --project sdk/tsconfig.json sdk/test/retry.test.ts
 */

import { RetryHandler, withRetry, isRetryable } from "../src/utils/retry";

async function assert(condition: boolean, msg: string) {
  if (!condition) throw new Error(`FAIL: ${msg}`);
  console.log(`  PASS: ${msg}`);
}

async function testDefaultRetryCondition() {
  console.log("\n[Default Retry Condition]");

  assert(isRetryable(new Error("ETIMEDOUT")), "ETIMEDOUT is retryable");
  assert(isRetryable(new Error("ECONNRESET")), "ECONNRESET is retryable");
  assert(isRetryable(new Error("timeout")), "timeout message is retryable");
  assert(isRetryable(new Error("500")), "500 status is retryable");
  assert(isRetryable(new Error("503")), "503 status is retryable");
  assert(isRetryable(new Error("502")), "502 status is retryable");

  assert(!isRetryable(new Error("400 Bad Request")), "400 is not retryable");
  assert(!isRetryable(new Error("401 Unauthorized")), "401 is not retryable");
  assert(!isRetryable(new Error("403 Forbidden")), "403 is not retryable");
  assert(!isRetryable(new Error("404 Not Found")), "404 is not retryable");
  assert(!isRetryable(new Error("422 Unprocessable")), "422 is not retryable");
}

async function test500Retries() {
  console.log("\n[5xx Errors Retry]");
  let attempts = 0;
  const handler = new RetryHandler({ maxRetries: 3 });

  try {
    await handler.execute(async () => {
      attempts++;
      throw new Error("500 Internal Server Error");
    });
  } catch (e) {
    // expected
  }

  assert(attempts === 4, `500 retried 4 times (1 initial + 3 retries), got ${attempts}`);
}

async function test400FailsImmediately() {
  console.log("\n[4xx Errors Fail Immediately]");
  let attempts = 0;
  const handler = new RetryHandler({ maxRetries: 3 });

  try {
    await handler.execute(async () => {
      attempts++;
      throw new Error("400 Bad Request");
    });
  } catch (e) {
    // expected
  }

  assert(attempts === 1, `400 failed immediately, got ${attempts} attempt(s)`);
}

async function testCustomCondition() {
  console.log("\n[Custom Condition Override]");
  let attempts = 0;
  const handler = new RetryHandler({
    maxRetries: 2,
    retryCondition: (err) => err.message.includes("RETRY_ME"),
  });

  try {
    await handler.execute(async () => {
      attempts++;
      throw new Error("400 RETRY_ME");
    });
  } catch (e) {
    // expected
  }

  assert(attempts === 3, `custom condition retried, got ${attempts} attempts`);

  // Test that it skips for non-matching
  attempts = 0;
  const handler2 = new RetryHandler({
    maxRetries: 2,
    retryCondition: (err) => err.message.includes("RETRY_ME"),
  });

  try {
    await handler2.execute(async () => {
      attempts++;
      throw new Error("400 DONT_RETRY");
    });
  } catch (e) {
    // expected
  }

  assert(attempts === 1, `custom condition skip, got ${attempts} attempt(s)`);
}

async function testOnRetryCallback() {
  console.log("\n[onRetry Callback]");
  const calls: Array<{ attempt: number; error: string }> = [];
  const handler = new RetryHandler({
    maxRetries: 2,
    onRetry: (attempt, error) => {
      calls.push({ attempt, error: error.message });
    },
  });

  try {
    await handler.execute(async () => {
      throw new Error("500 Server Error");
    });
  } catch (e) {
    // expected
  }

  assert(calls.length === 2, `onRetry called ${calls.length} times (expected 2)`);
  assert(calls[0].attempt === 1, "first call attempt=1");
  assert(calls[1].attempt === 2, "second call attempt=2");
}

async function testConsecutiveFailuresReset() {
  console.log("\n[Consecutive Failures Reset on Success]");
  let callCount = 0;
  const handler = new RetryHandler({ maxRetries: 3 });

  // Fail twice, succeed on third
  const result = await handler.execute(async () => {
    callCount++;
    if (callCount <= 2) throw new Error("500 Server Error");
    return "success";
  });

  assert(result === "success", "eventually succeeded");
  assert(handler.getFailureCount() === 0, "failure count reset after success");
}

async function testSuccessNoRetry() {
  console.log("\n[Success No Retry]");
  const handler = new RetryHandler({ maxRetries: 3 });
  const result = await handler.execute(async () => "ok");
  assert(result === "ok", "returns value directly");
  assert(handler.getFailureCount() === 0, "no failures");
}

async function testWithRetryHelper() {
  console.log("\n[withRetry Helper]");
  let count = 0;
  const result = await withRetry(async () => {
    count++;
    if (count < 3) throw new Error("500 Server Error");
    return "done";
  }, { maxRetries: 3 });

  assert(result === "done", "withRetry eventually succeeds");
  assert(count === 3, `withRetry attempted ${count} times`);
}

async function run() {
  console.log("=== RetryHandler Tests ===\n");

  try {
    await testDefaultRetryCondition();
    await test500Retries();
    await test400FailsImmediately();
    await testCustomCondition();
    await testOnRetryCallback();
    await testConsecutiveFailuresReset();
    await testSuccessNoRetry();
    await testWithRetryHelper();

    console.log("\n✅ ALL TESTS PASSED");
  } catch (e: any) {
    console.error(`\n❌ ${e.message}`);
    process.exit(1);
  }
}

run();
