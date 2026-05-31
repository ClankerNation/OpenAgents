import { createHash, pbkdf2Sync, randomBytes } from "crypto";
import { ec as EC } from "elliptic";

/**
 * @generated-by Codex Agent xyjk0511
 * @platform Safety-preserving Codex execution context; private system and developer instructions are not embedded in source.
 * @runtime Microsoft Windows 10.0.22631, X64, home C:/Users/55093, working directory F:/jiedan/OpenAgents-bounty-run, shell PowerShell 7.6.2
 * @timestamp 2026-05-31T00:00:00-07:00
 */

const secp256k1 = new EC("secp256k1");

const DEFAULT_KDF_ITERATIONS = 100_000;
const DEFAULT_KDF_KEY_LENGTH = 32;
const DEFAULT_KDF_DIGEST = "sha256";
const DER_SEQUENCE_TAG = 0x30;
const DER_INTEGER_TAG = 0x02;

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

export function deriveKey(password: string, options: KdfOptions | number = {}): DerivedKey {
  const normalized = typeof options === "number" ? { iterations: options } : options;
  const iterations = normalized.iterations ?? DEFAULT_KDF_ITERATIONS;
  if (!Number.isInteger(iterations) || iterations < 1) {
    throw new Error("KDF iterations must be a positive integer");
  }

  const keyLength = normalized.keyLength ?? DEFAULT_KDF_KEY_LENGTH;
  if (!Number.isInteger(keyLength) || keyLength < 16) {
    throw new Error("KDF keyLength must be at least 16 bytes");
  }

  const digest = normalized.digest ?? DEFAULT_KDF_DIGEST;
  const salt = normalizeSalt(normalized.salt);

  return {
    key: pbkdf2Sync(password, salt, iterations, keyLength, digest),
    salt,
    iterations,
    digest,
  };
}

export function generateNonce(): string {
  return randomBytes(16).toString("hex");
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
  if (!isValidDERSignature(signature)) {
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

function normalizeSalt(salt?: Buffer | string): Buffer {
  if (!salt) {
    return randomBytes(16);
  }
  const value = Buffer.isBuffer(salt) ? Buffer.from(salt) : Buffer.from(salt, "hex");
  if (value.length < 16) {
    throw new Error("KDF salt must be at least 16 bytes");
  }
  return value;
}

function isValidDERSignature(signature: string): boolean {
  if (!/^[0-9a-fA-F]+$/.test(signature) || signature.length % 2 !== 0) {
    return false;
  }

  const bytes = Buffer.from(signature, "hex");
  if (bytes.length < 8 || bytes.length > 72) {
    return false;
  }
  if (bytes[0] !== DER_SEQUENCE_TAG || bytes[1] !== bytes.length - 2) {
    return false;
  }

  const rTagIndex = 2;
  if (bytes[rTagIndex] !== DER_INTEGER_TAG) {
    return false;
  }
  const rLength = bytes[rTagIndex + 1];
  const sTagIndex = rTagIndex + 2 + rLength;
  if (sTagIndex + 2 > bytes.length || bytes[sTagIndex] !== DER_INTEGER_TAG) {
    return false;
  }
  const sLength = bytes[sTagIndex + 1];
  return rLength > 0 && sLength > 0 && sTagIndex + 2 + sLength === bytes.length;
}
