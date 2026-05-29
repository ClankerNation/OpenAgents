process.env.TS_NODE_IGNORE_DIAGNOSTICS = "5102";
process.env.TS_NODE_COMPILER_OPTIONS = JSON.stringify({
  module: "commonjs",
  target: "es2020",
});

require("ts-node/register/transpile-only");

const { expect } = require("chai");
const { withRetry, isRetryable } = require("../sdk/src/utils/retry.ts");

function httpError(status) {
  const error = new Error(`HTTP ${status}`);
  error.status = status;
  return error;
}

describe("conditional retry", function () {
  it("retries 5xx errors and calls onRetry", async function () {
    let attempts = 0;
    const retries = [];

    const result = await withRetry(
      async () => {
        attempts += 1;
        if (attempts < 3) throw httpError(500);
        return "ok";
      },
      {
        maxRetries: 3,
        baseDelayMs: 0,
        onRetry: (attempt, error) => retries.push([attempt, error.status]),
      }
    );

    expect(result).to.equal("ok");
    expect(attempts).to.equal(3);
    expect(retries).to.deep.equal([[1, 500], [2, 500]]);
  });

  it("does not retry 400-class errors by default", async function () {
    let attempts = 0;
    let thrown;

    try {
      await withRetry(
        async () => {
          attempts += 1;
          throw httpError(400);
        },
        { maxRetries: 3, baseDelayMs: 0 }
      );
    } catch (error) {
      thrown = error;
    }

    expect(thrown.message).to.equal("HTTP 400");
    expect(attempts).to.equal(1);
  });

  it("allows custom retry conditions to override the default", async function () {
    let attempts = 0;

    const result = await withRetry(
      async () => {
        attempts += 1;
        if (attempts < 2) throw httpError(400);
        return "custom";
      },
      {
        maxRetries: 2,
        baseDelayMs: 0,
        retryCondition: (error) => error.status === 400,
      }
    );

    expect(result).to.equal("custom");
    expect(attempts).to.equal(2);
  });

  it("classifies network and HTTP status errors", function () {
    expect(isRetryable(Object.assign(new Error("connect ETIMEDOUT"), { code: "ETIMEDOUT" }))).to.equal(true);
    expect(isRetryable(httpError(429))).to.equal(true);
    expect(isRetryable(httpError(503))).to.equal(true);
    expect(isRetryable(httpError(404))).to.equal(false);
  });
});
