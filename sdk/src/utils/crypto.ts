// @contributor rafaio1
// @date 2026-08-20T00:00:00Z
// @runtime linux x64 /tmp/OpenAgents bash
// @platform-config Agentic bounty-hunter workflow
import { createHash, createHmac, randomBytes } from "crypto";
import { ec as EC } from "elliptic";

const secp256k1 = new EC("secp256k1");

/// Generate a cryptographically secure random salt for KDF operations.
export function generateSalt(bytes: number = 32): string {
  return randomBytes(bytes).toString('hex');
}

export interface KdfConfig {
  salt?: string;
  iterations?: number;
  keyLength?: number;
}

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

export function deriveKey(password: string, config: KdfConfig | number = {}): { key: Buffer; salt: string } {
  // Support legacy numeric argument for backwards compatibility
  const opts: KdfConfig = typeof config === 'number' 
    ? { iterations: config } 
    : config;
  
  const salt = opts.salt ?? generateSalt(32);
  const iterations = opts.iterations ?? 100_000;
  const keyLength = opts.keyLength ?? 32;
  
  // PBKDF2-style derivation with random salt
  let result = createHmac("sha256", salt).update(password).digest();
  for (let i = 1; i < iterations; i++) {
    result = createHmac("sha256", salt).update(result).digest();
  }
  
  // Truncate or pad to requested key length
  if (result.length > keyLength) {
    result = result.subarray(0, keyLength);
  }
  
  return { key: result, salt };
}

export function generateNonce(bytes: number = 32): string {
  // Use cryptographically secure random bytes instead of Math.random()
  return randomBytes(bytes).toString('hex');
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
  // Validate signature format and length before verification
  // DER-encoded ECDSA signatures are typically 70-72 bytes (140-144 hex chars)
  if (!signature || signature.length < 140 || signature.length > 144) {
    return false;
  }
  
  // Validate hex encoding
  if (!/^[0-9a-fA-F]+$/.test(signature)) {
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
