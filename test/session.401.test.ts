import { expect } from "chai";
import { AuthenticationError, SessionManager, type SessionToken } from "../sdk/src/auth/session.ts";

// @contributor Hermes Agent (DeepSeek V4.1 Flash Abliterated, Nous Research)
// @platform full verbatim block: header of sdk/src/auth/session.ts
// @runtime os=windows arch=x86_64 working_dir=C:/Users/2/AppData/Local/hermes/cache/scratch/oa
//   shell=C:\Program Files\Git\bin\bash.exe

const TOKEN = (tag: string, ttl = 3600): SessionToken => ({
  token: `tok-${tag}`,
  expiresAt: Math.floor(Date.now() / 1000) + ttl,
  refreshToken: `ref-${tag}`,
  walletAddress: "0xw",
});

function manager(extra: Record<string, unknown> = {}) {
  const wallet: any = { address: "0xw", sendTransaction: async () => "0xsig" };
  const m = new SessionManager({ wallet, apiBaseUrl: "http://api.test", ...extra });
  (m as any).currentToken = TOKEN("first");
  return m;
}

type Answer = (url: string, init: any) => { status: number } | Response;

function stubFetch(answer: Answer) {
  const calls: Array<{ url: string; auth?: string }> = [];
  const original = globalThis.fetch;
  globalThis.fetch = (async (url: string, init: any) => {
    calls.push({ url, auth: init?.headers?.Authorization });
    const out: any = answer(url, init);
    if (out instanceof Response) return out;
    return new Response(JSON.stringify(out.status === 200 ? TOKEN("fresh") : {}), {
      status: out.status,
      headers: { "Content-Type": "application/json" },
    });
  }) as any;
  return { calls, restore: () => (globalThis.fetch = original) };
}

describe("SessionManager.request auth recovery", function () {
  let restore: (() => void) | null = null;
  afterEach(() => {
    restore?.();
    restore = null;
  });

  it("refreshes once and retries the original request", async function () {
    let protectedHits = 0;
    const stub = stubFetch((url) => {
      if (url.endsWith("/auth/refresh")) return { status: 200 };
      protectedHits += 1;
      return { status: protectedHits === 1 ? 401 : 200 };
    });
    restore = stub.restore;

    const res = await manager().request("/agents");
    expect(res.status).to.equal(200);
    expect(protectedHits).to.equal(2); // original + exactly one retry
    const refreshCalls = stub.calls.filter((c) => c.url.endsWith("/auth/refresh"));
    expect(refreshCalls.length).to.equal(1);
  });

  it("retries with the refreshed token, not the stale one", async function () {
    let attempt = 0;
    const stub = stubFetch((url) => {
      if (url.endsWith("/auth/refresh")) return { status: 200 };
      attempt += 1;
      return { status: attempt === 1 ? 401 : 200 };
    });
    restore = stub.restore;

    await manager().request("/agents");
    const protectedCall = stub.calls.filter((c) => !c.url.endsWith("/auth/refresh"));
    expect(protectedCall[0].auth).to.equal("Bearer tok-first");
    expect(protectedCall[1].auth).to.equal("Bearer tok-fresh");
  });

  it("throws AuthenticationError on a second 401 and fires the callback", async function () {
    const seen: AuthenticationError[] = [];
    const stub = stubFetch((url) => (url.endsWith("/auth/refresh") ? { status: 200 } : { status: 401 }));
    restore = stub.restore;

    const m = manager({ onAuthFailure: (e: AuthenticationError) => seen.push(e) });

    let caught: unknown;
    try {
      await m.request("/agents");
    } catch (error) {
      caught = error;
    }
    expect(caught).to.be.instanceOf(AuthenticationError);
    expect(seen.length).to.equal(1);
    expect(seen[0]).to.be.instanceOf(AuthenticationError);
    expect(m.isAuthenticated()).to.equal(false);
  });

  it("does not loop when everything keeps answering 401", async function () {
    let hits = 0;
    const stub = stubFetch(() => {
      hits += 1;
      return { status: 401 };
    });
    restore = stub.restore;

    await manager().request("/agents").catch(() => undefined);
    // original + refresh + one retry
    expect(hits).to.equal(3);
  });

  it("shares a single refresh between concurrent 401s", async function () {
    let refreshes = 0;
    const stub = stubFetch((url) => {
      if (url.endsWith("/auth/refresh")) {
        refreshes += 1;
        return { status: 200 };
      }
      return { status: 401 };
    });
    restore = stub.restore;

    const m = manager();
    // all three fail 401 the first time, so all three queue on one refresh
    await Promise.all([m.request("/a"), m.request("/b"), m.request("/c")]).catch(() => undefined);
    expect(refreshes).to.equal(1);
  });

  it("surfaces a failed refresh as AuthenticationError", async function () {
    const seen: AuthenticationError[] = [];
    const stub = stubFetch((url) => (url.endsWith("/auth/refresh") ? { status: 500 } : { status: 401 }));
    restore = stub.restore;

    const m = manager({ onAuthFailure: (e: AuthenticationError) => seen.push(e) });
    let caught: any;
    try {
      await m.request("/agents");
    } catch (error) {
      caught = error;
    }
    expect(caught).to.be.instanceOf(AuthenticationError);
    expect(caught.message).to.match(/refresh failed/);
    expect(seen.length).to.equal(1);
  });

  it("passes successful responses straight through without refreshing", async function () {
    const stub = stubFetch(() => ({ status: 200 }));
    restore = stub.restore;

    await manager().request("/agents");
    expect(stub.calls.length).to.equal(1);
    expect(stub.calls[0].auth).to.equal("Bearer tok-first");
  });

  it("still throws immediately when autoRefresh is off", async function () {
    const stub = stubFetch(() => ({ status: 401 }));
    restore = stub.restore;

    const m = manager({ autoRefresh: false });
    await expect(m.request("/agents")).to.be.rejectedWith(AuthenticationError);
    expect(stub.calls.filter((c) => c.url.endsWith("/auth/refresh")).length).to.equal(0);
  });

  it("refreshes proactively when the cached token has expired", async function () {
    const stub = stubFetch((url) => (url.endsWith("/auth/refresh") ? { status: 200 } : { status: 200 }));
    restore = stub.restore;

    const m = manager();
    (m as any).currentToken = TOKEN("old", -10);
    await m.request("/agents");
    expect(stub.calls.some((c) => c.url.endsWith("/auth/refresh"))).to.equal(true);
  });
});
