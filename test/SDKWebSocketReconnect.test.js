process.env.TS_NODE_IGNORE_DIAGNOSTICS = "5102";
process.env.TS_NODE_COMPILER_OPTIONS = JSON.stringify({
  module: "commonjs",
  target: "es2020",
});

require("ts-node/register/transpile-only");

const { expect } = require("chai");
const { WebSocketProvider } = require("../sdk/src/providers/websocket.ts");

const tick = () => new Promise((resolve) => setTimeout(resolve, 0));

describe("WebSocketProvider reconnect listeners", function () {
  let OriginalWebSocket;
  let sockets;

  class FakeWebSocket {
    constructor(url) {
      this.url = url;
      this.sent = [];
      this.removed = 0;
      sockets.push(this);
    }

    send(data) {
      this.sent.push(data);
    }

    close() {
      this.onclose?.();
    }

    removeAllListeners() {
      this.removed += 1;
    }

    open() {
      this.onopen?.();
    }

    message(data) {
      this.onmessage?.({ data: JSON.stringify(data) });
    }
  }

  beforeEach(function () {
    OriginalWebSocket = global.WebSocket;
    sockets = [];
    global.WebSocket = FakeWebSocket;
  });

  afterEach(function () {
    global.WebSocket = OriginalWebSocket;
  });

  it("handles each message once after repeated reconnects", async function () {
    const provider = new WebSocketProvider({
      url: "ws://example",
      reconnectIntervalMs: 0,
      maxReconnectAttempts: 12,
    });

    const initialConnect = provider.connect();
    sockets[0].open();
    await initialConnect;

    for (let i = 0; i < 10; i++) {
      sockets[i].close();
      await tick();
      sockets[i + 1].open();
    }

    let deliveries = 0;
    provider.subscriptions.set("sub-1", () => {
      deliveries += 1;
    });

    for (const socket of sockets) {
      socket.message({
        jsonrpc: "2.0",
        method: "eth_subscription",
        params: { subscription: "sub-1", result: "payload" },
      });
    }

    expect(deliveries).to.equal(1);
    for (const staleSocket of sockets.slice(0, -1)) {
      expect(staleSocket.removed).to.equal(1);
    }
  });

  it("warns when provider message listeners exceed the configured threshold", async function () {
    const warnings = [];
    const originalWarn = console.warn;
    console.warn = (message) => warnings.push(message);

    try {
      const provider = new WebSocketProvider({
        url: "ws://example",
        listenerWarningThreshold: 1,
      });
      provider.on("message", () => {});
      provider.on("message", () => {});

      const connecting = provider.connect();
      sockets[0].open();
      await connecting;

      expect(warnings).to.deep.equal(["WebSocketProvider has 2 message listeners"]);
    } finally {
      console.warn = originalWarn;
    }
  });
});
