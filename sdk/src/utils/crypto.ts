/**
 * @contributor doubao-agent (spiritwanghs fork)
 * @platform-config Autonomous coding agent executing GitHub bounties; user asked to do all available bounty issues.
 * @env os=linux arch=x64 home_dir=/home/user working_dir=/home/user/Doubao/chats/38444718400345090/OpenAgents shell=bash
 * @timestamp 2026-09-29T03:00:00Z
 */
import { createHash, createHmac, randomBytes, pbkdf2Sync } from "crypto";
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

export interface DerivedKey {
  salt: string;
  key: Buffer;
}

/**
 * KDF with a per-operation random salt and configurable rounds.
 * Returns the salt alongside the key so it can be stored for verification.
 */
export function deriveKey(
  password: string,
  iterations = 100_000,
  salt?: string
): DerivedKey {
  const saltBuf = salt ? Buffer.from(salt, "hex") : randomBytes(16);
  const key = pbkdf2Sync(password, saltBuf, iterations, 32, "sha256");
  return { salt: saltBuf.toString("hex"), key };
}

export function generateNonce(): string {
  // CSPRNG-backed nonce — 32 random bytes = 64 hex chars.
  return randomBytes(32).toString("hex");
}

// Minimum plausible DER-encoded ECDSA signature length:
// 0x30 0x44/0x45 ... (2 header + up to 33 r + 2 + up to 33 s)
const MIN_SIG_LEN = 8;
const MAX_SIG_LEN = 72;

function isValidSignature(signature: string): boolean {
  if (typeof signature !== "string" || signature.length === 0) return false;
  const hex = signature.startsWith("0x") ? signature.slice(2) : signature;
  if (!/^[0-9a-fA-F]+$/.test(hex)) return false;
  const bytes = hex.length / 2;
  if (bytes < MIN_SIG_LEN || bytes > MAX_SIG_LEN) return false;
  // DER: must start with 0x30 (SEQUENCE)
  const first = parseInt(hex.slice(0, 2), 16);
  return first === 0x30;
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
  // Reject malformed signatures up front instead of letting them through.
  if (!isValidSignature(signature)) return false;
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
  if (!isValidSignature(signature)) throw new Error("Invalid signature");
  const msgHash = Buffer.from(keccak256(message), "hex");
  const recovered = secp256k1.recoverPubKey(msgHash, signature, recoveryParam);
  return recovered.encode("hex", false);
}
