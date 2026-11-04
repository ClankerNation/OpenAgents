import { expect } from "chai";
import { RpcProvider } from "../sdk/src/providers/rpc.ts";

// @contributor Hermes Agent (DeepSeek V4.1 Flash Abliterated, Nous Research)
// @platform-config full verbatim block: header of sdk/src/providers/rpc.ts
// @runtime os=windows arch=x86_64 working_dir=C:/Users/2/AppData/Local/hermes/cache/scratch/oa
//   shell=C:\Program Files\Git\bin\bash.exe

type Call = { method: string; params: unknown[] };

const calls = (...methods: string[]): Call[] => methods.map((method, i) => ({ method, params: [i] }));

function provider(config: Record<string, unknown> = {}) {
  return new RpcProvider({ url: "http://rpc.test", chainId: 1, ...config });
}

/** Replace fetch with a stub that answers from `behaviour(requestBody)`. */
function stubFetch(behaviour: (body: any) => any) {
  const seen: any[] = [];
  const original = globalThis.fetch;
  globalThis.fetch = (async (_url: string, init: any) => {
    const body = JSON.parse(init.body);
    seen.push(body);
    const payload = await behaviour(body);
    return { json: async () => payload };
  }) as any;
  return { seen, restore: () => (globalThis.fetch = original) };
}

describe("RpcProvider.batchCall", function () {
  let restore: (() => void) | null = null;
  afterEach(() => {
    restore?.();
    restore = null;
  });

  it("matches out-of-order responses by id", async function () {
    const stub = stubFetch((body) =>
      [...body].reverse().map((request: any) => ({ jsonrpc: "2.0", id: request.id, result: `r${request.params[0]}` }))
    );
    restore = stub.restore;

    const outcomes = await provider().batchCall(calls("a", "b", "c"));
    expect(outcomes.map((o) => o.result)).to.deep.equal(["r0", "r1", "r2"]);
    expect(outcomes.every((o) => o.ok)).to.equal(true);
  });

  it("keeps input order even when the wire order is scrambled", async function () {
    const stub = stubFetch((body) => {
      const shuffled = [body[2], body[0], body[1]];
      return shuffled.map((request: any) => ({ jsonrpc: "2.0", id: request.id, result: request.method }));
    });
    restore = stub.restore;

    const outcomes = await provider().batchCall(calls("first", "second", "third"));
    expect(outcomes.map((o) => o.result)).to.deep.equal(["first", "second", "third"]);
  });

  it("lets one failing entry fail alone", async function () {
    const stub = stubFetch((body) =>
      body.map((request: any) =>
        request.params[0] === 1
          ? { jsonrpc: "2.0", id: request.id, error: { code: -32000, message: "reverted" } }
          : { jsonrpc: "2.0", id: request.id, result: "fine" }
      )
    );
    restore = stub.restore;

    const outcomes = await provider().batchCall(calls("a", "b", "c"));
    expect(outcomes.map((o) => o.ok)).to.deep.equal([true, false, true]);
    expect(outcomes[1].error).to.deep.equal({ code: -32000, message: "reverted" });
    expect(outcomes[0].result).to.equal("fine");
  });

  it("times an unanswered entry out without waiting for the socket", async function () {
    const stub = stubFetch(() => new Promise(() => {})); // never resolves
    restore = stub.restore;

    const started = Date.now();
    const outcomes = await provider({ requestTimeoutMs: 25 }).batchCall(calls("a", "b"));
    expect(Date.now() - started).to.be.lessThan(2000);
    expect(outcomes.map((o) => o.error?.code)).to.deep.equal(["TIMEOUT", "TIMEOUT"]);
  });

  it("reports a missing reply as NO_RESPONSE", async function () {
    const stub = stubFetch((body) => [body[0]].map((r: any) => ({ jsonrpc: "2.0", id: r.id, result: "only" })));
    restore = stub.restore;

    const outcomes = await provider({ requestTimeoutMs: 40 }).batchCall(calls("a", "b"));
    expect(outcomes[0].ok).to.equal(true);
    expect(outcomes[1].error?.code).to.equal("NO_RESPONSE");
  });

  it("marks every entry on a transport failure", async function () {
    const original = globalThis.fetch;
    globalThis.fetch = (async () => {
      throw new Error("econnreset");
    }) as any;
    restore = () => (globalThis.fetch = original);

    const outcomes = await provider().batchCall(calls("a", "b"));
    expect(outcomes.map((o) => o.error?.code)).to.deep.equal(["NETWORK", "NETWORK"]);
    expect(outcomes[0].ok).to.equal(false);
  });

  it("accepts a bare object when a one-entry batch comes back unwrapped", async function () {
    const stub = stubFetch((body) => ({ jsonrpc: "2.0", id: body[0].id, result: 7 }));
    restore = stub.restore;

    const outcomes = await provider().batchCall(calls("solo"));
    expect(outcomes[0].result).to.equal(7);
  });

  it("tolerates string ids from the node", async function () {
    const stub = stubFetch((body) => body.map((r: any) => ({ jsonrpc: "2.0", id: String(r.id), result: "s" })));
    restore = stub.restore;

    const outcomes = await provider().batchCall(calls("a"));
    expect(outcomes[0].ok).to.equal(true);
  });

  it("splits oversized batches into several HTTP requests", async function () {
    const stub = stubFetch((body) => body.map((r: any) => ({ jsonrpc: "2.0", id: r.id, result: 1 })));
    restore = stub.restore;

    await provider({ maxBatchSize: 2 }).batchCall(calls("a", "b", "c", "d", "e"));
    expect(stub.seen.length).to.equal(3);
    expect(stub.seen.map((b) => b.length)).to.deep.equal([2, 2, 1]);
  });

  it("sends nothing for an empty batch", async function () {
    const stub = stubFetch(() => []);
    restore = stub.restore;

    expect(await provider().batchCall([])).to.deep.equal([]);
    expect(stub.seen.length).to.equal(0);
  });

  it("still reports a result of false and 0 as ok", async function () {
    const stub = stubFetch((body) =>
      body.map((r: any) => ({ jsonrpc: "2.0", id: r.id, result: r.params[0] === 0 ? 0 : false }))
    );
    restore = stub.restore;

    const outcomes = await provider().batchCall(calls("a", "b"));
    expect(outcomes.map((o) => o.ok)).to.deep.equal([true, true]);
    expect(outcomes[0].result).to.equal(0);
    expect(outcomes[1].result).to.equal(false);
  });
});
