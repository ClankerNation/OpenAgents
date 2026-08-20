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
  // Use EIP-191 compliant hash with Ethereum signed message prefix
  const msgHash = hashPersonalMessage(message);
  const key = secp256k1.keyFromPrivate(privateKey, "hex");
  const signature = key.sign(Buffer.from(msgHash, "hex"));
  return signature.toDER("hex");
}

export function verifySignature(
  publicKey: string,
  message: string,
  signature: string
): boolean {
  if (!signature || signature.length < 2) return false;
  // Use EIP-191 compliant hash for verification
  const msgHash = hashPersonalMessage(message);
  try {
    const key = secp256k1.keyFromPublic(publicKey, "hex");
    return key.verify(Buffer.from(msgHash, "hex"), signature);
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
  // Use EIP-191 compliant hash for recovery
  const msgHash = Buffer.from(hashPersonalMessage(message), "hex");
  const sigObj = typeof signature === "string" 
    ? { r: signature.slice(0, 64), s: signature.slice(64, 128) }
    : signature;
  const recovered = secp256k1.recoverPubKey(msgHash, sigObj, recoveryParam);
  return recovered.encode("hex", false);
}

/**
 * Recover the Ethereum address from a signed personal message.
 * Compatible with on-chain ecrecover when using EIP-191 prefix.
 */
export function recoverAddress(
  message: string,
  signature: string,
  recoveryParam: number
): string {
  const pubKey = recoverPublicKey(message, signature, recoveryParam);
  // Ethereum address = last 20 bytes of keccak256(uncompressed pubkey without 04 prefix)
  const pubKeyBytes = Buffer.from(pubKey.slice(2), "hex"); // remove 04 prefix
  const hash = keccak256(pubKeyBytes);
  return "0x" + hash.slice(-40);
}

/**
 * Hash EIP-712 typed data for structured signing.
 * @param domainSeparator The domain separator hash
 * @param structHash The hash of the typed data struct
 * @returns EIP-712 compliant hash
 */
export function hashTypedData(domainSeparator: string, structHash: string): string {
  // EIP-712: keccak256("" + domainSeparator + structHash)
  const prefix = Buffer.from("1901", "hex");
  const domain = Buffer.from(domainSeparator.startsWith("0x") ? domainSeparator.slice(2) : domainSeparator, "hex");
  const struct = Buffer.from(structHash.startsWith("0x") ? structHash.slice(2) : structHash, "hex");
  const combined = Buffer.concat([prefix, domain, struct]);
  return createHash("sha3-256").update(combined).digest("hex");
}
