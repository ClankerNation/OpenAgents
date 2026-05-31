const assert = require("assert");
process.env.TS_NODE_COMPILER_OPTIONS = JSON.stringify({
  module: "commonjs",
  target: "es2020",
  moduleResolution: "node",
  ignoreDeprecations: "6.0",
});
require("ts-node/register/transpile-only");

const { isRetryable, withRetry } = require("../sdk/src/utils/retry.ts");

function httpError(status) {
  const error = new Error(`HTTP ${status}`);
  error.status = status;
  return error;
}

describe("SDK conditional retry", function () {
  it("retries 5xx responses by default", async function () {
    let calls = 0;
    const retries = [];

    const result = await withRetry(async () => {
      calls++;
      if (calls < 2) throw httpError(500);
      return "ok";
    }, {
      maxRetries: 2,
      baseDelayMs: 0,
      onRetry: (attempt, error) => retries.push({ attempt, status: error.status }),
    });

    assert.equal(result, "ok");
    assert.equal(calls, 2);
    assert.deepEqual(retries, [{ attempt: 1, status: 500 }]);
  });

  it("does not retry 4xx responses by default", async function () {
    let calls = 0;
    await assert.rejects(
      () => withRetry(async () => {
        calls++;
        throw httpError(400);
      }, { maxRetries: 3, baseDelayMs: 0 }),
      /HTTP 400/
    );

    assert.equal(calls, 1);
  });

  it("retries network errors by default", async function () {
    let calls = 0;

    const result = await withRetry(async () => {
      calls++;
      if (calls < 2) throw new Error("ECONNRESET socket closed");
      return "ok";
    }, { maxRetries: 2, baseDelayMs: 0 });

    assert.equal(result, "ok");
    assert.equal(calls, 2);
  });

  it("allows custom retry conditions to override the default", async function () {
    let calls = 0;

    const result = await withRetry(async () => {
      calls++;
      if (calls < 2) throw httpError(400);
      return "retried";
    }, {
      maxRetries: 2,
      baseDelayMs: 0,
      retryCondition: (error) => error.status === 400,
    });

    assert.equal(result, "retried");
    assert.equal(calls, 2);
  });

  it("exposes retryability for status and network errors", function () {
    assert.equal(isRetryable(httpError(503)), true);
    assert.equal(isRetryable(httpError(404)), false);
    assert.equal(isRetryable(new Error("ETIMEDOUT")), true);
  });
});
