/**
 * @contributor Codex Agent xyjk0511
 * @platform Safety-preserving Codex execution context; private system and developer instructions are not embedded in source.
 * @runtime Microsoft Windows 10.0.22631, X64, redacted local paths, shell PowerShell 7.6.2
 * @date 2026-05-31T00:00:00-07:00
 */

const assert = require("assert");
process.env.TS_NODE_COMPILER_OPTIONS = JSON.stringify({
  module: "commonjs",
  target: "es2020",
  moduleResolution: "node",
  ignoreDeprecations: "6.0",
});
require("ts-node/register/transpile-only");

const { SessionManager } = require("../sdk/src/auth/session.ts");

function token(tokenValue, refreshToken, expiresAt) {
  return {
    token: tokenValue,
    refreshToken,
    expiresAt,
    walletAddress: "0xabc",
  };
}

function jsonResponse(body, ok = true, status = 200) {
  return {
    ok,
    status,
    async json() {
      return body;
    },
  };
}

describe("SessionManager token hardening", function () {
  let originalFetch;
  let originalDateNow;
  let originalWindow;
  let originalLocalStorage;
  const nowSeconds = 2_000_000;

  beforeEach(function () {
    originalFetch = global.fetch;
    originalDateNow = Date.now;
    originalWindow = global.window;
    originalLocalStorage = global.localStorage;
    Date.now = () => nowSeconds * 1000;
  });

  afterEach(function () {
    global.fetch = originalFetch;
    Date.now = originalDateNow;
    global.window = originalWindow;
    global.localStorage = originalLocalStorage;
  });

  function createManager() {
    return new SessionManager({
      wallet: {
        address: "0xabc",
        async sendTransaction() {
          return "0xsigned";
        },
      },
      apiBaseUrl: "https://api.example.test",
    });
  }

  it("does not read from or write to localStorage", function () {
    const trap = {
      getItem() {
        throw new Error("localStorage getItem should not be used");
      },
      setItem() {
        throw new Error("localStorage setItem should not be used");
      },
      removeItem() {
        throw new Error("localStorage removeItem should not be used");
      },
    };
    global.window = { localStorage: trap };
    global.localStorage = trap;

    const manager = createManager();
    manager.logout();

    assert.equal(manager.isAuthenticated(), false);
  });

  it("refreshes expired tokens and stores rotated refresh tokens in memory", async function () {
    const manager = createManager();
    manager.currentToken = token("old-access", "old-refresh", nowSeconds - 1);
    let refreshCalls = 0;

    global.fetch = async (url, options) => {
      refreshCalls++;
      assert.equal(url, "https://api.example.test/auth/refresh");
      assert.deepEqual(JSON.parse(options.body), { refreshToken: "old-refresh" });
      return jsonResponse(token("new-access", "new-refresh", nowSeconds + 3600));
    };

    const accessToken = await manager.getToken();

    assert.equal(accessToken, "new-access");
    assert.equal(refreshCalls, 1);
    assert.equal(manager.currentToken.refreshToken, "new-refresh");
    assert.equal(manager.isAuthenticated(), true);
  });

  it("coalesces concurrent refreshes into one network request", async function () {
    const manager = createManager();
    manager.currentToken = token("expired-access", "shared-refresh", nowSeconds - 1);
    let refreshCalls = 0;
    let releaseRefresh;

    global.fetch = async () => {
      refreshCalls++;
      await new Promise((resolve) => {
        releaseRefresh = resolve;
      });
      return jsonResponse(token("coalesced-access", "rotated-refresh", nowSeconds + 3600));
    };

    const first = manager.getToken();
    const second = manager.getToken();
    const third = manager.getToken();
    releaseRefresh();

    const results = await Promise.all([first, second, third]);

    assert.deepEqual(results, ["coalesced-access", "coalesced-access", "coalesced-access"]);
    assert.equal(refreshCalls, 1);
    assert.equal(manager.currentToken.refreshToken, "rotated-refresh");
  });
});
