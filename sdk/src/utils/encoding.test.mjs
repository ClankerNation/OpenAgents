import { decodeParameter } from "./encoding.ts";
import { AbiCoder } from "ethers";

const coder = AbiCoder.defaultAbiCoder();
const complexType = "tuple(string,uint256[],uint256)";
const data = {
  name: "Antigravity",
  amounts: [100n, 200n],
  id: 42n
};

const encoded = coder.encode(
  [complexType],
  [["Antigravity", [100n, 200n], 42n]]
);

const decoded = decodeParameter(complexType, encoded);
console.log("Decoded:", decoded);

if (decoded[0] !== "Antigravity") throw new Error("String decode failed");
if (decoded[1][0] !== 100n || decoded[1][1] !== 200n) throw new Error("Array decode failed");
if (decoded[2] !== 42n) throw new Error("Uint decode failed");

console.log("All tests passed!");
