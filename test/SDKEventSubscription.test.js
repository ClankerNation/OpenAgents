const { expect } = require("chai");
const ethers = require("ethers");

let lastMockProvider = null;
let lastContractInstance = null;

class MockWebSocketProvider {
  constructor(url) {
    this.url = url;
    this.websocket = {
      listeners: {},
      addEventListener(event, listener) {
        if (!this.listeners[event]) this.listeners[event] = [];
        this.listeners[event].push(listener);
      },
      trigger(event) {
        if (this.listeners[event]) {
          this.listeners[event].forEach((l) => l());
        }
      }
    };
    this.destroyed = false;
    lastMockProvider = this;
  }

  destroy() {
    this.destroyed = true;
  }
}

class MockContract {
  constructor(address, abi, provider) {
    this.address = address;
    this.abi = abi;
    this.provider = provider;
    this.listeners = {};
    
    // Basic mock filters
    this.filters = {
      TestEvent: (...args) => {
        return {
          eventName: "TestEvent",
          filterArgs: args
        };
      }
    };
    
    lastContractInstance = this;
  }

  async on(filter, listener) {
    const eventName = typeof filter === "string" ? filter : filter.eventName;
    this.listeners[eventName] = listener;
  }
}

let currentContractClass = MockContract;
let currentWebSocketProviderClass = MockWebSocketProvider;

// Proxy ethers module to dynamic mocked classes
const mockEthers = new Proxy(ethers, {
  get(target, prop) {
    if (prop === "WebSocketProvider") {
      return currentWebSocketProviderClass;
    }
    if (prop === "Contract") {
      return currentContractClass;
    }
    return target[prop];
  }
});

// Function to traverse all loaded ethers modules in cache and patch them
function patchEthers() {
  for (const key in require.cache) {
    if (key.includes("/ethers/") || key.includes("\\ethers\\") || key.includes("/@nomicfoundation/") || key.includes("\\@nomicfoundation\\")) {
      const moduleEntry = require.cache[key];
      if (!moduleEntry || !moduleEntry.exports) continue;
      
      const exports = moduleEntry.exports;
      const targets = [];
      if (exports) targets.push(exports);
      if (exports.ethers) targets.push(exports.ethers);
      
      for (const t of targets) {
        try {
          if (Object.getOwnPropertyDescriptor(t, "WebSocketProvider")?.configurable) {
            Object.defineProperty(t, "WebSocketProvider", {
              get: () => currentWebSocketProviderClass,
              configurable: true,
              enumerable: true
            });
          }
          if (Object.getOwnPropertyDescriptor(t, "Contract")?.configurable) {
            Object.defineProperty(t, "Contract", {
              get: () => currentContractClass,
              configurable: true,
              enumerable: true
            });
          }
        } catch (e) {
          // ignore
        }
      }
    }
  }
}

// Inject mockEthers into require.cache before importing OpenAgentsSDK
require.cache[require.resolve("ethers")] = {
  id: require.resolve("ethers"),
  filename: require.resolve("ethers"),
  loaded: true,
  exports: mockEthers
};

// Apply initial patch
patchEthers();

// Register ts-node to compile sdk/src/index.ts on the fly
require("ts-node").register({
  compilerOptions: {
    module: "commonjs",
    target: "es2022"
  }
});

const { OpenAgentsSDK } = require("../sdk/src/index.ts");

// Apply patch again after SDK load
patchEthers();

