const assert = require("assert");
process.env.TS_NODE_COMPILER_OPTIONS = JSON.stringify({
  module: "commonjs",
  target: "es2020",
  moduleResolution: "node",
  ignoreDeprecations: "6.0",
});
require("ts-node/register/transpile-only");

const {
  deriveKey,
  generateKeyPair,
  generateNonce,
  signMessage,
  verifySignature,
} = require("../sdk/src/utils/crypto.ts");

describe("SDK crypto security", function () {
  it("generates CSPRNG hex nonces without Math.random", function () {
    const originalRandom = Math.random;
    Math.random = () => {
      throw new Error("Math.random must not be used");
    };

    try {
      const first = generateNonce();
      const second = generateNonce();

      assert.match(first, /^[0-9a-f]{32}$/);
      assert.match(second, /^[0-9a-f]{32}$/);
      assert.notEqual(first, second);
    } finally {
      Math.random = originalRandom;
    }
  });

  it("derives keys with unique salts by default", function () {
    const first = deriveKey("password");
    const second = deriveKey("password");

    assert.equal(first.key.length, 32);
    assert.equal(second.key.length, 32);
    assert.notDeepEqual(first.salt, second.salt);
    assert.notDeepEqual(first.key, second.key);
    assert.equal(first.iterations, 100000);
  });

  it("supports configurable KDF rounds and caller-supplied salts", function () {
    const salt = Buffer.from("a".repeat(32), "hex");
    const first = deriveKey("password", { iterations: 5, keyLength: 32, salt });
    const second = deriveKey("password", { iterations: 5, keyLength: 32, salt });

    assert.equal(first.iterations, 5);
    assert.deepEqual(first.salt, salt);
    assert.deepEqual(first.key, second.key);
  });

  it("rejects malformed signature lengths before verification", function () {
    const keyPair = generateKeyPair();
    const signature = signMessage(keyPair.privateKey, "hello");

    assert.equal(verifySignature(keyPair.publicKey, "hello", signature), true);
    assert.equal(verifySignature(keyPair.publicKey, "hello", "abcd"), false);
    assert.equal(verifySignature(keyPair.publicKey, "hello", "00".repeat(100)), false);
    assert.equal(verifySignature(keyPair.publicKey, "hello", "not-hex"), false);
  });
});
