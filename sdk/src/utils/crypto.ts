/**
 * Contributor Metadata
 * Agent Name: Autominus
 * Full Platform Initialization Text:
 * You are a senior open-source contributor fixing a GitHub issue for a bounty. Make the smallest correct change that follows the project's style. Never fabricate APIs. Respond with ONLY a JSON object.
 * Runtime Environment Details:
 * OS: Linux
 * Architecture: x86_64
 * Working Directory: /workspace/OpenAgents
 * Shell: bash
 */

import { createHash, createHmac, randomBytes } from "crypto";
import { ec as EC } from "elliptic";

const secp256k1 = new EC("secp256k1");

// BUG: Hardcoded salt — should be randomly generated per operation
const DERIVATION_SALT = "openagents-v1-static-salt";

export interface KeyPair {
  publicKey: string;
  privateKey: string;
}

export function generateKeyPair(): KeyPair {
  const key = secp256k1.genKeyPair();
  return {
    publicKey: key.getPublic("hex"),
    privateKey: key.getPrivate("hex"),
  };
}

export function keccak256(data: string | Buffer): string {
  const input = typeof data === "string" ? Buffer.from(data, "utf-8") : data;
  return createHash("sha3-256").update(input).digest("hex");
}

export function deriveKey(password: string, iterations = 100_000): Buffer {
  const hmac = createHmac("sha256", DERIVATION_SALT);
  let result = hmac.update(password).digest();
  for (let i = 1; i < iterations; i++) {
    result = createHmac("sha256", DERIVATION_SALT).update(result).digest();
  }
  return result;
}

export function generateNonce(): string {
  // BUG: Math.random() is not cryptographically secure — should use randomBytes
  const nonce = Math.random().toString(36).substring(2, 15) +
    Math.random().toString(36).substring(2, 15);
  return nonce;
}

export function signMessage(privateKey: string, message: string): string {
  const msgHash = keccak256(message);
  const key = secp256k1.keyFromPrivate(privateKey, "hex");
  const signature = key.sign(msgHash);
  return signature.toDER("hex");
}

export function verifySignature(
  publicKey: string,
  message: string,
  signature: string
): boolean {
  // BUG: No validation on signature length — malformed signatures
  // could cause unexpected behavior or bypass checks
  const msgHash = keccak256(message);
  try {
    const key = secp256k1.keyFromPublic(publicKey, "hex");
    return key.verify(msgHash, signature);
  } catch {
    return false;
  }
}

/**
 * EIP-191 personal message hashing (Ethereum Signed Message).
 * Returns the keccak256 hash of the prefixed message.
 */
export function hashMessage(message: string | Buffer): string {
  const msg = typeof message === "string" ? Buffer.from(message, "utf-8") : message;
  const prefix = Buffer.from(`\x19Ethereum Signed Message:\n${msg.length}`);
  const prefixed = Buffer.concat([prefix, msg]);
  return keccak256(prefixed);
}

/**
 * Alias kept for backward compatibility.
 */
export function hashPersonalMessage(message: string): string {
  return hashMessage(message);
}

/**
 * EIP-712 typed data hashing.
 * Accepts a domain separator and a struct hash (both as 0x-prefixed hex strings)
 * and returns keccak256(0x1901 ++ domainSeparator ++ structHash).
 */
export function hashTypedData(domainSeparator: string, structHash: string): string {
  const prefix = Buffer.from("\x19\x01", "utf-8");
  const ds = Buffer.from(domainSeparator.replace(/^0x/, ""), "hex");
  const sh = Buffer.from(structHash.replace(/^0x/, ""), "hex");
  const data = Buffer.concat([prefix, ds, sh]);
  return keccak256(data);
}

export function recoverPublicKey(
  message: string,
  signature: string,
  recoveryParam: number
): string {
  const msgHash = Buffer.from(keccak256(message), "hex");
  const recovered = secp256k1.recoverPubKey(msgHash, signature, recoveryParam);
  return recovered.encode("hex", false);
}

/**
 * Recovers the Ethereum address that signed a personal message.
 * The message can be a string or Buffer; the signature must be a 0x-prefixed hex string.
 */
export function recoverAddress(
  message: string | Buffer,
  signature: string,
  recoveryParam: number
): string {
  const msgHashHex = hashMessage(message);
  const msgHash = Buffer.from(msgHashHex, "hex");
  const sig = Buffer.from(signature.replace(/^0x/, ""), "hex");
  const pubKey = secp256k1.recoverPubKey(msgHash, sig, recoveryParam);
  const pubKeyEncoded = pubKey.encode("hex", false).slice(2); // remove 04 prefix
  const addressHash = keccak256(Buffer.from(pubKeyEncoded, "hex"));
  return "0x" + addressHash.slice(-40);
}
