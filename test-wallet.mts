// Tests for Wallet: key not on object, clear() zeros, chainId check.
import { Wallet } from "./sdk/src/auth/wallet";

let passed = 0, failed = 0;
function assert(cond: boolean, msg: string) {
  if (cond) { console.log("  ok -", msg); passed++; }
  else { console.error("  FAIL -", msg); failed++; }
}

// Mock provider
const mockProvider = {
  getChainId: () => 1,
  call: async () => "0x1",
  getBalance: async () => 0n,
};

const privKey = "0x" + "aa".repeat(32);

// Test 1: private key not enumerable on the object
{
  console.log("test 1: key not visible via Object.keys");
  const w = new Wallet({ privateKey: privKey, provider: mockProvider as any });
  const keys = Object.keys(w);
  assert(!keys.includes("privateKey"), "privateKey not in Object.keys");
  assert(!keys.includes("_privateKey"), "_privateKey not in Object.keys");
  // JSON.stringify should not leak key
  const json = JSON.stringify(w);
  assert(!json.includes(privKey.slice(2)), "key not in JSON.stringify output");
}

// Test 2: clear() zeros the key
{
  console.log("test 2: clear() zeros the key");
  const w = new Wallet({ privateKey: privKey, provider: mockProvider as any });
  const before = (w as any).exportPrivateKey();
  w.clear();
  const after = (w as any).exportPrivateKey();
  assert(after === "", "key emptied after clear(), got: " + after.slice(0,10));
}

// Test 3: chainId mismatch throws
{
  console.log("test 3: chainId mismatch throws");
  const w = new Wallet({ privateKey: privKey, provider: mockProvider as any });
  let threw = false;
  try {
    await w.signTransaction({
      to: "0x1111111111111111111111111111111111111111",
      value: 0n, data: "0x", gasLimit: 21000n,
      chainId: 999, // mismatch (provider=1)
    });
  } catch (e: any) { threw = /Chain ID mismatch/.test(e.message); }
  assert(threw, "chain mismatch rejected");
}

console.log(`\n${passed} passed, ${failed} failed`);
process.exit(failed ? 1 : 0);
