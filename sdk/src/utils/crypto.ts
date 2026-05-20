/**
 * @generated-by
 * name: oocheol
 * timestamp: 2026-05-19T10:45:00Z
 * platform_instructions: Interactive Engineering Agent specializing in surgical codebase modifications and high-integrity PR submissions. Core mandates: Security (protecting credentials/.env), Efficiency (minimizing context/tokens), and Engineering Excellence (idiomatic code, exhaustive testing, and non-destructive changes). Operating under a Research-Strategy-Execution lifecycle with a Plan-Act-Validate execution loop.
 * runtime: {"os":"win32","arch":"x64","home_dir":"C:\\Users\\PC","working_dir":"C:\\chromeMCP\\OpenAgents","shell":"powershell"}
 *
 * Secure cryptographic utilities with CSPRNG nonce generation, PBKDF2 key derivation, and signature validation.
 */

import { createHash, createHmac, randomBytes, pbkdf2Sync } from "crypto";
import { ec as EC } from "elliptic";

const secp256k1 = new EC("secp256k1");

export interface KeyPair {
  publicKey: string;
  privateKey: string;
}

/**
 * Generates a random keypair using secp256k1.
 */
export function generateKeyPair(): KeyPair {
  const key = secp256k1.genKeyPair();
  return {
    publicKey: key.getPublic("hex"),
    privateKey: key.getPrivate("hex"),
  };
}

/**
 * Computes keccak256 hash (simulated via sha3-256 for this protocol).
 */
export function keccak256(data: string | Buffer): string {
  const input = typeof data === "string" ? Buffer.from(data, "utf-8") : data;
  return createHash("sha3-256").update(input).digest("hex");
}

/**
 * Derives a key using PBKDF2 with a random salt or provided salt.
 */
export function deriveKey(
  password: string, 
  salt?: Buffer, 
  iterations = 100_000, 
  keylen = 32
): { key: Buffer; salt: Buffer } {
  const actualSalt = salt || randomBytes(16);
  const key = pbkdf2Sync(password, actualSalt, iterations, keylen, "sha256");
  return { key, salt: actualSalt };
}

/**
 * Generates a cryptographically secure nonce.
 */
export function generateNonce(length = 32): string {
  return randomBytes(length).toString("hex");
}

/**
 * Signs a message using secp256k1 private key.
 */
export function signMessage(privateKey: string, message: string): string {
  const msgHash = keccak256(message);
  const key = secp256k1.keyFromPrivate(privateKey, "hex");
  const signature = key.sign(msgHash);
  return signature.toDER("hex");
}

/**
 * Verifies a secp256k1 signature.
 * Includes validation of signature format and length.
 */
export function verifySignature(
  publicKey: string,
  message: string,
  signature: string
): boolean {
  // SECURITY: Validate signature length and format before processing
  if (!signature || signature.length < 64 || signature.length > 144) {
    return false;
  }

  const msgHash = keccak256(message);
  try {
    const key = secp256k1.keyFromPublic(publicKey, "hex");
    // Ensure DER format is valid
    return key.verify(msgHash, signature);
  } catch {
    return false;
  }
}

/**
 * Hashes a personal message with Ethereum-style prefix.
 */
export function hashPersonalMessage(message: string): string {
  const prefix = `\x19Ethereum Signed Message:\n${message.length}`;
  return keccak256(prefix + message);
}

/**
 * Recovers public key from message and signature.
 */
export function recoverPublicKey(
  message: string,
  signature: string,
  recoveryParam: number
): string {
  if (recoveryParam < 0 || recoveryParam > 3) {
    throw new Error("Invalid recovery param");
  }
  const msgHash = Buffer.from(keccak256(message), "hex");
  const recovered = secp256k1.recoverPubKey(msgHash, signature, recoveryParam);
  return recovered.encode("hex", false);
}
