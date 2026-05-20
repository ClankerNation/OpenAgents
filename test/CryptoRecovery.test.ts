import assert from "node:assert/strict";
import { ec as EC } from "elliptic";
import { computeAddress } from "ethers";

import {
  isValidSignature,
  keccak256,
  normalizePublicKey,
  publicKeyToAddress,
  recoverAddress,
  recoverPublicKey,
  verifySignature,
} from "../sdk/src/utils/crypto";

const secp256k1 = new EC("secp256k1");
const privateKey = "1".padStart(64, "0");
const key = secp256k1.keyFromPrivate(privateKey, "hex");
const message = "openagents recovery bounty";
const messageHash = Buffer.from(keccak256(message), "hex");
const signature = key.sign(messageHash, { canonical: true });
const recoveryBit = signature.recoveryParam ?? 0;
const compactSignature = `${signature.r.toString("hex").padStart(64, "0")}${signature.s
  .toString("hex")
  .padStart(64, "0")}`;
const compactSignatureWithRecovery = `${compactSignature}${(recoveryBit + 27)
  .toString(16)
  .padStart(2, "0")}`;
const derSignature = signature.toDER("hex");
const publicKey = key.getPublic("hex");
const compressedPublicKey = key.getPublic(true, "hex");
const expectedAddress = computeAddress(`0x${privateKey}`).toLowerCase();

assert.equal(recoverPublicKey(message, derSignature, recoveryBit), publicKey);
assert.equal(recoverPublicKey(message, compactSignature, recoveryBit, "compressed"), compressedPublicKey);
assert.equal(normalizePublicKey(compressedPublicKey), publicKey);
assert.equal(publicKeyToAddress(publicKey).toLowerCase(), expectedAddress);
assert.equal(publicKeyToAddress(compressedPublicKey).toLowerCase(), expectedAddress);
assert.equal(recoverAddress(message, compactSignature, recoveryBit).toLowerCase(), expectedAddress);
assert.equal(isValidSignature(message, derSignature, expectedAddress), true);
assert.equal(isValidSignature(message, compactSignatureWithRecovery, expectedAddress), true);
assert.equal(isValidSignature("tampered", compactSignatureWithRecovery, expectedAddress), false);
assert.equal(verifySignature(compressedPublicKey, message, compactSignature), true);

console.log("Crypto recovery tests passed");
