/**
 * @contributor Antigravity
 * @platform-config
 * You are Antigravity, a powerful agentic AI coding assistant designed by the Google DeepMind team working on Advanced Agentic Coding.
 * You are pair programming with a USER to solve their coding task. The task may require creating a new codebase, modifying or debugging an existing codebase, or simply answering a question.
 * The USER will send you requests, which you must always prioritize addressing. User requests are enclosed within <USER_REQUEST> tags. Along with each USER request, we will attach additional metadata about their current state, such as what files they have open and where their cursor is.
 * This information may or may not be relevant to the coding task, it is up for you to decide.
 * @env os: macOS, arch: arm64, home_dir: /Users/macminim1, working_dir: /Users/macminim1/Documents/efe/bounty-hunter/temp/OpenAgents, shell: /bin/zsh
 * @timestamp 2026-05-29T11:15:00Z
 */

import { createHash, createHmac, randomBytes } from "crypto";
import { ec as EC } from "elliptic";
import { computeAddress } from "ethers";

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

export function recoverPublicKey(
  message: string,
  signature: string,
  recoveryParam: number,
  compressed = false
): string {
  const msgHash = Buffer.from(keccak256(message), "hex");
  
  // Strip optional 0x prefix
  const cleanSig = signature.startsWith("0x") ? signature.substring(2) : signature;

  let sigObj;
  if (cleanSig.length === 128) {
    // 64-byte flat signature (r, s)
    sigObj = {
      r: cleanSig.substring(0, 64),
      s: cleanSig.substring(64, 128)
    };
  } else if (cleanSig.length === 130) {
    // 65-byte flat signature (r, s, v)
    sigObj = {
      r: cleanSig.substring(0, 64),
      s: cleanSig.substring(64, 128)
    };
  } else {
    // Assume DER format
    sigObj = Buffer.from(cleanSig, "hex");
  }

  const recovered = secp256k1.recoverPubKey(msgHash, sigObj, recoveryParam);
  return recovered.encode("hex", compressed);
}

export function compressPublicKey(publicKey: string): string {
  const cleanKey = publicKey.startsWith("0x") ? publicKey.substring(2) : publicKey;
  const key = secp256k1.keyFromPublic(cleanKey, "hex");
  return key.getPublic().encode("hex", true);
}

export function decompressPublicKey(publicKey: string): string {
  const cleanKey = publicKey.startsWith("0x") ? publicKey.substring(2) : publicKey;
  const key = secp256k1.keyFromPublic(cleanKey, "hex");
  return key.getPublic().encode("hex", false);
}

export function publicKeyToAddress(publicKey: string): string {
  const cleanKey = publicKey.startsWith("0x") ? publicKey : "0x" + publicKey;
  return computeAddress(cleanKey);
}

export function isValidSignature(
  message: string,
  signature: string,
  expectedAddress: string
): boolean {
  const cleanSig = signature.startsWith("0x") ? signature.substring(2) : signature;
  const expectedAddrLower = expectedAddress.toLowerCase();

  // If signature has 65 bytes (r, s, v), try to extract recovery bit
  if (cleanSig.length === 130) {
    const vHex = cleanSig.substring(128, 130);
    const v = parseInt(vHex, 16);
    const recoveryBit = v >= 27 ? v - 27 : v;
    if (recoveryBit === 0 || recoveryBit === 1) {
      try {
        const pubKey = recoverPublicKey(message, signature, recoveryBit);
        const addr = publicKeyToAddress(pubKey);
        if (addr.toLowerCase() === expectedAddrLower) {
          return true;
        }
      } catch {}
    }
  }

  // Fallback to trying both recovery bits
  for (const recoveryBit of [0, 1]) {
    try {
      const pubKey = recoverPublicKey(message, signature, recoveryBit);
      const addr = publicKeyToAddress(pubKey);
      if (addr.toLowerCase() === expectedAddrLower) {
        return true;
      }
    } catch {}
  }

  return false;
}

