import assert from "node:assert/strict";
import { RpcProvider, JsonRpcBatchItemError } from "./rpc";

type FetchHandler = (body: any) => Promise<any>;

function installFetch(handler: FetchHandler): () => void {
  const originalFetch = globalThis.fetch;

  globalThis.fetch = (async (_url: string | URL | Request, init?: RequestInit) => {
    const body = JSON.parse(String(init?.body));
    const payload = await handler(body);
    return {
      json: async () => payload,
    } as Response;
  }) as typeof fetch;

  return () => {
    globalThis.fetch = originalFetch;
  };
}

function isBatchError(value: unknown): value is JsonRpcBatchItemError {
  return Boolean(value && typeof value === "object" && "error" in value);
}

async function testShuffledBatchResponses(): Promise<void> {
  const restoreFetch = installFetch(async (body) => [
    { jsonrpc: "2.0", id: body[2].id, result: "third" },
    { jsonrpc: "2.0", id: body[0].id, result: "first" },
    { jsonrpc: "2.0", id: body[1].id, result: "second" },
  ]);

  try {
    const provider = new RpcProvider({ url: "http://rpc.test", chainId: 1 });
    const results = await provider.batchCall([
      { method: "first", params: [] },
      { method: "second", params: [] },
      { method: "third", params: [] },
    ]);

    assert.deepEqual(results, ["first", "second", "third"]);
  } finally {
    restoreFetch();
  }
}

async function testPartialFailureDoesNotFailBatch(): Promise<void> {
  const restoreFetch = installFetch(async (body) => [
    { jsonrpc: "2.0", id: body[1].id, error: { code: -32001, message: "bad call" } },
    { jsonrpc: "2.0", id: body[0].id, result: "ok" },
  ]);

  try {
    const provider = new RpcProvider({ url: "http://rpc.test", chainId: 1 });
    const results = await provider.batchCall([
      { method: "ok", params: [] },
      { method: "bad", params: [] },
    ]);

    assert.equal(results[0], "ok");
    assert.ok(isBatchError(results[1]));
    assert.equal(results[1].error.code, -32001);
    assert.equal(results[1].error.message, "bad call");
  } finally {
    restoreFetch();
  }
}

async function testMissingResponseReturnsTimeoutError(): Promise<void> {
  const restoreFetch = installFetch(async (body) => [
    { jsonrpc: "2.0", id: body[0].id, result: "ok" },
  ]);

  try {
    const provider = new RpcProvider({
      url: "http://rpc.test",
      chainId: 1,
      timeoutMs: 25,
    });
    const results = await provider.batchCall([
      { method: "ok", params: [] },
      { method: "missing", params: [] },
    ]);

    assert.equal(results[0], "ok");
    assert.ok(isBatchError(results[1]));
    assert.equal(results[1].error.code, -32000);
    assert.match(results[1].error.message, /timed out after 25ms/);
  } finally {
    restoreFetch();
  }
}

async function main(): Promise<void> {
  await testShuffledBatchResponses();
  await testPartialFailureDoesNotFailBatch();
  await testMissingResponseReturnsTimeoutError();
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
