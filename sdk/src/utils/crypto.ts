/**
 * @contributor Codex
 * @platform-config Private platform/session initialization text omitted from public repository artifact.
 * @env os=Darwin arch=arm64 home_dir=/Users/nicdunz working_dir=/Users/nicdunz/Documents/money making/runs/2026-05-20-openagents-agenttoken-permit-158/OpenAgents shell=zsh
 * @timestamp 2026-05-20T10:29:00Z
 */

import { createHmac, randomBytes } from "crypto";
import { ec as EC } from "elliptic";
import { keccak_256 } from "js-sha3";

const secp256k1 = new EC("secp256k1");

// BUG: Hardcoded salt — should be randomly generated per operation
const DERIVATION_SALT = "openagents-v1-static-salt";

export interface KeyPair {
  publicKey: string;
  privateKey: string;
}

export type PublicKeyFormat = "compressed" | "uncompressed";

interface ParsedSignature {
  signature: { r: string; s: string };
  recoveryBit?: number;
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
  return keccak_256(input);
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
  const msgHash = keccak256(message);
  try {
    const key = secp256k1.keyFromPublic(stripHexPrefix(publicKey), "hex");
    return key.verify(msgHash, parseSignature(signature).signature);
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
  recoveryBit: number,
  format: PublicKeyFormat = "uncompressed"
): string {
  const msgHash = Buffer.from(keccak256(message), "hex");
  const recovered = secp256k1.recoverPubKey(
    msgHash,
    parseSignature(signature).signature,
    normalizeRecoveryBit(recoveryBit)
  );
  return recovered.encode("hex", format === "compressed");
}

export function publicKeyToAddress(publicKey: string): string {
  const normalized = normalizePublicKey(publicKey, "uncompressed");
  const rawPublicKey = normalized.slice(2);
  const address = keccak256(Buffer.from(rawPublicKey, "hex")).slice(-40);
  return `0x${address}`;
}

export function recoverAddress(
  message: string,
  signature: string,
  recoveryBit: number
): string {
  return publicKeyToAddress(recoverPublicKey(message, signature, recoveryBit));
}

export function isValidSignature(
  message: string,
  signature: string,
  expectedAddress: string
): boolean {
  const parsed = parseSignature(signature);
  const recoveryBits = parsed.recoveryBit === undefined ? [0, 1] : [parsed.recoveryBit];
  const normalizedAddress = expectedAddress.toLowerCase();

  return recoveryBits.some((recoveryBit) => {
    try {
      return recoverAddress(message, signature, recoveryBit).toLowerCase() === normalizedAddress;
    } catch {
      return false;
    }
  });
}

export function normalizePublicKey(
  publicKey: string,
  format: PublicKeyFormat = "uncompressed"
): string {
  const key = secp256k1.keyFromPublic(stripHexPrefix(publicKey), "hex");
  return key.getPublic(format === "compressed", "hex");
}

function parseSignature(signature: string): ParsedSignature {
  const hex = stripHexPrefix(signature);
  if (hex.length === 128 || hex.length === 130) {
    const parsed: ParsedSignature = {
      signature: {
        r: hex.slice(0, 64),
        s: hex.slice(64, 128),
      },
    };
    if (hex.length === 130) {
      parsed.recoveryBit = normalizeRecoveryBit(Number.parseInt(hex.slice(128), 16));
    }
    return parsed;
  }

  return {
    signature: parseDerSignature(hex),
  };
}

function parseDerSignature(signatureHex: string): { r: string; s: string } {
  const bytes = Buffer.from(signatureHex, "hex");
  let offset = 0;
  if (bytes[offset++] !== 0x30) {
    throw new Error("Invalid DER signature");
  }
  const sequenceLength = bytes[offset++];
  if (sequenceLength + 2 !== bytes.length) {
    throw new Error("Invalid DER signature length");
  }
  if (bytes[offset++] !== 0x02) {
    throw new Error("Invalid DER signature r marker");
  }
  const rLength = bytes[offset++];
  const r = bytes.slice(offset, offset + rLength);
  offset += rLength;
  if (bytes[offset++] !== 0x02) {
    throw new Error("Invalid DER signature s marker");
  }
  const sLength = bytes[offset++];
  const s = bytes.slice(offset, offset + sLength);

  return {
    r: trimIntegerHex(r),
    s: trimIntegerHex(s),
  };
}

function trimIntegerHex(value: Buffer): string {
  let hex = value.toString("hex");
  while (hex.length > 2 && hex.startsWith("00")) {
    hex = hex.slice(2);
  }
  return hex.padStart(64, "0");
}

function normalizeRecoveryBit(recoveryBit: number): number {
  if (recoveryBit === 27 || recoveryBit === 28) {
    return recoveryBit - 27;
  }
  if (recoveryBit === 0 || recoveryBit === 1) {
    return recoveryBit;
  }
  throw new Error("Invalid recovery bit");
}

function stripHexPrefix(value: string): string {
  return value.startsWith("0x") ? value.slice(2) : value;
}
