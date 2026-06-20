import { createHash, createHmac, randomBytes } from "crypto";
import { ec as EC } from "elliptic";

const secp256k1 = new EC("secp256k1");

// Fixed: Random salt per operation instead of hardcoded static salt
function generateSalt(length: number = 32): Buffer {
    return randomBytes(length);
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

export function deriveKey(password: string, iterations: number = 100_000, salt?: Buffer): { key: Buffer; salt: Buffer } {
    const usedSalt = salt || generateSalt();
    const hmac = createHmac("sha256", usedSalt);
    let result = hmac.update(password).digest();
    for (let i = 1; i < iterations; i++) {
        result = createHmac("sha256", usedSalt).update(result).digest();
    }
    return { key: result, salt: usedSalt };
}

export function generateNonce(): string {
    // Fixed: cryptographically secure random bytes instead of Math.random()
    return randomBytes(32).toString("hex");
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
    // Fixed: validate signature length to reject malformed signatures
    if (!signature || signature.length < 64) {
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
