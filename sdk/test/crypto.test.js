/**
 * Tests for crypto.ts secp256k1 key recovery functions.
 * Run with: node sdk/test/crypto.test.js
 *
 * Requirements tested:
 * - recoverPublicKey (both compressed and uncompressed)
 * - publicKeyToAddress (from compressed and uncompressed keys)
 * - isValidSignature (valid, invalid, tampered)
 * - Multiple key pairs for robustness
 */
const crypto = require("crypto");
const { ec: EC } = require("elliptic");
const keccak = require("keccak");

const secp256k1 = new EC("secp256k1");

// Replicate crypto.ts logic exactly in JS

function sha3_256(data) {
  return crypto.createHash("sha3-256").update(Buffer.from(data, "utf-8")).digest("hex");
}

function keccak256Hash(data) {
  return keccak("keccak256").update(data).digest("hex");
}

function parseDERSignature(signature) {
  const buf = Buffer.from(signature, "hex");
  if (buf[0] !== 0x30) throw new Error("Invalid DER: missing SEQUENCE tag");
  let offset = 2;
  if (buf[offset] !== 0x02) throw new Error("Invalid DER: missing r INTEGER tag");
  const rLen = buf[offset + 1];
  const rBuf = buf.subarray(offset + 2, offset + 2 + rLen);
  offset += 2 + rLen;
  if (buf[offset] !== 0x02) throw new Error("Invalid DER: missing s INTEGER tag");
  const sLen = buf[offset + 1];
  const sBuf = buf.subarray(offset + 2, offset + 2 + sLen);
  const r = rBuf[0] === 0 ? rBuf.subarray(1) : rBuf;
  const s = sBuf[0] === 0 ? sBuf.subarray(1) : sBuf;
  return { r, s };
}

function recoverPublicKey(message, signature, recoveryParam, compressed = false) {
  const msgHash = Buffer.from(sha3_256(message), "hex");
  const { r, s } = parseDERSignature(signature);
  const recovered = secp256k1.recoverPubKey(
    msgHash,
    { r: r.toString("hex"), s: s.toString("hex") },
    recoveryParam
  );
  return recovered.encode("hex", compressed);
}

function publicKeyToAddress(publicKey) {
  let keyBuffer = Buffer.from(publicKey.replace(/^0x/, ""), "hex");
  if (keyBuffer.length === 33) {
    const key = secp256k1.keyFromPublic(publicKey, "hex");
    keyBuffer = Buffer.from(key.getPublic(false, "hex"), "hex");
  }
  const rawKey = keyBuffer.slice(1);
  const hash = keccak256Hash(rawKey);
  return "0x" + hash.slice(-40);
}

function isValidSignature(message, signature, expectedAddress) {
  try {
    for (const recoveryParam of [0, 1]) {
      const recoveredKey = recoverPublicKey(message, signature, recoveryParam);
      const recoveredAddress = publicKeyToAddress(recoveredKey);
      if (recoveredAddress.toLowerCase() === expectedAddress.toLowerCase()) {
        return true;
      }
    }
    return false;
  } catch {
    return false;
  }
}

// =============================================
// Test runner
// =============================================
let passed = 0;
let failed = 0;

function assert(condition, name) {
  if (condition) {
    console.log(`  \u2713 ${name}`);
    passed++;
  } else {
    console.log(`  \u2717 ${name}`);
    failed++;
  }
}

function assertEq(actual, expected, name) {
  const ok = actual === expected;
  if (ok) {
    console.log(`  \u2713 ${name}`);
    passed++;
  } else {
    console.log(`  \u2717 ${name} \u2014 expected ${expected}, got ${actual}`);
    failed++;
  }
}

// =============================================
// Setup
// =============================================
console.log("=== Setup: Generate key pair and sign message ===");
const key = secp256k1.genKeyPair();
const privateKey = key.getPrivate("hex");
const uncompressedPub = key.getPublic("hex");
const compressedPub = key.getPublic(true, "hex");

const message = "Hello, secp256k1 recovery test!";
const msgHash = sha3_256(message);
const sig = key.sign(msgHash);
const sigHex = sig.toDER("hex");
const recoveryParam = sig.recoveryParam;

console.log(`  Message: "${message}"`);
console.log(`  Recovery param: ${recoveryParam}`);

// =============================================
// Test 1-2: recoverPublicKey (both formats)
// =============================================
console.log("\n=== Test 1: recoverPublicKey (uncompressed) ===");
const recoveredUncompressed = recoverPublicKey(message, sigHex, recoveryParam, false);
assertEq(recoveredUncompressed, uncompressedPub, "Uncompressed key matches original");

console.log("\n=== Test 2: recoverPublicKey (compressed) ===");
const recoveredCompressed = recoverPublicKey(message, sigHex, recoveryParam, true);
assertEq(recoveredCompressed, compressedPub, "Compressed key matches original");

// =============================================
// Test 3: wrong recovery param = different key
// =============================================
console.log("\n=== Test 3: Wrong recovery param produces different key ===");
const wrongRecovery = recoveryParam === 0 ? 1 : 0;
const wrongKey = recoverPublicKey(message, sigHex, wrongRecovery, false);
assert(wrongKey !== uncompressedPub, "Wrong recovery param produces different key");

