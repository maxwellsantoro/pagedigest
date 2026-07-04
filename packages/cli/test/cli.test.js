import assert from "node:assert/strict";
import test from "node:test";

import { ASSETS, GENERATOR_VERSION, assetFor, sha256 } from "../src/cli.js";

test("maps supported platforms to pinned release assets", () => {
  const mac = assetFor("darwin", "arm64");
  assert.equal(mac.target, "aarch64-apple-darwin");
  assert.equal(mac.archiveName, `pagedigest-generator-v${GENERATOR_VERSION}-aarch64-apple-darwin.tar.gz`);
  assert.match(mac.url, /generator-v0\.1\.0/);
  assert.equal(mac.sha256.length, 64);

  assert.equal(assetFor("win32", "x64").extension, "zip");
  assert.equal(Object.keys(ASSETS).length, 4);
});

test("rejects unsupported platforms", () => {
  assert.throws(() => assetFor("linux", "arm64"), /does not provide/);
});

test("computes stable SHA-256 digests", () => {
  assert.equal(sha256(new TextEncoder().encode("pagedigest")), "21a50bfae35038f74c9a17a6ee63ad17d03396039c73fc050b2e0fc524f718c1");
});
