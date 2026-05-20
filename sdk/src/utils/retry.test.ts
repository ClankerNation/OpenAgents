import assert from "node:assert/strict";
import { RetryHandler } from "./retry";

async function testDefaultMaxRetries(): Promise<void> {
  const handler = new RetryHandler({ baseDelayMs: 0 });
  let attempts = 0;

  await assert.rejects(
    handler.execute(async () => {
      attempts++;
      throw new Error("ETIMEDOUT");
    }),
    /ETIMEDOUT/
  );

  assert.equal(attempts, 6, "default maxRetries should allow 5 retries");
}

async function testSuccessResetsFailureCount(): Promise<void> {
  const handler = new RetryHandler({ baseDelayMs: 0, maxRetries: 1 });
  let attempts = 0;

  const result = await handler.execute(async () => {
    attempts++;
    if (attempts === 1) {
      throw new Error("ECONNRESET");
    }
    return "ok";
  });

  assert.equal(result, "ok");
  assert.equal(handler.getFailureCount(), 0);
}

function testBackoffCap(): void {
  const handler = new RetryHandler({ baseDelayMs: 500, maxDelayMs: 1_000_000 });
  const delay = (handler as any).calculateBackoff(1_000);

  assert.equal(delay, 60_000);
}

function testJitterRange(): void {
  const originalRandom = Math.random;
  Math.random = () => 1;

  try {
    const handler = new RetryHandler({ baseDelayMs: 100, maxDelayMs: 10_000 });
    const delay = (handler as any).calculateBackoff(1);

    assert.equal(delay, 250);
  } finally {
    Math.random = originalRandom;
  }
}

async function main(): Promise<void> {
  await testDefaultMaxRetries();
  await testSuccessResetsFailureCount();
  testBackoffCap();
  testJitterRange();
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
