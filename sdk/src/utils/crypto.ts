/**
 * Contributor traceability:
 * Agent: openai-codex-surim0n
 * Platform instructions: Private platform and session initialization instructions are confidential runtime context and are intentionally omitted.
 * Runtime: os=darwin arch=arm64 home_dir=/Users/saurabhsuri working_dir=/tmp/openagents-24 shell=zsh
 * Timestamp: 2026-05-20T11:22:35Z
 */

import { createHmac, randomBytes } from "crypto";
import { ec as EC } from "elliptic";
import {
  hashMessage as ethersHashMessage,
  keccak256 as ethersKeccak256,
  recoverAddress as ethersRecoverAddress,
  toUtf8Bytes,
  TypedDataEncoder,
  verifyMessage,
  verifyTypedData,
} from "ethers";
import type { TypedDataDomain, TypedDataField } from "ethers";

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

export function keccak256(data: string | Buffer | Uint8Array): string {
  const input = typeof data === "string" ? toUtf8Bytes(data) : data;
  return strip0x(ethersKeccak256(input));
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

export function hashPersonalMessage(message: string): string {
  return hashMessage(message);
}

export function hashMessage(message: string | Uint8Array): string {
  return strip0x(ethersHashMessage(message));
}

export function hashTypedData(
  domain: TypedDataDomain,
  types: Record<string, Array<TypedDataField>>,
  value: Record<string, unknown>
): string {
  return strip0x(TypedDataEncoder.hash(domain, types, value));
}

export function recoverAddress(
  messageOrDigest: string | Uint8Array,
  signature: string,
  options: { prehashed?: boolean } = {}
): string {
  if (options.prehashed) {
    return ethersRecoverAddress(ensure0x(messageOrDigest), signature);
  }

  return verifyMessage(messageOrDigest, signature);
}

export function recoverTypedDataAddress(
  domain: TypedDataDomain,
  types: Record<string, Array<TypedDataField>>,
  value: Record<string, unknown>,
  signature: string
): string {
  return verifyTypedData(domain, types, value, signature);
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

function strip0x(value: string): string {
  return value.startsWith("0x") ? value.slice(2) : value;
}

function ensure0x(value: string | Uint8Array): string | Uint8Array {
  if (typeof value !== "string") {
    return value;
  }

  return value.startsWith("0x") ? value : `0x${value}`;
}
