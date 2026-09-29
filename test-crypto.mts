import { generateNonce, deriveKey, verifySignature, signMessage, generateKeyPair } from "./sdk/src/utils/crypto";

let passed = 0, failed = 0;
function assert(cond: boolean, msg: string) {
  if (cond) { console.log("  ok -", msg); passed++; }
  else { console.error("  FAIL -", msg); failed++; }
}

// 1. CSPRNG nonce
{
  console.log("test 1: nonce is CSPRNG-backed hex");
  const a = generateNonce();
  const b = generateNonce();
  assert(/^[0-9a-f]{64}$/.test(a), "nonce is 64 hex chars, got: " + a.slice(0, 16) + "...");
  assert(a !== b, "nonces are unique");
  assert(!/\d/.test(a.replace(/[0-9a-f]/g, "")) && a.length === 64, "nonce format valid");
}

// 2. Invalid signature lengths rejected
{
  console.log("test 2: invalid signature lengths rejected");
  const { publicKey } = generateKeyPair();
  const msg = "hello";
  assert(verifySignature(publicKey, msg, "") === false, "empty sig rejected");
  assert(verifySignature(publicKey, msg, "0x1234") === false, "short sig rejected");
  assert(verifySignature(publicKey, msg, "0x" + "ff".repeat(100)) === false, "long sig rejected");
  assert(verifySignature(publicKey, msg, "zzzz") === false, "non-hex sig rejected");
  const good = signMessage(generateKeyPair().privateKey, msg);
  assert(verifySignature(publicKey, msg, good) === false, "wrong-key sig rejected");
}

// 3. Valid signature accepted
{
  console.log("test 3: valid signature accepted");
  const kp = generateKeyPair();
  const sig = signMessage(kp.privateKey, "data");
  assert(verifySignature(kp.publicKey, "data", sig) === true, "valid sig verifies");
  assert(verifySignature(kp.publicKey, "tampered", sig) === false, "tampered msg rejected");
}

// 4. KDF unique salts + configurable rounds
{
  console.log("test 4: KDF unique salts");
  const d1 = deriveKey("password123");
  const d2 = deriveKey("password123");
  assert(d1.salt !== d2.salt, "salts are unique per call");
  assert(d1.key.length === 32, "key is 32 bytes");
  // Deterministic when salt provided
  const d3 = deriveKey("password123", 100_000, d1.salt);
  assert(d3.key.equals(d1.key), "same salt+password => same key");
  const d4 = deriveKey("pw", 2000, d1.salt);
  assert(!d4.key.equals(d1.key), "different rounds => different key");
}

console.log(`\n${passed} passed, ${failed} failed`);
process.exit(failed ? 1 : 0);
