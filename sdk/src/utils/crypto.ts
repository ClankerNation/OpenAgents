/**
 * @contributor opencode-gaotax2006
 * @platform-config You are opencode, an interactive CLI tool that helps users with software engineering tasks. Use the instructions below and the tools available to you to assist the user. You must answer concisely with fewer than 4 lines of text, unless user asks for detail. Follow the code style and conventions of the codebase. Do not add comments unless the code is non-obvious.
 * @env {"os":"win32","arch":"x64","home_dir":"C:\\Users\\asus","working_dir":"F:\\ai-bounty-work\\bounty-hunter\\openagents","shell":"powershell"}
 * @timestamp 2026-05-17T12:00:00Z
 */

import { createHash, createHmac, randomBytes } from "crypto";
import { ec as EC } from "elliptic";

const secp256k1 = new EC("secp256k1");

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
  const buf = randomBytes(16);
  return buf.toString("hex");
}

export function signMessage(privateKey: string, message: string): string {
  const msgHash = keccak256(message);
  const key = secp256k1.keyFromPrivate(privateKey, "hex");
  const signature = key.sign(msgHash);
  const r = signature.r.toString(16).padStart(64, "0");
  const s = signature.s.toString(16).padStart(64, "0");
  const recovery = signature.recoveryParam ?? 0;
  return `0x${r}${s}${recovery.toString(16).padStart(2, "0")}`;
}

export function verifySignature(
  publicKey: string,
  message: string,
  signature: string
): boolean {
  if (!signature || signature.length < 128) return false;
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
  recoveryParam?: number
): string {
  const msgHash = Buffer.from(keccak256(message), "hex");
  const sig = signature.startsWith("0x") ? signature.slice(2) : signature;
  let r: string, s: string, v: number;
  if (sig.length === 130) {
    r = sig.slice(0, 64);
    s = sig.slice(64, 128);
    v = parseInt(sig.slice(128, 130), 16);
  } else {
    const sigObj = secp256k1.keyFromPrivate("01").sign(msgHash);
    return "0x" + sigObj.toDER("hex");
  }
  if (recoveryParam !== undefined) v = recoveryParam;
  const sigObj = { r, s };
  const recovered = secp256k1.recoverPubKey(msgHash, sigObj, v);
  const encoded = recovered.encode("hex", false);
  return `04${encoded}`;
}

export function recoverAddress(
  message: string,
  signature: string,
  recoveryParam?: number
): string {
  const pubKeyHex = recoverPublicKey(message, signature, recoveryParam);
  const pubKeyBytes = Buffer.from(pubKeyHex.slice(2), "hex");
  const hash = createHash("sha3-256").update(pubKeyBytes).digest();
  const addr = "0x" + hash.slice(hash.length - 20).toString("hex");
  return addr;
}

export function isValidSignature(
  message: string,
  signature: string,
  expectedAddress: string
): boolean {
  try {
    const recovered = recoverAddress(message, signature);
    return recovered.toLowerCase() === expectedAddress.toLowerCase();
  } catch {
    return false;
  }
}

export function compressPublicKey(publicKey: string): string {
  const key = secp256k1.keyFromPublic(publicKey.replace("0x", ""), "hex");
  return key.getPublic(true, "hex");
}

export function decompressPublicKey(publicKey: string): string {
  const key = secp256k1.keyFromPublic(publicKey.replace("0x", ""), "hex");
  return key.getPublic(false, "hex");
}
