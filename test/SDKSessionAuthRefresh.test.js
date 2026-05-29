process.env.TS_NODE_IGNORE_DIAGNOSTICS = "5102";
process.env.TS_NODE_COMPILER_OPTIONS = JSON.stringify({
  module: "commonjs",
  target: "es2020",
});

require("ts-node/register/transpile-only");

const { expect } = require("chai");
const { SessionManager, AuthenticationError } = require("../sdk/src/auth/session.ts");

function token(value) {
  return {
    token: value,
    refreshToken: `${value}-refresh`,
    expiresAt: Math.floor(Date.now() / 1000) + 3600,
    walletAddress: "0xabc",
  };
}

function response(status, body = {}) {
  return {
    status,
    ok: status >= 200 && status < 300,
    json: async () => body,
  };
}

function makeSession(config = {}) {
  const session = new SessionManager({
    wallet: { address: "0xabc", sendTransaction: async () => "0xsig" },
    apiBaseUrl: "https://api.example",
    ...config,
  });
  session.currentToken = token("old-token");
  return session;
}

describe("SessionManager auth refresh", function () {
  let originalFetch;

  beforeEach(function () {
    originalFetch = global.fetch;
  });

  afterEach(function () {
    global.fetch = originalFetch;
  });

  it("refreshes on 401 and retries the original request once", async function () {
    const calls = [];
    const refreshed = token("new-token");

    global.fetch = async (url, init) => {
      const auth = init.headers?.get ? init.headers.get("Authorization") : init.headers?.Authorization;
      calls.push({ url, auth });
      if (calls.length === 1) return response(401);
      if (calls.length === 2) return response(200, refreshed);
      return response(200, { ok: true });
    };

    const session = makeSession();
    const res = await session.request("/agents");

    expect(res.status).to.equal(200);
    expect(calls).to.deep.equal([
      { url: "https://api.example/agents", auth: "Bearer old-token" },
      { url: "https://api.example/auth/refresh", auth: undefined },
      { url: "https://api.example/agents", auth: "Bearer new-token" },
    ]);
  });

  it("throws AuthenticationError after a second 401", async function () {
    global.fetch = async (url) => {
      if (url.endsWith("/auth/refresh")) return response(200, token("new-token"));
      return response(401);
    };

    let thrown;
    try {
      await makeSession().fetch("/tasks");
    } catch (error) {
      thrown = error;
    }

    expect(thrown).to.be.instanceOf(AuthenticationError);
    expect(thrown.message).to.equal("Authentication failed after refresh");
  });

  it("fires onAuthFailure on final authentication failure", async function () {
    const failures = [];
    global.fetch = async (url) => {
      if (url.endsWith("/auth/refresh")) return response(500);
      return response(401);
    };

    let thrown;
    try {
      await makeSession({ onAuthFailure: (error) => failures.push(error.message) }).request("/health");
    } catch (error) {
      thrown = error;
    }

    expect(thrown).to.be.instanceOf(AuthenticationError);
    expect(failures).to.deep.equal(["Refresh failed: 500"]);
  });
});