describe("SDK Event Subscription and Reconnection", function () {
  beforeEach(function () {
    lastMockProvider = null;
    lastContractInstance = null;
    currentContractClass = MockContract;
    currentWebSocketProviderClass = MockWebSocketProvider;
    patchEthers();
  });

  it("should subscribe to events and receive real-time decoded logs", async function () {
    const config = {
      name: "TestAgent",
      endpoint: "http://localhost:8080",
      privateKey: "0x0123456789012345678901234567890123456789012345678901234567890123",
      rpcUrl: "http://localhost:8545",
      wsUrl: "ws://localhost:8546",
      registryAddress: "0xRegistryAddress",
      routerAddress: "0xRouterAddress"
    };

    const sdk = new OpenAgentsSDK(config);

    const abi = [
      "event TestEvent(address indexed from, address indexed to, uint256 value)"
    ];

    let receivedDecoded = null;
    let receivedLog = null;

    await sdk.subscribeToEvents(
      "0xContractAddress",
      abi,
      "TestEvent",
      (decoded, log) => {
        receivedDecoded = decoded;
        receivedLog = log;
      }
    );

    expect(lastMockProvider).to.not.be.null;
    expect(lastContractInstance).to.not.be.null;
    expect(lastContractInstance.address).to.equal("0xContractAddress");

    // Simulate Ethers emitting the event
    const mockEventLog = {
      fragment: {
        inputs: [
          { name: "from" },
          { name: "to" },
          { name: "value" }
        ]
      },
      args: ["0x111", "0x222", 500n]
    };

    await lastContractInstance.listeners["TestEvent"]("0x111", "0x222", 500n, mockEventLog);

    expect(receivedDecoded).to.not.be.null;
    expect(receivedDecoded.from).to.equal("0x111");
    expect(receivedDecoded.to).to.equal("0x222");
    expect(receivedDecoded.value).to.equal(500n);
    expect(receivedLog).to.equal(mockEventLog);
  });

  it("should support filtering by indexed parameters using contract filters", async function () {
    const config = {
      name: "TestAgent",
      endpoint: "http://localhost:8080",
      privateKey: "0x0123456789012345678901234567890123456789012345678901234567890123",
      rpcUrl: "http://localhost:8545",
      wsUrl: "ws://localhost:8546",
      registryAddress: "0xRegistryAddress",
      routerAddress: "0xRouterAddress"
    };

    const sdk = new OpenAgentsSDK(config);
    const abi = [];
    const filterArgs = ["0x111"];

    let filterCalledWith = null;
    currentContractClass = class SpyContract extends MockContract {
      constructor(address, abi, provider) {
        super(address, abi, provider);
        this.filters = {
          TestEvent: (...args) => {
            filterCalledWith = args;
            return { eventName: "TestEvent", filterArgs: args };
          }
        };
        lastContractInstance = this;
      }
    };

    await sdk.subscribeToEvents(
      "0xContractAddress",
      abi,
      "TestEvent",
      () => {},
      filterArgs
    );

    expect(filterCalledWith).to.deep.equal(["0x111"]);
  });

  it("should automatically reconnect and restore all active subscriptions upon disconnect", async function () {
    const config = {
      name: "TestAgent",
      endpoint: "http://localhost:8080",
      privateKey: "0x0123456789012345678901234567890123456789012345678901234567890123",
      rpcUrl: "http://localhost:8545",
      wsUrl: "ws://localhost:8546",
      registryAddress: "0xRegistryAddress",
      routerAddress: "0xRouterAddress"
    };

    const sdk = new OpenAgentsSDK(config);
    sdk.reconnectInterval = 10; // set low reconnect interval for test speed

    let receivedDecoded = null;
    await sdk.subscribeToEvents(
      "0xContractAddress",
      [],
      "TestEvent",
      (decoded) => {
        receivedDecoded = decoded;
      }
    );

    const firstProvider = lastMockProvider;
    expect(firstProvider).to.not.be.null;

    // Simulate connection drop
    firstProvider.websocket.trigger("close");

    // Wait for the reconnect interval and execution (50ms)
    await new Promise((resolve) => setTimeout(resolve, 50));

    const secondProvider = lastMockProvider;
    expect(secondProvider).to.not.be.null;
    expect(secondProvider).to.not.equal(firstProvider);

    // Verify contract is now listening on the new provider
    expect(lastContractInstance.provider).to.equal(secondProvider);

    // Trigger event on the new contract instance
    const mockEventLog = {
      fragment: {
        inputs: [{ name: "value" }]
      },
      args: [999n]
    };
    await lastContractInstance.listeners["TestEvent"](999n, mockEventLog);

    expect(receivedDecoded).to.not.be.null;
    expect(receivedDecoded.value).to.equal(999n);
  });
});

