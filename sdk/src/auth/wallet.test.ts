import assert from "assert";
import { Wallet } from "./wallet";
import { RpcProvider } from "../providers/rpc";

class MockProvider extends RpcProvider {
  calls: Array<{ method: string; params: unknown[] }> = [];
  private nonce = 0;

  constructor(chainId = 8453) {
    super({ url: "http://127.0.0.1:8545", chainId });
  }

  async call(method: string, params: unknown[] = []): Promise<unknown> {
    this.calls.push({ method, params });
    if (method === "eth_getTransactionCount") {
      return `0x${(this.nonce++).toString(16)}`;
    }
    if (method === "eth_gasPrice") {
      return "0x1";
    }
    if (method === "eth_sendRawTransaction") {
      return "0xsent";
    }
    throw new Error(`unexpected call: ${method}`);
  }
}

const PRIVATE_KEY =
  "1111111111111111111111111111111111111111111111111111111111111111";

async function testFreshPendingNonce() {
  const provider = new MockProvider();
  const wallet = new Wallet({ privateKey: PRIVATE_KEY, provider });

  assert.equal(await wallet.getNonce(), 0);
  assert.equal(await wallet.getNonce(), 1);
  assert.deepEqual(
    provider.calls
      .filter((call) => call.method === "eth_getTransactionCount")
      .map((call) => call.params[1]),
    ["pending", "pending"]
  );
}

async function testRejectsMissingOrMismatchedChain() {
  const provider = new MockProvider(8453);
  const wallet = new Wallet({ privateKey: PRIVATE_KEY, provider });

  await assert.rejects(
    () => wallet.signTransaction({
      to: "0x0000000000000000000000000000000000000001",
      value: 0n,
      data: "0x",
      gasLimit: 21_000n,
    }),
    /chainId is required/
  );

  await assert.rejects(
    () => wallet.signTransaction({
      to: "0x0000000000000000000000000000000000000001",
      value: 0n,
      data: "0x",
      gasLimit: 21_000n,
      chainId: 1,
    }),
    /does not match/
  );
}

async function testDestroysKeyAfterSigning() {
  const provider = new MockProvider(8453);
  const wallet = new Wallet({ privateKey: PRIVATE_KEY, provider });

  await wallet.signTransaction({
    to: "0x0000000000000000000000000000000000000001",
    value: 0n,
    data: "0x",
    gasLimit: 21_000n,
    chainId: 8453,
  });

  assert.throws(() => wallet.exportPrivateKey(), /destroyed/);
  await assert.rejects(
    () => wallet.signTransaction({
      to: "0x0000000000000000000000000000000000000001",
      value: 0n,
      data: "0x",
      gasLimit: 21_000n,
      chainId: 8453,
    }),
    /destroyed/
  );
}

async function run() {
  await testFreshPendingNonce();
  await testRejectsMissingOrMismatchedChain();
  await testDestroysKeyAfterSigning();
}

run().catch((error) => {
  console.error(error);
  process.exit(1);
});
