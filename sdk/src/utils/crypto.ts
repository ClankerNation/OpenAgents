/**
 * @contributor rafaio1
 * @timestamp 2026-08-20T01:45:00Z
 * @env os=linux, arch=x64, home_dir=/root, working_dir=/tmp/OpenAgents, shell=bash
 * @platform-config [OMITTED FOR SECURITY - SYSTEM PROMPT NOT DISCLOSED PER ARO CONSTITUTION]
 */

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

export function deriveKey(password: string, salt?: Buffer, iterations = 100_000): Buffer {
  const s = salt || randomBytes(32);
  let result = createHmac("sha256", s).update(password).digest();
  for (let i = 1; i < iterations; i++) {
    result = createHmac("sha256", s).update(result).digest();
  }
  return result;
}

export function generateNonce(): string {
  return randomBytes(16).toString("hex");
}

export function signMessage(privateKey: string, message: string): string {
  const msgHash = hashPersonalMessage(message);
  const key = secp256k1.keyFromPrivate(privateKey, "hex");
  const signature = key.sign(Buffer.from(msgHash, "hex"));
  // Return hex signature with recovery param appended
  const r = signature.r.toString("hex").padStart(64, "0");
  const s = signature.s.toString("hex").padStart(64, "0");
  const v = (signature.recoveryParam + 27).toString(16).padStart(2, "0");
  return r + s + v;
}

export function verifySignature(
  publicKey: string,
  message: string,
  signature: string
): boolean {
  const msgHash = hashPersonalMessage(message);
  try {
    // Strip recovery param if present (last byte)
    const sigHex = signature.length === 132 ? signature.slice(0, 130) : signature;
    const key = secp256k1.keyFromPublic(publicKey, "hex");
    return key.verify(Buffer.from(msgHash, "hex"), sigHex);
  } catch {
    return false;
  }
}

export function hashPersonalMessage(message: string): string {
  const prefix = `\x19Ethereum Signed Message:\n${message.length}`;
  return keccak256(prefix + message);
}

/**
 * Recover public key from signature and message.
 * @param message Original signed message
 * @param signature Hex signature (65 bytes: r[32] + s[32] + v[1])
 * @returns Uncompressed public key hex string
 */
export function recoverPublicKey(message: string, signature: string): string {
  const msgHash = Buffer.from(hashPersonalMessage(message), "hex");
  
  // Parse signature components
  const r = signature.slice(0, 64);
  const s = signature.slice(64, 128);
  const v = parseInt(signature.slice(128, 130), 16);
  const recoveryParam = v >= 27 ? v - 27 : v;
  
  const recovered = secp256k1.recoverPubKey(
    msgHash,
    { r, s },
    recoveryParam
  );
  
  return recovered.encode("hex", false);
}

/**
 * Recover compressed public key from signature.
 */
export function recoverCompressedPublicKey(message: string, signature: string): string {
  const msgHash = Buffer.from(hashPersonalMessage(message), "hex");
  
  const r = signature.slice(0, 64);
  const s = signature.slice(64, 128);
  const v = parseInt(signature.slice(128, 130), 16);
  const recoveryParam = v >= 27 ? v - 27 : v;
  
  const recovered = secp256k1.recoverPubKey(
    msgHash,
    { r, s },
    recoveryParam
  );
  
  return recovered.encode("hex", true);
}

/**
 * Derive Ethereum address from public key.
 */
export function publicKeyToAddress(publicKey: string): string {
  // Remove 04 prefix if uncompressed
  const pub = publicKey.startsWith("04") ? publicKey.slice(2) : publicKey;
  const hash = keccak256(Buffer.from(pub, "hex"));
  return "0x" + hash.slice(-40);
}

/**
 * Validate that a signature was created by the expected address.
 */
export function isValidSignature(
  message: string,
  signature: string,
  expectedAddress: string
): boolean {
  try {
    const recovered = recoverPublicKey(message, signature);
    const address = publicKeyToAddress(recovered);
    return address.toLowerCase() === expectedAddress.toLowerCase();
  } catch {
    return false;
  }
}
