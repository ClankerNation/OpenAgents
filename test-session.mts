// Tests for SessionManager: no localStorage, expiry check, refresh coalescing.
import { SessionManager } from "./sdk/src/auth/session";

let passed = 0, failed = 0;
function assert(cond: boolean, msg: string) {
  if (cond) { console.log("  ok -", msg); passed++; }
  else { console.error("  FAIL -", msg); failed++; }
}

// Mock wallet
const mockWallet = { address: "0xabc", sendTransaction: async () => "0xsig" };

// Test 1: no localStorage access
{
  console.log("test 1: never touches localStorage");
  let localStorageTouched = false;
  // @ts-ignore
  global.window = { localStorage: { getItem: () => { localStorageTouched = true; return null; }, setItem: () => { localStorageTouched = true; }, removeItem: () => { localStorageTouched = true; } } };
  const s = new SessionManager({ wallet: mockWallet as any, apiBaseUrl: "http://x" });
  assert(!localStorageTouched, "constructor does not read localStorage");
  // @ts-ignore
  delete global.window;
}

// Test 2: expired token triggers refresh
{
  console.log("test 2: expired token auto-refreshes");
  let refreshCalls = 0;
  // @ts-ignore
  global.fetch = async (url: string) => {
    if (url.includes("/auth/refresh")) {
      refreshCalls++;
      return { ok: true, json: async () => ({ token: "new", expiresAt: Math.floor(Date.now()/1000) + 3600, refreshToken: "rt2", walletAddress: "0xabc" }) };
    }
    return { ok: false, status: 401, json: async () => ({}) };
  };
  const s = new SessionManager({ wallet: mockWallet as any, apiBaseUrl: "http://x" });
  // @ts-ignore
  s.currentToken = { token: "old", expiresAt: Math.floor(Date.now()/1000) - 100, refreshToken: "rt1", walletAddress: "0xabc" };
  const t = await s.getToken();
  assert(t === "new", "got refreshed token");
  assert(refreshCalls === 1, "refresh called once");
}

// Test 3: concurrent refresh coalesced
{
  console.log("test 3: concurrent refresh coalesced");
  let refreshCalls = 0;
  // @ts-ignore
  global.fetch = async (url: string) => {
    if (url.includes("/auth/refresh")) {
      refreshCalls++;
      await new Promise(r => setTimeout(r, 50));
      return { ok: true, json: async () => ({ token: "t" + refreshCalls, expiresAt: Math.floor(Date.now()/1000) + 3600, refreshToken: "rt", walletAddress: "0xabc" }) };
    }
    return { ok: false, status: 401, json: async () => ({}) };
  };
  const s = new SessionManager({ wallet: mockWallet as any, apiBaseUrl: "http://x" });
  // @ts-ignore
  s.currentToken = { token: "old", expiresAt: Math.floor(Date.now()/1000) - 10, refreshToken: "rt", walletAddress: "0xabc" };
  const [a, b, c] = await Promise.all([s.getToken(), s.getToken(), s.getToken()]);
  assert(refreshCalls === 1, `only 1 refresh call, got ${refreshCalls}`);
  assert(a === b && b === c, "all got same token");
}

console.log(`\n${passed} passed, ${failed} failed`);
process.exit(failed ? 1 : 0);
