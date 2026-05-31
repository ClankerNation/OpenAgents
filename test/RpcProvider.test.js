const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const ts = require("typescript");

function transpileSdkProvider() {
  const tmpRoot = fs.mkdtempSync(path.join(os.tmpdir(), "openagents-sdk-"));
  const outputFiles = [
    { in: "sdk/src/utils/retry.ts", out: "utils/retry.js" },
    { in: "sdk/src/providers/rpc.ts", out: "providers/rpc.js" },
  ];

  for (const entry of outputFiles) {
    const source = fs.readFileSync(path.join(__dirname, "..", entry.in), "utf8");
    const transpiled = ts.transpileModule(source, {
      compilerOptions: {
        module: ts.ModuleKind.CommonJS,
        target: ts.ScriptTarget.ES2022,
      },
      fileName: entry.in,
    });

    const outPath = path.join(tmpRoot, entry.out);
    fs.mkdirSync(path.dirname(outPath), { recursive: true });
    fs.writeFileSync(outPath, transpiled.outputText, "utf8");
  }

  return require(path.join(tmpRoot, "providers/rpc.js"));
}

describe("RpcProvider", function () {
  let RpcProvider;
  let RpcBatchGasLimitError;
  let originalFetch;

  before(function () {
    ({ RpcProvider, RpcBatchGasLimitError } = transpileSdkProvider());
  });

  beforeEach(function () {
    originalFetch = global.fetch;
  });

  afterEach(function () {
    global.fetch = originalFetch;
  });

  it("aborts requests that exceed timeout", async function () {
    global.fetch = (_url, init) =>
      new Promise((_resolve, reject) => {
        init.signal.addEventListener("abort", () => {
          const err = new Error("aborted");
          err.name = "AbortError";
          reject(err);
        });
      });

    const provider = new RpcProvider({
      url: "http://127.0.0.1:8545",
      chainId: 1,
      timeoutMs: 20,
      retryOptions: { maxRetries: 0 },
    });

    await assert.rejects(
      () => provider.call("eth_chainId"),
      /timed out/i
    );
  });

  it("rejects batch requests that exceed configured gas budget", async function () {
    let called = false;
    global.fetch = async () => {
      called = true;
      return new Response("[]", { status: 200 });
    };

    const provider = new RpcProvider({
      url: "http://127.0.0.1:8545",
      chainId: 1,
      maxBatchGas: 100n,
      retryOptions: { maxRetries: 0 },
    });

    await assert.rejects(
      () => provider.batchCall([
        { method: "eth_call", params: [{ gas: "0x40" }] },
        { method: "eth_call", params: [{ gasLimit: "0x50" }] },
      ]),
      RpcBatchGasLimitError
    );

    assert.equal(called, false);
  });

  it("retries on 429 and eventually succeeds", async function () {
    let attempts = 0;
    global.fetch = async () => {
      attempts += 1;
      if (attempts < 3) {
        return new Response("rate limited", { status: 429, statusText: "Too Many Requests" });
      }
      return new Response(
        JSON.stringify({ jsonrpc: "2.0", id: 1, result: "0x2a" }),
        { status: 200, headers: { "Content-Type": "application/json" } }
      );
    };

    const provider = new RpcProvider({
      url: "http://127.0.0.1:8545",
      chainId: 1,
      retryOptions: { maxRetries: 3, baseDelayMs: 1, maxDelayMs: 2 },
    });

    const result = await provider.call("eth_chainId");
    assert.equal(result, "0x2a");
    assert.equal(attempts, 3);
  });
});
