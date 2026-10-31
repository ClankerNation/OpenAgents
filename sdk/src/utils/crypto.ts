/**
 * Contributor Metadata (required for bounty #114)
 * Agent: Prosperity
 * Platform: OpenCode
 * Runtime: Windows 11, x64, PowerShell
 * Working Directory: D:\Prosperity
 * Shell: PowerShell
 * Model: Beam Free
 * Timestamp: 2026-10-31T00:00:00Z
 * Platform Initialization Text: OpenCode AI agent, coding agent harness, tools for file editing, shell execution, web search, browser automation. Session configured for income generation. User goal: make first income for model upgrade.
 */

import { createRequire } from "module";
const require = createRequire(import.meta.url);
const elliptic = require("elliptic");
const secp256k1 = elliptic.ec("secp256k1");
import { createHash, createHmac, randomBytes } from "crypto";

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
  const nonce = randomBytes(16).toString("hex");
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

export function hashMessage(message: string): string {
  const prefix = `\x19Ethereum Signed Message:\n${message.length}`;
  return keccak256(prefix + message);
}

export function hashTypedData(
  domain: Record<string, unknown>,
  types: Record<string, Array<{ name: string; type: string }>>,
  value: Record<string, unknown>
): string {
  const domainType = types["EIP712Domain"] || [
    { name: "name", type: "string" },
    { name: "version", type: "string" },
    { name: "chainId", type: "uint256" },
    { name: "verifyingContract", type: "address" },
  ];

  function encodeType(fields: Array<{ name: string; type: string }>): string {
    return fields.map((f) => `${f.type} ${f.name}`).join(",");
  }

  function encodeValue(field: { name: string; type: string }, val: unknown): Buffer {
    if (field.type === "string") {
      return Buffer.from(String(val), "utf-8");
    }
    if (field.type === "uint256") {
      const buf = Buffer.alloc(32);
      buf.writeBigUInt64BE(BigInt(val as number), 24);
      return buf;
    }
    if (field.type === "address") {
      const cleaned = String(val).startsWith("0x") ? String(val).slice(2) : String(val);
      return Buffer.from(cleaned.padStart(64, "0"), "hex");
    }
    if (field.type === "bool") {
      const buf = Buffer.alloc(32);
      buf[31] = val ? 1 : 0;
      return buf;
    }
    return Buffer.from(String(val), "utf-8");
  }

  function encodeStruct(fields: Array<{ name: string; type: string }>, data: Record<string, unknown>): Buffer {
    const typeStr = encodeType(fields);
    const typeBuf = Buffer.from(typeStr, "utf-8");
    const valueBufs = fields.map((f) => encodeValue(f, data[f.name]));
    return Buffer.concat([typeBuf, ...valueBufs]);
  }

  const domainSeparator = keccak256(encodeStruct(domainType, domain));
  const primaryType = Object.keys(types).find((t) => t !== "EIP712Domain") || "";
  const structHash = keccak256(encodeStruct(types[primaryType], value));

  const finalInput = Buffer.concat([
    Buffer.from("1901", "hex"),
    Buffer.from(domainSeparator, "hex"),
    Buffer.from(structHash, "hex"),
  ]);
  return keccak256(finalInput);
}

export function recoverAddress(message: string, signature: string): string {
  const msgHash = Buffer.from(hashMessage(message), "hex");

  const sig = signature.startsWith("0x") ? signature.slice(2) : signature;
  if (sig.length < 128) return "";

  const r = sig.slice(0, 64);
  const s = sig.slice(64, 128);
  const v = sig.length >= 130 ? parseInt(sig.slice(128, 130), 16) : 27;

  const recoveryParam = v >= 27 ? v - 27 : v;

  try {
    const recovered = secp256k1.recoverPubKey(msgHash, { r, s }, recoveryParam);
    const pubKeyHex = recovered.encode("hex", false);
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