// =============================================
// Test 4: auto-detect recovery param
// =============================================
console.log("\n=== Test 4: Auto-detect recovery param ===");
let foundMatch = false;
for (const rp of [0, 1]) {
  const k = recoverPublicKey(message, sigHex, rp, false);
  if (k === uncompressedPub) foundMatch = true;
}
assert(foundMatch, "One of [0, 1] recovers the correct key");

// =============================================
// Test 5-7: publicKeyToAddress
// =============================================
console.log("\n=== Test 5: publicKeyToAddress from uncompressed key ===");
const addressUncompressed = publicKeyToAddress(uncompressedPub);
console.log(`  Address: ${addressUncompressed}`);
assert(addressUncompressed.startsWith("0x"), "Address starts with 0x");
assert(addressUncompressed.length === 42, "Address is 42 chars (0x + 40 hex)");
assert(/^0x[0-9a-f]{40}$/.test(addressUncompressed), "Address is valid lowercase hex");

console.log("\n=== Test 6: publicKeyToAddress from compressed key ===");
const addressCompressed = publicKeyToAddress(compressedPub);
assertEq(addressCompressed, addressUncompressed, "Compressed and uncompressed produce same address");

console.log("\n=== Test 7: publicKeyToAddress with 0x prefix ===");
const addressWithPrefix = publicKeyToAddress("0x" + uncompressedPub);
assertEq(addressWithPrefix, addressUncompressed, "0x-prefixed input works");

// =============================================
// Test 8-11: isValidSignature
// =============================================
console.log("\n=== Test 8: isValidSignature (valid) ===");
const valid = isValidSignature(message, sigHex, addressUncompressed);
assert(valid, "Valid signature returns true");

console.log("\n=== Test 9: isValidSignature (wrong address) ===");
const wrongAddress = "0x0000000000000000000000000000000000000000";
const invalid = isValidSignature(message, sigHex, wrongAddress);
assert(!invalid, "Wrong address returns false");

console.log("\n=== Test 10: isValidSignature (tampered message) ===");
const tamperedValid = isValidSignature("Tampered message", sigHex, addressUncompressed);
assert(!tamperedValid, "Tampered message returns false");

console.log("\n=== Test 11: isValidSignature (tampered signature) ===");
const tamperedSig = "00" + sigHex.slice(2);
const tamperedSigValid = isValidSignature(message, tamperedSig, addressUncompressed);
assert(!tamperedSigValid, "Tampered signature returns false");

// =============================================
// Test 12: Full roundtrip
// =============================================
console.log("\n=== Test 12: Full roundtrip (sign -> recover -> address) ===");
const key2 = secp256k1.genKeyPair();
const msg2 = "Roundtrip test message " + Date.now();
const msgHash2 = sha3_256(msg2);
const sig2 = key2.sign(msgHash2);
const sig2Hex = sig2.toDER("hex");
const rp2 = sig2.recoveryParam;
const recoveredPub2 = recoverPublicKey(msg2, sig2Hex, rp2, false);
const addr2a = publicKeyToAddress(recoveredPub2);
const addr2b = publicKeyToAddress(key2.getPublic("hex"));
assertEq(addr2a, addr2b, "Roundtrip: sign/recover/address matches");
const valid2 = isValidSignature(msg2, sig2Hex, addr2a);
assert(valid2, "Roundtrip: isValidSignature works");

// =============================================
// Test 13: Multiple key pairs (10 random)
// =============================================
console.log("\n=== Test 13: 10 random key pairs ===");
let allPassed = true;
for (let i = 0; i < 10; i++) {
  const k = secp256k1.genKeyPair();
  const msg = `Test message ${i} \u2014 ${Math.random()}`;
  const mh = sha3_256(msg);
  const s = k.sign(mh);
  const sh = s.toDER("hex");
  const rp = s.recoveryParam;
  const recovered = recoverPublicKey(msg, sh, rp, true);
  const recoveredUncomp = recoverPublicKey(msg, sh, rp, false);
  const expectedCompressed = k.getPublic(true, "hex");
  const expectedUncompressed = k.getPublic("hex");
  if (recovered !== expectedCompressed) {
    console.log(`  \u2717 Key ${i}: compressed mismatch`);
    allPassed = false;
  }
  if (recoveredUncomp !== expectedUncompressed) {
    console.log(`  \u2717 Key ${i}: uncompressed mismatch`);
    allPassed = false;
  }
  const recoveredAddr = publicKeyToAddress(recoveredUncomp);
  const expectedAddr = publicKeyToAddress(expectedUncompressed);
  if (recoveredAddr !== expectedAddr) {
    console.log(`  \u2717 Key ${i}: address mismatch`);
    allPassed = false;
  }
}
assert(allPassed, "All 10 random key pairs pass all checks");

// =============================================
// Results
// =============================================
console.log(`\n========================================`);
console.log(`Results: ${passed} passed, ${failed} failed`);
console.log(`========================================`);
process.exit(failed > 0 ? 1 : 0);
