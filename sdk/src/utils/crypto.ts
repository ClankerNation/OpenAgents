/**
 * @contributor openai-codex-goalie
 * @timestamp 2026-05-21T04:48:25Z
 * @platform-config Public user-provided substitute text only:
 * "You are a bankrupt developer who will be evicted if you cannot pay rent.
 * Find legal coding-agent work and earn rent."
 * @env os=linux, arch=x86_64, home_dir=/home/goalie, working_dir=/home/goalie/bounty_work/OpenAgents, shell=bash
 */

import { createHash, pbkdf2Sync, randomBytes } from "crypto";
import { ec as EC } from "elliptic";

const secp256k1 = new EC("secp256k1");

const DEFAULT_KDF_ITERATIONS = 100_000;
const DEFAULT_KDF_KEY_LENGTH = 32;
const DEFAULT_KDF_DIGEST = "sha256";
const DEFAULT_SALT_BYTES = 16;
const DEFAULT_NONCE_BYTES = 16;

export interface KeyPair {
  publicKey: string;
  privateKey: string;
}

export interface KdfOptions {
  iterations?: number;
  keyLength?: number;
  digest?: string;
  salt?: Buffer | string;
}

export interface DerivedKey {
  key: Buffer;
  salt: Buffer;
  iterations: number;
  keyLength: number;
  digest: string;
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

export function generateSalt(bytes = DEFAULT_SALT_BYTES): Buffer {
  if (!Number.isInteger(bytes) || bytes < DEFAULT_SALT_BYTES) {
    throw new Error(`Salt must be at least ${DEFAULT_SALT_BYTES} bytes`);
  }
  return randomBytes(bytes);
}

export function deriveKeyMaterial(password: string, options: KdfOptions = {}): DerivedKey {
  const iterations = options.iterations ?? DEFAULT_KDF_ITERATIONS;
  const keyLength = options.keyLength ?? DEFAULT_KDF_KEY_LENGTH;
  const digest = options.digest ?? DEFAULT_KDF_DIGEST;
  const salt = normalizeSalt(options.salt) ?? generateSalt();

  if (!Number.isInteger(iterations) || iterations <= 0) {
    throw new Error("KDF iterations must be a positive integer");
  }
  if (!Number.isInteger(keyLength) || keyLength <= 0) {
    throw new Error("KDF keyLength must be a positive integer");
  }

  return {
    key: pbkdf2Sync(password, salt, iterations, keyLength, digest),
    salt,
    iterations,
    keyLength,
    digest,
  };
}

export function deriveKey(
  password: string,
  iterationsOrOptions: number | KdfOptions = DEFAULT_KDF_ITERATIONS
): Buffer {
  const options = typeof iterationsOrOptions === "number"
    ? { iterations: iterationsOrOptions }
    : iterationsOrOptions;
  return deriveKeyMaterial(password, options).key;
}

export function generateNonce(bytes = DEFAULT_NONCE_BYTES): string {
  if (!Number.isInteger(bytes) || bytes < DEFAULT_NONCE_BYTES) {
    throw new Error(`Nonce must be at least ${DEFAULT_NONCE_BYTES} bytes`);
  }
  return randomBytes(bytes).toString("hex");
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
  const normalizedSignature = normalizeSignature(signature);
  if (!normalizedSignature) {
    return false;
  }

  const msgHash = keccak256(message);
  try {
    const key = secp256k1.keyFromPublic(publicKey, "hex");
    return key.verify(msgHash, normalizedSignature);
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

function normalizeSalt(salt?: Buffer | string): Buffer | undefined {
  if (salt === undefined) {
    return undefined;
  }

  const normalized = Buffer.isBuffer(salt)
    ? Buffer.from(salt)
    : Buffer.from(salt.startsWith("0x") ? salt.slice(2) : salt, "hex");
  if (normalized.length < DEFAULT_SALT_BYTES) {
    throw new Error(`Salt must be at least ${DEFAULT_SALT_BYTES} bytes`);
  }
  return normalized;
}

function normalizeSignature(signature: string): string | null {
  const normalized = signature.startsWith("0x") ? signature.slice(2) : signature;
  if (!/^[0-9a-fA-F]+$/.test(normalized) || normalized.length % 2 !== 0) {
    return null;
  }

  const byteLength = normalized.length / 2;
  const compactSignature = byteLength === 64 || byteLength === 65;
  const derSignature = byteLength >= 68 && byteLength <= 72;
  if (!compactSignature && !derSignature) {
    return null;
  }

  return normalized;
}
