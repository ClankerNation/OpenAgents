const assert = require("assert");
process.env.TS_NODE_COMPILER_OPTIONS = JSON.stringify({
  module: "commonjs",
  target: "es2020",
  moduleResolution: "node",
  ignoreDeprecations: "6.0",
});
require("ts-node/register/transpile-only");

const { WebSocketProvider } = require("../sdk/src/providers/websocket.ts");

class MockWebSocket {
  static instances = [];
  static listenerCountValue = 1;

  constructor(url) {
    this.url = url;
    this.onopen = null;
    this.onmessage = null;
    this.onclose = null;
    this.onerror = null;
    this.sent = [];
    this.closed = false;
    this.removeAllListenersCalled = false;
    MockWebSocket.instances.push(this);
  }

  send(message) {
    this.sent.push(message);
  }

  close() {
    this.closed = true;
    this.onclose?.();
  }

  removeAllListeners() {
    this.removeAllListenersCalled = true;
  }

  listenerCount(event) {
    return event === "message" ? MockWebSocket.listenerCountValue : 0;
  }

  open() {
    this.onopen?.();
  }

  message(payload) {
    this.onmessage?.({ data: JSON.stringify(payload) });
  }
}

describe("WebSocketProvider listener cleanup", function () {
  let originalWebSocket;
  let originalWarn;

  beforeEach(function () {
    originalWebSocket = global.WebSocket;
    originalWarn = console.warn;
    MockWebSocket.instances = [];
    MockWebSocket.listenerCountValue = 1;
    global.WebSocket = MockWebSocket;
  });

  afterEach(function () {
    global.WebSocket = originalWebSocket;
    console.warn = originalWarn;
  });

  async function connectAndOpen(provider) {
    const promise = provider.connect();
    MockWebSocket.instances.at(-1).open();
    await promise;
  }

  it("cleans old socket handlers across repeated reconnects", async function () {
    const provider = new WebSocketProvider({ url: "ws://example.test" });
    let calls = 0;

    await connectAndOpen(provider);
    provider.subscriptions.set("sub-1", () => calls++);

    for (let i = 0; i < 10; i++) {
      await connectAndOpen(provider);
    }

    for (const socket of MockWebSocket.instances) {
      socket.message({ method: "eth_subscription", params: { subscription: "sub-1", result: "data" } });
    }

    assert.equal(calls, 1);
    assert(MockWebSocket.instances.slice(0, -1).every((socket) => socket.removeAllListenersCalled));
    assert(MockWebSocket.instances.slice(0, -1).every((socket) => socket.onmessage === null));
  });

  it("ignores stale socket callbacks after socket replacement", async function () {
    const provider = new WebSocketProvider({ url: "ws://example.test" });
    let disconnected = 0;
    provider.on("disconnected", () => disconnected++);

    await connectAndOpen(provider);
    const stale = MockWebSocket.instances[0];
    await connectAndOpen(provider);

    stale.onclose?.();

    assert.equal(disconnected, 0);
  });

  it("warns when message listener count exceeds the threshold", async function () {
    const warnings = [];
    console.warn = (message) => warnings.push(message);
    MockWebSocket.listenerCountValue = 12;

    const provider = new WebSocketProvider({ url: "ws://example.test", listenerWarningThreshold: 10 });
    await connectAndOpen(provider);

    assert.equal(warnings.length, 1);
    assert.match(warnings[0], /listener count 12 exceeds threshold 10/);
  });
});
