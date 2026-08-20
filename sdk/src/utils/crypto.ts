// @fix-author rafaio1
// @date 2026-08-20T00:00:00Z
// @runtime linux x64 /tmp/OpenAgents bash
// @platform-config Agentic bounty-hunter workflow

import { createHash, createHmac, randomBytes } from "crypto";
import { ec as EC } from "elliptic";

const secp256k1 = new EC("secp256k1");

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

/**
 * Derive a key from a password using HMAC-based KDF with configurable rounds.
 * Uses a unique random salt per invocation for security.
 * @param password The password to derive from
 * @param iterations Number of HMAC iterations (default 100,000)
 * @param salt Optional custom salt; if not provided, generates a random 32-byte salt
 * @returns Object containing the derived key and the salt used
 */
export function deriveKey(
  password: string,
  iterations: number = 100_000,
  salt?: Buffer
): { key: Buffer; salt: Buffer } {
  const usedSalt = salt ?? randomBytes(32);
  let result = createHmac("sha256", usedSalt).update(password).digest();
  for (let i = 1; i < iterations; i++) {
    result = createHmac("sha256", usedSalt).update(result).digest();
  }
  return { key: result, salt: usedSalt };
}

/**
 * Generate a cryptographically secure nonce using CSPRNG.
 * @param bytes Number of random bytes (default 32)
 * @returns Hex-encoded random nonce
 */
export function generateNonce(bytes: number = 32): string {
  return randomBytes(bytes).toString("hex");
}

/**
 * Generate a unique random salt for cryptographic operations.
 * @param bytes Number of random bytes (default 32)
 * @returns Random salt as Buffer
 */
export function generateSalt(bytes: number = 32): Buffer {
  return randomBytes(bytes);
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
  // Validate signature length — DER-encoded secp256k1 signatures are typically 70-72 bytes (140-144 hex chars)
  if (!signature || signature.length < 130 || signature.length > 144) {
    return false;
  }
  // Validate hex format
  if (!/^[0-9a-fA-F]+$/.test(signature)) {
    return false;
  }
  const msgHash = keccak256(message);
  try {
    const key = secp256k1.keyFromPublic(publicKey, "hex");
    return key.verify(msgHash, signature);
  } catch {
    return false;
  }
}

export function hashPersonalMessage(message: string): string {
  const prefix = `\x19Ethereum Signed Message:\n${message.length}`;
  return keccak256(prefix + message);
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
