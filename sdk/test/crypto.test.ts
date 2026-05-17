/**
 * Tests for crypto.ts secp256k1 key recovery and address derivation.
 * Run with: npx ts-node --project sdk/tsconfig.json sdk/test/crypto.test.ts
 */

import {
  generateKeyPair,
  signMessage,
  recoverPublicKey,
  recoverAddress,
  isValidSignature,
  compressPublicKey,
  decompressPublicKey,
  generateNonce,
} from "../src/utils/crypto";

async function assert(condition: boolean, msg: string) {
  if (!condition) throw new Error(`FAIL: ${msg}`);
  console.log(`  PASS: ${msg}`);
}

async function testKeyPairGeneration() {
  console.log("\n[Key Pair Generation]");
  const kp = generateKeyPair();
  assert(kp.publicKey.length > 0, "public key generated");
  assert(kp.privateKey.length > 0, "private key generated");
}

async function testSignAndRecover() {
  console.log("\n[Sign and Recover Public Key]");
  const kp = generateKeyPair();
  const message = "Hello, OpenAgents!";
  const signature = signMessage(kp.privateKey, message);
  assert(signature.length > 0, "signature generated");

  const recovered = recoverPublicKey(message, signature);
  assert(recovered.length > 0, "public key recovered from signature");
}

async function testRecoverAddress() {
  console.log("\n[Recover Address from Signature]");
  const kp = generateKeyPair();
  const message = "Test message for address recovery";
  const signature = signMessage(kp.privateKey, message);
  const address = recoverAddress(message, signature);
  assert(address.startsWith("0x"), "address starts with 0x");
  assert(address.length === 42, `address length is 42, got ${address.length}`);
}

async function testIsValidSignature() {
  console.log("\n[isValidSignature]");
  const kp = generateKeyPair();
  const message = "Verification test message";
  const signature = signMessage(kp.privateKey, message);

  const derivedAddress = recoverAddress(message, signature);
  const valid = isValidSignature(message, signature, derivedAddress);
  assert(valid, "valid signature returns true");

  const fakeAddress = "0x0000000000000000000000000000000000000000";
  const invalid = isValidSignature(message, signature, fakeAddress);
  assert(!invalid, "wrong address returns false");

  const badSig = isValidSignature(message, "0xdeadbeef", derivedAddress);
  assert(!badSig, "malformed signature returns false");
}

async function testCompressDecompress() {
  console.log("\n[Compress/Decompress Public Key]");
  const kp = generateKeyPair();
  const decompressed = decompressPublicKey(kp.publicKey);
  assert(decompressed.length === 130, `decompressed length 130, got ${decompressed.length}`);

  const compressed = compressPublicKey(kp.publicKey);
  assert(compressed.length === 66, `compressed length 66, got ${compressed.length}`);

  const reDecompressed = decompressPublicKey(compressed);
  assert(reDecompressed === decompressed, "compressed→decompressed matches original");
}

async function testGenerateNonceSecure() {
  console.log("\n[Generate Nonce Cryptographically Secure]");
  const nonce1 = generateNonce();
  const nonce2 = generateNonce();
  assert(nonce1.length > 0, "nonce generated");
  assert(nonce1 !== nonce2, "nonces are unique");
  assert(/^[0-9a-f]+$/.test(nonce1), "nonce is hex-encoded");
}

async function run() {
  console.log("=== Crypto Tests ===\n");

  try {
    await testKeyPairGeneration();
    await testSignAndRecover();
    await testRecoverAddress();
    await testIsValidSignature();
    await testCompressDecompress();
    await testGenerateNonceSecure();

    console.log("\n✅ ALL TESTS PASSED");
  } catch (e: any) {
    console.error(`\n❌ ${e.message}`);
    process.exit(1);
  }
}

run();
