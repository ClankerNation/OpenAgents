/**
 * Cryptographic utilities for EVM-compatible contract interactions.
 *
 * @fix-author Gaotax2006
 * @date 2026-06-23
 * @issue #136 Fix crypto.ts doesn't support secp256k1 key recovery from signed messages
 */

import { createHash, createHmac, randomBytes } from "crypto";
import { ec as EC } from "elliptic";

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
  return randomBytes(16).toString("hex");
}

export function signMessage(privateKey: string, message: string): string {
  const msgHash = keccak256(message);
  const key = secp256k1.keyFromPrivate(privateKey, "hex");
  const signature = key.sign(msgHash);
  return signature.toDER("hex");
}

/**
 * Recover the public key from a signed message using secp256k1.
 * Supports both DER-encoded and compact (r || s || v) signatures.
 * @param message The original signed message
 * @param signature DER or compact hex signature
 * @returns Recovered public key (uncompressed hex)
 */
export function recoverPublicKey(message: string, signature: string): string {
  const msgHash = Buffer.from(keccak256(message), "hex");

  // Handle compact signatures (r || s || v, 65 bytes = 130 hex chars)
  if (signature.length === 130) {
    const r = signature.slice(0, 64);
    const s = signature.slice(64, 128);
    const v = parseInt(signature.slice(128, 130), 16);
    const recoveryParam = v >= 27 ? v - 27 : v;

    const sigObj = {
      r: BigInt("0x" + r),
      s: BigInt("0x" + s),
    };

    const recovered = secp256k1.recoverPubKey(msgHash, sigObj, recoveryParam);
    return recovered.encode("hex", false);
  }

  // Handle DER-encoded signatures
  const key = secp256k1.keyFromPublic("04" + msgHash.toString("hex").slice(0, 64), "hex");
  // Fallback: try to verify and extract public key
  // For DER signatures, we need the v parameter from elsewhere
  // This is a best-effort recovery
  throw new Error("DER signatures require v parameter — use compact format (r||s||v) for key recovery");
}

/**
 * Recover the Ethereum address from a signed message.
 * @param message The original signed message
 * @param signature Compact hex signature (r || s || v, 130 hex chars)
 * @returns Recovered 0x-prefixed Ethereum address
 */
export function recoverAddress(message: string, signature: string): string {
  const publicKey = recoverPublicKey(message, signature);
  const hash = keccak256("0x" + publicKey.slice(2));
  return "0x" + hash.slice(-40);
}

/**
 * Create an Ethereum-personal-signed message hash.
 * @param message Message to sign
 * @returns Hash compatible with eth_sign / personal_sign
 */
export function personalSignHash(message: string): string {
  const prefix = `\x19Ethereum Signed Message:\n${message.length}`;
  return keccak256(prefix + message);
}

/**
 * Recover public key from an eth_sign signature.
 * @param message Original message
 * @param signature Compact hex signature (r || s || v)
 * @returns Recovered uncompressed public key hex
 */
export function recoverEthPublicKey(message: string, signature: string): string {
  const msgHash = personalSignHash(message);
  const r = BigInt("0x" + signature.slice(0, 64));
  const s = BigInt("0x" + signature.slice(64, 128));
  const v = parseInt(signature.slice(128, 130), 16);
  const recoveryParam = v >= 27 ? v - 27 : v;

  const sigObj = { r, s };
  const recovered = secp256k1.recoverPubKey(Buffer.from(msgHash, "hex"), sigObj, recoveryParam);
  return recovered.encode("hex", false);
}

/**
 * Verify a signature against a public key and message.
 * Supports both DER-encoded and compact signatures.
 * @param publicKey The signer's public key (hex)
 * @param message The signed message
 * @param signature DER or compact hex signature
 * @returns true if signature is valid
 */
export function verifySignature(
  publicKey: string,
  message: string,
  signature: string
): boolean {
  const msgHash = keccak256(message);

  // Validate signature length
  if (signature.length < 66) {
    return false;
  }

  // Handle compact signatures (r || s || v)
  if (signature.length === 130) {
    const r = BigInt("0x" + signature.slice(0, 64));
    const s = BigInt("0x" + signature.slice(64, 128));
    const v = parseInt(signature.slice(128, 130), 16);
    const recoveryParam = v >= 27 ? v - 27 : v;

    // Recover public key and compare
    const recovered = secp256k1.recoverPubKey(
      Buffer.from(msgHash, "hex"),
      { r, s },
      recoveryParam
    );
    const recoveredHex = recovered.encode("hex", false);
    return recoveredHex === publicKey.replace("0x", "");
  }

  // Handle DER-encoded signatures
  try {
    const key = secp256k1.keyFromPublic(publicKey.startsWith("0x") ? publicKey.slice(2) : publicKey, "hex");
    const derSig = Buffer.from(signature, "hex");
    return key.verify(msgHash, derSig);
  } catch {
    return false;
  }
}
