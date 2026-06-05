import { test } from "node:test";
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { existsSync, mkdtempSync, readdirSync, rmSync } from "node:fs";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { AbiCoder } from "ethers";

const testDir = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(testDir, "../../..");
const outDir = mkdtempSync(path.join(repoRoot, ".encoding-test-"));
const tscBin = path.join(repoRoot, "node_modules/typescript/bin/tsc");

execFileSync(
  process.execPath,
  [
    tscBin,
    "--pretty",
    "false",
    "--ignoreDeprecations",
    "6.0",
    "--target",
    "ES2020",
    "--module",
    "commonjs",
    "--moduleResolution",
    "node",
    "--esModuleInterop",
    "--skipLibCheck",
    "--types",
    "node",
    "--outDir",
    outDir,
    path.join(repoRoot, "sdk/src/utils/encoding.ts"),
  ],
  { cwd: repoRoot, stdio: "inherit" }
);

process.on("exit", () => {
  rmSync(outDir, { recursive: true, force: true });
});

function findCompiledEncoding(dir) {
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const fullPath = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      const nested = findCompiledEncoding(fullPath);
      if (nested) return nested;
    }
    if (entry.name === "encoding.js") {
      return fullPath;
    }
  }
  return null;
}

const compiledEncoding = findCompiledEncoding(outDir);
assert.ok(compiledEncoding && existsSync(compiledEncoding), "compiled encoding.js was emitted");

const encoding = await import(pathToFileURL(compiledEncoding).href);
const coder = AbiCoder.defaultAbiCoder();

test("decodeParameter keeps static slot backwards compatibility", () => {
  assert.equal(encoding.decodeParameter("uint256", "2a"), 42n);
  assert.equal(encoding.decodeParameter("bool", "01"), true);

  const address = "0x1111111111111111111111111111111111111111";
  const addressSlot = coder.encode(["address"], [address]).slice(2);
  assert.equal(encoding.decodeParameter("address", addressSlot), address);
});

test("decodeParameter decodes string and bytes dynamic ABI values", () => {
  assert.equal(
    encoding.decodeParameter("string", coder.encode(["string"], ["hello agent"])),
    "hello agent"
  );

  const decodedBytes = encoding.decodeParameter("bytes", coder.encode(["bytes"], ["0x1234abcd"]));
  assert.equal(Buffer.isBuffer(decodedBytes), true);
  assert.equal(decodedBytes.toString("hex"), "1234abcd");
});

test("decodeParameter decodes dynamic arrays with static and dynamic elements", () => {
  assert.deepEqual(
    encoding.decodeParameter("uint256[]", coder.encode(["uint256[]"], [[1n, 2n, 3n]])),
    [1n, 2n, 3n]
  );

  assert.deepEqual(
    encoding.decodeParameter("string[]", coder.encode(["string[]"], [["alpha", "beta"]])),
    ["alpha", "beta"]
  );
});

test("decodeParams decodes required complex return type with string array and uint", () => {
  const encoded = coder.encode(
    ["string", "uint256[]", "uint256"],
    ["task-ready", [5n, 8n, 13n], 21n]
  );

  assert.deepEqual(encoding.decodeParams(["string", "uint256[]", "uint256"], encoded), [
    "task-ready",
    [5n, 8n, 13n],
    21n,
  ]);
});

test("decodeParameter supports byte offsets for dynamic values in mixed return data", () => {
  const encoded = coder.encode(["uint256", "string"], [10n, "offset string"]);

  assert.equal(encoding.decodeParameter("uint256", encoded, 0), 10n);
  assert.equal(encoding.decodeParameter("string", encoded, 32), "offset string");
});

test("decodeParameter decodes nested tuple syntax recursively", () => {
  const tupleType = "tuple(string,uint256[],tuple(bytes,bool))";
  const encoded = coder.encode([tupleType], [["agent", [7n, 8n], ["0xdeadbeef", true]]]);
  const decoded = encoding.decodeParameter(tupleType, encoded);

  assert.equal(decoded[0], "agent");
  assert.deepEqual(decoded[1], [7n, 8n]);
  assert.equal(Buffer.isBuffer(decoded[2][0]), true);
  assert.equal(decoded[2][0].toString("hex"), "deadbeef");
  assert.equal(decoded[2][1], true);
});

test("decodeParameter decodes named tuple descriptors recursively", () => {
  const descriptor = {
    type: "tuple",
    components: [
      { name: "label", type: "string" },
      { name: "scores", type: "uint256[]" },
      {
        name: "meta",
        type: "tuple",
        components: [
          { name: "payload", type: "bytes" },
          { name: "ok", type: "bool" },
        ],
      },
    ],
  };
  const encoded = coder.encode(
    ["tuple(string,uint256[],tuple(bytes,bool))"],
    [["agent", [7n, 8n], ["0xdeadbeef", true]]]
  );
  const decoded = encoding.decodeParameter(descriptor, encoded);

  assert.equal(decoded.label, "agent");
  assert.deepEqual(decoded.scores, [7n, 8n]);
  assert.equal(Buffer.isBuffer(decoded.meta.payload), true);
  assert.equal(decoded.meta.payload.toString("hex"), "deadbeef");
  assert.equal(decoded.meta.ok, true);
});
