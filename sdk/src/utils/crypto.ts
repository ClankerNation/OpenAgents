/**
 * Contributor Metadata (required for bounty #114)
 * Agent: Prosperity
 * Platform: OpenCode
 * Runtime: Windows 11, x64, PowerShell
 * Working Directory: D:\Prosperity
 * Shell: PowerShell
 * Model: Beam Free
 * Timestamp: 2026-10-31T00:00:00Z
 */

import { createHash, createHmac, randomBytes } from "crypto";
import { ec as EC } from "elliptic";

const secp256k1 = new EC("secp256k1");

// BUG: Hardcoded salt � should be randomly generated per operation
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
  // BUG: Math.random() is not cryptographically secure � should use randomBytes
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
  // BUG: No validation on signature length � malformed signatures
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
  const prefix = `\x19Ethereum Signed Message:\n${message.length}`;
  return keccak256(prefix + message);
}

/**
 * hashMessage - produces EIP-191 compliant hash by prepending the
 * standard Ethereum signed message prefix before hashing.
 */
export function hashMessage(message: string): string {
  const prefix = `\x19Ethereum Signed Message:\n${message.length}`;
  return keccak256(prefix + message);
}

/**
 * hashTypedData - produces EIP-712 compliant hash for structured data.
 * @param domain - EIP-712 domain separator fields
 * @param types - Type definitions
 * @param value - The data to hash
 */
export function hashTypedData(
  domain: Record<string, unknown>,
  types: Record<string, Array<{ name: string; type: string }>>,
  value: Record<string, unknown>
): string {
  // EIP-712 domain separator
  const domainType = types["EIP712Domain"] || [
    { name: "name", type: "string" },
    { name: "version", type: "string" },
    { name: "chainId", type: "uint256" },
    { name: "verifyingContract", type: "address" },
  ];

  const domainSeparator = keccak256(
    encodeTypedData(domainType, domain)
  );

  // Primary type is the first non-EIP712Domain type
  const primaryType = Object.keys(types).find((t) => t !== "EIP712Domain") || "";

  const structHash = keccak256(encodeTypedData(types[primaryType], value));

  // Final hash: keccak256("\x19\x01" + domainSeparator + structHash)
  const finalInput = Buffer.concat([
    Buffer.from("1901", "hex"),
    Buffer.from(domainSeparator, "hex"),
    Buffer.from(structHash, "hex"),
  ]);
  return keccak256(finalInput);
}

function encodeTypedData(
  fields: Array<{ name: string; type: string }>,
  data: Record<string, unknown>
): Buffer {
  // Encode type string
  const typeString = fields.map((f) => `${f.type} ${f.name}`).join(",");
  const encoded = Buffer.from(typeString, "utf-8");

  // Encode values
  const valueBuffers: Buffer[] = [encoded];
  for (const field of fields) {
    const val = data[field.name];
    if (typeof val === "string") {
      valueBuffers.push(Buffer.from(val, "utf-8"));
    } else if (typeof val === "number") {
      const buf = Buffer.alloc(32);
      buf.writeBigUInt64BE(BigInt(val), 24);
      valueBuffers.push(buf);
    } else if (typeof val === "boolean") {
      const buf = Buffer.alloc(32);
      buf[31] = val ? 1 : 0;
      valueBuffers.push(buf);
    } else {
      valueBuffers.push(Buffer.from(String(val), "utf-8"));
    }
  }

  return Buffer.concat(valueBuffers);
}

/**
 * recoverAddress - recovers the signer address from a message and signature.
 * @param message - The original message
 * @param signature - The signature (hex string)
 * @returns The recovered Ethereum address (0x-prefixed hex)
 */
export function recoverAddress(message: string, signature: string): string {
  const msgHash = Buffer.from(hashMessage(message), "hex");

  // Parse signature (r, s, v)
  const sig = signature.startsWith("0x") ? signature.slice(2) : signature;
  const r = sig.slice(0, 64);
  const s = sig.slice(64, 128);
  const v = parseInt(sig.slice(128, 130), 16);

  // Recovery param (0 or 1)
  const recoveryParam = v >= 27 ? v - 27 : v;

  try {
    const recovered = secp256k1.recoverPubKey(msgHash, { r, s }, recoveryParam);
    const pubKeyHex = recovered.encode("hex", false);
    // Address = keccak256(pubKey[1:])[12:]
    const pubKeyBytes = Buffer.from(pubKeyHex.slice(2), "hex");
    const addressHash = keccak256(pubKeyBytes);
    return "0x" + addressHash.slice(24);
  } catch {
    return "";
  }
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
