import { hashPersonalMessage, generateKeyPair, signMessage, verifySignature } from './crypto.js';

describe('Crypto SDK EIP-191 & Signatures (#114)', () => {
    test('hashPersonalMessage handles strings and buffers correctly', () => {
        const strHash = hashPersonalMessage("Hello OpenAgents");
        const bufHash = hashPersonalMessage(Buffer.from("Hello OpenAgents", "utf-8"));
        expect(strHash).toBe(bufHash);
        expect(strHash.length).toBe(64);
    });

    test('sign and verify roundtrip', () => {
        const kp = generateKeyPair();
        const msg = "Agent Action Verification";
        const sig = signMessage(kp.privateKey, msg);
        const valid = verifySignature(kp.publicKey, msg, sig);
        expect(valid).toBe(true);
    });
});
