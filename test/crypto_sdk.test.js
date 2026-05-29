const { expect } = require("chai");
const { ethers } = require("ethers");
const {
  generateKeyPair,
  signMessage,
  verifySignature,
  recoverPublicKey,
  compressPublicKey,
  decompressPublicKey,
  publicKeyToAddress,
  isValidSignature,
} = require("../sdk/src/utils/crypto");

describe("Cryptography SDK Utilities", () => {
  it("should generate a valid key pair", () => {
    const keyPair = generateKeyPair();
    expect(keyPair.publicKey).to.be.a("string");
    expect(keyPair.privateKey).to.be.a("string");
    expect(keyPair.publicKey.length).to.equal(130); // Uncompressed hex public key is 65 bytes (130 hex characters)
  });

  it("should sign a message and verify it", () => {
    const keyPair = generateKeyPair();
    const message = "Hello OpenAgents!";
    const signature = signMessage(keyPair.privateKey, message);
    expect(signature).to.be.a("string");

    const isValid = verifySignature(keyPair.publicKey, message, signature);
    expect(isValid).to.be.true;
  });

  it("should recover public key and support compressed/uncompressed formats", () => {
    const keyPair = generateKeyPair();
    const message = "Hello OpenAgents!";
    
    const crypto = require("../sdk/src/utils/crypto");
    const hash = crypto.keccak256(message);
    
    const elliptic = require("elliptic");
    const ec = new elliptic.ec("secp256k1");
    const key = ec.keyFromPrivate(keyPair.privateKey, "hex");
    const signatureObj = key.sign(hash);
    const recoveryBit = signatureObj.recoveryParam;
    const derSig = signatureObj.toDER("hex");

    // Recover uncompressed
    const recoveredUncompressed = recoverPublicKey(message, derSig, recoveryBit, false);
    expect(recoveredUncompressed).to.equal(keyPair.publicKey);

    // Recover compressed
    const recoveredCompressed = recoverPublicKey(message, derSig, recoveryBit, true);
    const expectedCompressed = compressPublicKey(keyPair.publicKey);
    expect(recoveredCompressed).to.equal(expectedCompressed);
  });

  it("should compress and decompress public keys correctly", () => {
    const keyPair = generateKeyPair();
    const compressed = compressPublicKey(keyPair.publicKey);
    expect(compressed.length).to.equal(66); // Compressed hex public key is 33 bytes (66 hex characters)
    expect(compressed.startsWith("02") || compressed.startsWith("03")).to.be.true;

    const decompressed = decompressPublicKey(compressed);
    expect(decompressed).to.equal(keyPair.publicKey);
  });

  it("should derive Ethereum address matching on-chain behavior", () => {
    const wallet = ethers.Wallet.createRandom();
    const uncompressedPubKey = wallet.signingKey.publicKey.substring(2); // strip 0x prefix
    const derivedAddress = publicKeyToAddress(uncompressedPubKey);
    expect(derivedAddress.toLowerCase()).to.equal(wallet.address.toLowerCase());
  });

  it("should validate signatures using isValidSignature convenience helper", () => {
    const message = "Sign this message to log in";
    const keyPair = generateKeyPair();
    const elliptic = require("elliptic");
    const ec = new elliptic.ec("secp256k1");
    const key = ec.keyFromPrivate(keyPair.privateKey, "hex");
    const crypto = require("../sdk/src/utils/crypto");
    const hash = crypto.keccak256(message);
    const signatureObj = key.sign(hash);
    const recoveryBit = signatureObj.recoveryParam;
    
    // Create flat 65-byte signature (r, s, v)
    const r = signatureObj.r.toString("hex", 64);
    const s = signatureObj.s.toString("hex", 64);
    const v = (27 + recoveryBit).toString(16);
    const flatSig = "0x" + r + s + v;

    const address = publicKeyToAddress(keyPair.publicKey);
    const isValid = isValidSignature(message, flatSig, address);
    expect(isValid).to.be.true;
  });
});
