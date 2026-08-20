// @fix-author rafaio1
// @date 2026-08-20T00:00:00Z
// @runtime linux x64 /tmp/OpenAgents bash
// @platform-config Agentic bounty-hunter workflow
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
  const prefix = `\x19Ethereum Signed Message:\n${message.length}`;
  return keccak256(prefix + message);
}

export interface RecoveredKey {
  publicKey: string;
  compressed: string;
}

/**
 * Recover public key from ECDSA signature on secp256k1.
 * @param message - Original signed message (will be keccak256 hashed)
 * @param signature - DER or hex-encoded signature
 * @param recoveryBit - Recovery parameter (0 or 1)
 * @returns Object with both uncompressed and compressed public key formats
 */
export function recoverPublicKey(
  message: string,
  signature: string,
  recoveryBit: number
): RecoveredKey {
  if (recoveryBit !== 0 && recoveryBit !== 1) {
    throw new Error("Invalid recovery bit: must be 0 or 1");
  }

  const msgHash = Buffer.from(keccak256(message), "hex");
  
  // Parse signature - support both DER and raw r||s format
  let sigObj;
  try {
    if (signature.length === 128) {
      // Raw r||s format (64 bytes each)
      const r = signature.slice(0, 64);
      const s = signature.slice(64, 128);
      sigObj = { r, s };
    } else {
      // DER encoded
      sigObj = secp256k1.Signature.decode(Buffer.from(signature, "hex"));
    }
  } catch (e) {
    throw new Error(`Invalid signature format: ${(e as Error).message}`);
  }

  const recovered = secp256k1.recoverPubKey(msgHash, sigObj, recoveryBit);
  
  return {
    publicKey: recovered.encode("hex", false),   // Uncompressed (65 bytes)
    compressed: recovered.encodeCompressed("hex"), // Compressed (33 bytes)
  };
}
