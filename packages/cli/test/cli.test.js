import assert from "node:assert/strict";
import { mkdtemp, readFile, rm, stat, writeFile, mkdir } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";
import test from "node:test";

import {
  ASSETS,
  GENERATOR_VERSION,
  MAX_ARCHIVE_BYTES,
  assetFor,
  download,
  installBinary,
  sha256,
} from "../src/cli.js";

test("maps supported platforms to pinned release assets", () => {
  const mac = assetFor("darwin", "arm64");
  assert.equal(mac.target, "aarch64-apple-darwin");
  assert.equal(mac.archiveName, `pagedigest-generator-v${GENERATOR_VERSION}-aarch64-apple-darwin.tar.gz`);
  assert.match(mac.url, /generator-v0\.2\.0/);
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

function mockResponse({ status = 200, statusText = "OK", body, headers = {} }) {
  const bytes = body instanceof Uint8Array ? body : new TextEncoder().encode(body);
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText,
    headers: {
      get(name) {
        const key = name.toLowerCase();
        const map = Object.fromEntries(
          Object.entries(headers).map(([k, v]) => [k.toLowerCase(), v]),
        );
        if (key === "content-length" && map[key] === undefined) {
          return String(bytes.byteLength);
        }
        return map[key] ?? null;
      },
    },
    async arrayBuffer() {
      return bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength);
    },
  };
}

test("download rejects HTTP failures", async () => {
  const asset = { ...assetFor("linux", "x64"), sha256: "00".repeat(32), url: "https://example.test/x" };
  await assert.rejects(
    () =>
      download(asset, {
        fetchImpl: async () => mockResponse({ status: 404, statusText: "Not Found", body: "missing" }),
      }),
    /failed to download generator \(404/,
  );
});

test("download rejects content-length over the size limit", async () => {
  const asset = { ...assetFor("linux", "x64"), sha256: "00".repeat(32), url: "https://example.test/x" };
  await assert.rejects(
    () =>
      download(asset, {
        maxBytes: 8,
        fetchImpl: async () =>
          mockResponse({
            body: "tiny",
            headers: { "content-length": "999" },
          }),
      }),
    /exceeds the download size limit/,
  );
});

test("download rejects body larger than the size limit", async () => {
  const asset = { ...assetFor("linux", "x64"), sha256: "00".repeat(32), url: "https://example.test/x" };
  await assert.rejects(
    () =>
      download(asset, {
        maxBytes: 4,
        fetchImpl: async () => mockResponse({ body: "too-large", headers: { "content-length": "0" } }),
      }),
    /exceeds the download size limit/,
  );
});

test("download rejects digest mismatches", async () => {
  const body = new TextEncoder().encode("not-the-expected-archive");
  const asset = {
    ...assetFor("linux", "x64"),
    sha256: "11".repeat(32),
    url: "https://example.test/x",
  };
  await assert.rejects(
    () =>
      download(asset, {
        fetchImpl: async () => mockResponse({ body }),
      }),
    /generator archive digest mismatch/,
  );
});

test("download returns verified bytes when digest matches", async () => {
  const body = new TextEncoder().encode("verified-archive-bytes");
  const asset = {
    ...assetFor("linux", "x64"),
    sha256: sha256(body),
    url: "https://example.test/x",
  };
  const got = await download(asset, {
    fetchImpl: async () => mockResponse({ body }),
  });
  assert.equal(sha256(got), asset.sha256);
  assert.equal(got.byteLength, body.byteLength);
});

test("installBinary extracts the expected layout and installs the binary", async () => {
  const root = await mkdtemp(path.join(tmpdir(), "pagedigest-cli-"));
  try {
    const stage = path.join(root, "stage");
    const archiveStem = `pagedigest-generator-v${GENERATOR_VERSION}-x86_64-unknown-linux-gnu`;
    const payloadDir = path.join(stage, archiveStem);
    await mkdir(payloadDir, { recursive: true });
    const fakeBinary = path.join(payloadDir, "pagedigest-generator");
    await writeFile(fakeBinary, "#!/bin/sh\necho ok\n", { mode: 0o755 });

    const archivePath = path.join(root, `${archiveStem}.tar.gz`);
    const packed = spawnSync("tar", ["-czf", archivePath, "-C", stage, archiveStem], {
      encoding: "utf8",
    });
    assert.equal(packed.status, 0, packed.stderr);

    const archiveBytes = new Uint8Array(await readFile(archivePath));
    const asset = {
      target: "x86_64-unknown-linux-gnu",
      extension: "tar.gz",
      archiveName: path.basename(archivePath),
      url: "https://example.test/generator.tar.gz",
      sha256: sha256(archiveBytes),
    };

    const destination = path.join(root, "cache", "pagedigest-generator");
    await installBinary(asset, destination, {
      platform: "linux",
      fetchImpl: async () => mockResponse({ body: archiveBytes }),
    });

    const installed = await stat(destination);
    assert.equal(installed.isFile(), true);
    const content = await readFile(destination, "utf8");
    assert.match(content, /echo ok/);
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test("installBinary rejects archives missing the generator binary", async () => {
  const root = await mkdtemp(path.join(tmpdir(), "pagedigest-cli-empty-"));
  try {
    const stage = path.join(root, "stage");
    const archiveStem = `pagedigest-generator-v${GENERATOR_VERSION}-x86_64-unknown-linux-gnu`;
    await mkdir(path.join(stage, archiveStem), { recursive: true });
    // Deliberately omit pagedigest-generator from the archive.
    await writeFile(path.join(stage, archiveStem, "README.txt"), "no binary here\n");

    const archivePath = path.join(root, `${archiveStem}.tar.gz`);
    const packed = spawnSync("tar", ["-czf", archivePath, "-C", stage, archiveStem], {
      encoding: "utf8",
    });
    assert.equal(packed.status, 0, packed.stderr);

    const archiveBytes = new Uint8Array(await readFile(archivePath));
    const asset = {
      target: "x86_64-unknown-linux-gnu",
      extension: "tar.gz",
      archiveName: path.basename(archivePath),
      url: "https://example.test/generator.tar.gz",
      sha256: sha256(archiveBytes),
    };

    await assert.rejects(
      () =>
        installBinary(asset, path.join(root, "out", "pagedigest-generator"), {
          platform: "linux",
          fetchImpl: async () => mockResponse({ body: archiveBytes }),
        }),
      /did not contain the expected binary/,
    );
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test("MAX_ARCHIVE_BYTES is enforced as a hard cap constant", () => {
  assert.equal(MAX_ARCHIVE_BYTES, 10 * 1024 * 1024);
});
