const { expect } = require("chai");

require("ts-node").register({
  transpileOnly: true,
  compilerOptions: {
    module: "commonjs",
    moduleResolution: "node",
    target: "es2020",
  },
});

const {
  deriveKey,
  deriveKeyMaterial,
  generateNonce,
  signMessage,
  verifySignature,
} = require("../sdk/src/utils/crypto");

const PRIVATE_KEY =
  "0000000000000000000000000000000000000000000000000000000000000001";
const PUBLIC_KEY =
  "0479be667ef9dcbbac55a06295ce870b07029bfcdb2dce28d959f2815b16f81798" +
  "483ada7726a3c4655da4fbfc0e1108a8fd17b448a68554199c47d08ffb10d4b8";

describe("crypto utilities security hardening", function () {
  it("generates CSPRNG nonces with sufficient entropy", function () {
    const nonceA = generateNonce();
    const nonceB = generateNonce();

    expect(nonceA).to.match(/^[0-9a-f]{32}$/);
    expect(nonceB).to.match(/^[0-9a-f]{32}$/);
    expect(nonceA).not.to.equal(nonceB);
    expect(() => generateNonce(8)).to.throw("Nonce must be at least");
  });

  it("derives keys with unique salts and configurable rounds", function () {
    const first = deriveKeyMaterial("correct horse battery staple", {
      iterations: 5,
    });
    const second = deriveKeyMaterial("correct horse battery staple", {
      iterations: 5,
    });

    expect(first.salt.equals(second.salt)).to.equal(false);
    expect(first.key.equals(second.key)).to.equal(false);
    expect(first.iterations).to.equal(5);

    const repeated = deriveKey("correct horse battery staple", {
      iterations: 5,
      salt: first.salt,
    });
    expect(repeated.equals(first.key)).to.equal(true);
  });

  it("rejects malformed signature lengths before verification", function () {
    const message = "OpenAgents";
    const signature = signMessage(PRIVATE_KEY, message);

    expect(verifySignature(PUBLIC_KEY, message, signature)).to.equal(true);
    expect(verifySignature(PUBLIC_KEY, message, "abcd")).to.equal(false);
    expect(verifySignature(PUBLIC_KEY, message, signature + "00".repeat(20))).to.equal(false);
  });
});
