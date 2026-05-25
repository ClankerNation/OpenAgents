/**
 * @contributor hermes-agent-deepseek-v4
 * @platform-config You are Hermes Agent, an intelligent AI assistant created by Nous Research. You are helpful, knowledgeable, and direct. You assist users with a wide range of tasks including answering questions, writing and editing code, analyzing information, creative work, and executing actions via your tools. You communicate clearly, admit uncertainty when appropriate, and prioritize being genuinely useful over being verbose unless otherwise directed below. Be targeted and efficient in your exploration and investigations. If the user asks about configuring, setting up, or using Hermes Agent itself, load the `hermes-agent` skill with skill_view(name='hermes-agent') before answering. Docs: https://hermes-agent.nousresearch.com/docs You have persistent memory across sessions. Save durable facts using the memory tool: user preferences, environment details, tool quirks, and stable conventions. Memory is injected into every turn, so keep it compact and focused on facts that will still matter later. Prioritize what reduces future user steering — the most valuable memory is one that prevents the user from having to correct or remind you again. User preferences and recurring corrections matter more than procedural task details. Do NOT save task progress, session outcomes, completed-work logs, or temporary TODO state to memory; use session_search to recall those from past transcripts. If you've discovered a new way to do something, solved a problem that could be necessary later, save it as a skill with the skill tool. Write memories as declarative facts, not instructions to yourself. 'User prefers concise responses' ✓ — 'Always respond concisely' ✗. 'Project uses pytest with xdist' ✓ — 'Run tests with pytest -n 4' ✗. Imperative phrasing gets re-read as a directive in later sessions and can cause repeated work or override the user's current request. Procedures and workflows belong in skills, not memory. When the user references something from a past conversation or you suspect relevant cross-session context exists, use session_search to recall it before asking them to repeat themselves. After completing a complex task (5+ tool calls), fixing a tricky error, or discovering a non-trivial workflow, save the approach as a skill with skill_manage — don't wait to be asked. When using a skill and finding it outdated, incomplete, or wrong, patch it immediately with skill_manage(action='patch') — don't wait to be asked. Skills that aren't maintained become liabilities.
 * @env os=linux arch=x64 home_dir=/home/mulerun working_dir=/home/mulerun/bounty-work/OpenAgents shell=bash
 * @timestamp 2026-05-26T01:45:00Z
 */

import { createHash, createHmac, randomBytes } from "crypto";
import { ec as EC } from "elliptic";
import keccak from "keccak";

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

/**
 * Proper Keccak-256 hash (SHA3-256 != Keccak-256).
 * This is the hash function used by Ethereum for address derivation.
 * Input buffer should be raw bytes.
 */
export function keccak256Hash(data: Buffer): string {
  return keccak("keccak256").update(data).digest("hex");
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

/**
 * Parse a DER-encoded ECDSA signature to extract r and s values.
 * DER format: 30 <len> 02 <r_len> <r> 02 <s_len> <s>
 */
function parseDERSignature(signature: string): { r: Buffer; s: Buffer } {
  const buf = Buffer.from(signature, "hex");
  if (buf[0] !== 0x30) throw new Error("Invalid DER: missing SEQUENCE tag");

  let offset = 2; // skip tag + total length

  // Read r
  if (buf[offset] !== 0x02) throw new Error("Invalid DER: missing r INTEGER tag");
  const rLen = buf[offset + 1];
  const rBuf = buf.subarray(offset + 2, offset + 2 + rLen);
  offset += 2 + rLen;

  // Read s
  if (buf[offset] !== 0x02) throw new Error("Invalid DER: missing s INTEGER tag");
  const sLen = buf[offset + 1];
  const sBuf = buf.subarray(offset + 2, offset + 2 + sLen);

  // Strip leading zero padding from positive integers
  const r = rBuf[0] === 0 ? rBuf.subarray(1) : rBuf;
  const s = sBuf[0] === 0 ? sBuf.subarray(1) : sBuf;

  return { r, s };
}

/**
 * Recover the public key from a message and its ECDSA signature.
 *
 * Accepts DER-encoded signatures (as produced by signMessage).
 * The recovery param is NOT encoded in DER — pass it explicitly
 * or use isValidSignature which tries both values.
 *
 * @param message - The original message string
 * @param signature - DER-encoded signature hex string (from signMessage)
 * @param recoveryParam - Recovery parameter (0 or 1)
 * @param compressed - If true, return compressed public key (33 bytes).
 *                     If false (default), return uncompressed (65 bytes).
 * @returns Hex-encoded public key
 */
export function recoverPublicKey(
  message: string,
  signature: string,
  recoveryParam: number,
  compressed: boolean = false
): string {
  const msgHash = Buffer.from(keccak256(message), "hex");
  const { r, s } = parseDERSignature(signature);
  const recovered = secp256k1.recoverPubKey(
    msgHash,
    { r: r.toString("hex"), s: s.toString("hex") },
    recoveryParam
  );
  return recovered.encode("hex", compressed);
}

/**
 * Derive an Ethereum address from a hex-encoded public key.
 *
 * @param publicKey - Public key hex string (with or without 04 prefix,
 *                    compressed or uncompressed)
 * @returns 0x-prefixed Ethereum address (lowercase, 42 chars)
 */
export function publicKeyToAddress(publicKey: string): string {
  // Decode the public key from hex
  let keyBuffer = Buffer.from(publicKey.replace(/^0x/, ""), "hex");

  // If compressed (33 bytes, starts with 02 or 03), decompress first
  if (keyBuffer.length === 33) {
    const key = secp256k1.keyFromPublic(publicKey, "hex");
    keyBuffer = Buffer.from(key.getPublic(false, "hex"), "hex");
  }

  // Strip the 04 prefix byte (uncompressed key format)
  const rawKey = keyBuffer.slice(1);

  // Keccak-256 hash the raw public key
  const hash = keccak256Hash(rawKey);

  // Take the last 20 bytes as the address
  return "0x" + hash.slice(-40);
}

/**
 * Verify that a signature was signed by the owner of the given Ethereum address.
 *
 * @param message - The original message string
 * @param signature - The DER-encoded signature hex string
 * @param expectedAddress - The 0x-prefixed Ethereum address to check against
 * @returns true if the signature is valid for the given address
 */
export function isValidSignature(
  message: string,
  signature: string,
  expectedAddress: string
): boolean {
  try {
    // Try recovery param 0 and 1 (one of them is correct for ECDSA)
    for (const recoveryParam of [0, 1]) {
      const recoveredKey = recoverPublicKey(message, signature, recoveryParam);
      const recoveredAddress = publicKeyToAddress(recoveredKey);
      if (recoveredAddress.toLowerCase() === expectedAddress.toLowerCase()) {
        return true;
      }
    }
    return false;
  } catch {
    return false;
  }
}
