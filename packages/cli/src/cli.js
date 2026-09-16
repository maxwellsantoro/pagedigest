#!/usr/bin/env node

import { createHash } from "node:crypto";
import { realpathSync } from "node:fs";
import { chmod, copyFile, mkdir, mkdtemp, rename, rm, stat, writeFile } from "node:fs/promises";
import { homedir } from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

export const GENERATOR_VERSION = "0.3.0";
const RELEASE_ROOT = `https://github.com/maxwellsantoro/pagedigest/releases/download/generator-v${GENERATOR_VERSION}`;
export const MAX_ARCHIVE_BYTES = 10 * 1024 * 1024;

export const ASSETS = Object.freeze({
  "darwin-arm64": {
    target: "aarch64-apple-darwin",
    sha256: "fb42ec0e8a82c61d4d51e7260e481aefed7d7aadbbdf6e9d66522676a99afae9",
    extension: "tar.gz",
  },
  "darwin-x64": {
    target: "x86_64-apple-darwin",
    sha256: "b7c5d5bb27c5aa28046dbced7f522bba421543b42576ef94444d2ee8d1a71ebc",
    extension: "tar.gz",
  },
  "linux-x64": {
    target: "x86_64-unknown-linux-gnu",
    sha256: "9ff4a7a602ddecd6810b69ac8bdcc9a673b64e5580c1342dffc3058bfc67e637",
    extension: "tar.gz",
  },
  "win32-x64": {
    target: "x86_64-pc-windows-msvc",
    sha256: "266fa7a7d498188d27c08bde04f2ac146999a8d05e3eb4011b16a5e81073ecc5",
    extension: "zip",
  },
});

export function assetFor(platform = process.platform, arch = process.arch) {
  const key = `${platform}-${arch}`;
  const asset = ASSETS[key];
  if (!asset) {
    throw new Error(`pagedigest does not provide a generator binary for ${platform}/${arch}`);
  }
  const archiveName = `pagedigest-generator-v${GENERATOR_VERSION}-${asset.target}.${asset.extension}`;
  return { ...asset, archiveName, url: `${RELEASE_ROOT}/${archiveName}` };
}

export function sha256(bytes) {
  return createHash("sha256").update(bytes).digest("hex");
}

export function cacheDirectory(env = process.env, platform = process.platform, arch = process.arch) {
  const base = env.PAGEDIGEST_CACHE_DIR || env.XDG_CACHE_HOME || path.join(homedir(), ".cache");
  return path.join(base, "pagedigest", GENERATOR_VERSION, `${platform}-${arch}`);
}

async function isFile(filename) {
  try {
    return (await stat(filename)).isFile();
  } catch (error) {
    if (error.code === "ENOENT") return false;
    throw error;
  }
}

/**
 * Download and verify a generator archive.
 * @param {ReturnType<typeof assetFor>} asset
 * @param {{ fetchImpl?: typeof fetch, maxBytes?: number }} [options]
 */
export async function download(asset, options = {}) {
  const fetchImpl = options.fetchImpl ?? globalThis.fetch;
  const maxBytes = options.maxBytes ?? MAX_ARCHIVE_BYTES;
  if (typeof fetchImpl !== "function") {
    throw new Error("fetch is not available; Node.js 20+ is required");
  }
  const response = await fetchImpl(asset.url, { redirect: "follow" });
  if (!response.ok) {
    throw new Error(`failed to download generator (${response.status} ${response.statusText})`);
  }
  const declaredLength = Number(response.headers.get("content-length") || 0);
  if (declaredLength > maxBytes) {
    throw new Error("generator archive exceeds the download size limit");
  }
  const bytes = new Uint8Array(await response.arrayBuffer());
  if (bytes.byteLength > maxBytes) {
    throw new Error("generator archive exceeds the download size limit");
  }
  const actualDigest = sha256(bytes);
  if (actualDigest !== asset.sha256) {
    throw new Error(`generator archive digest mismatch: expected ${asset.sha256}, received ${actualDigest}`);
  }
  return bytes;
}

/**
 * Install a verified archive into destination.
 * Archives are extracted with the system `tar` (including `.zip` on Windows via tar.exe).
 * @param {ReturnType<typeof assetFor>} asset
 * @param {string} destination
 * @param {{ fetchImpl?: typeof fetch, maxBytes?: number, platform?: string }} [options]
 */
export async function installBinary(asset, destination, options = {}) {
  const platform = options.platform ?? process.platform;
  const cacheRoot = path.dirname(destination);
  await mkdir(cacheRoot, { recursive: true });
  const tempRoot = await mkdtemp(path.join(cacheRoot, ".install-"));
  try {
    const archivePath = path.join(tempRoot, asset.archiveName);
    await writeFile(archivePath, await download(asset, options), { flag: "wx" });
    const extractRoot = path.join(tempRoot, "extract");
    await mkdir(extractRoot);
    const extracted = spawnSync("tar", ["-xf", archivePath, "-C", extractRoot], {
      encoding: "utf8",
      windowsHide: true,
    });
    if (extracted.error || extracted.status !== 0) {
      const detail = extracted.error?.message || extracted.stderr.trim() || `exit ${extracted.status}`;
      throw new Error(`failed to extract generator archive with tar: ${detail}`);
    }
    const binaryName = platform === "win32" ? "pagedigest-generator.exe" : "pagedigest-generator";
    const archiveStem = asset.archiveName.replace(/\.(?:tar\.gz|zip)$/, "");
    const source = path.join(extractRoot, archiveStem, binaryName);
    if (!(await isFile(source))) {
      throw new Error("generator archive did not contain the expected binary");
    }
    const staged = path.join(tempRoot, binaryName);
    await copyFile(source, staged);
    if (platform !== "win32") await chmod(staged, 0o755);
    try {
      await rename(staged, destination);
    } catch (error) {
      if (!(await isFile(destination))) throw error;
    }
  } finally {
    await rm(tempRoot, { recursive: true, force: true });
  }
}

export async function generatorBinary(options = {}) {
  const platform = options.platform ?? process.platform;
  const arch = options.arch ?? process.arch;
  const env = options.env ?? process.env;
  const binaryName = platform === "win32" ? "pagedigest-generator.exe" : "pagedigest-generator";
  const destination = path.join(cacheDirectory(env, platform, arch), binaryName);
  if (!(await isFile(destination))) {
    await installBinary(assetFor(platform, arch), destination, { ...options, platform });
  }
  return destination;
}

function digestReminder(args) {
  return args.includes("--with-digest");
}

export async function main(args = process.argv.slice(2)) {
  const binary = await generatorBinary();
  const result = spawnSync(binary, args, { stdio: "inherit", windowsHide: false });
  if (result.error) throw result.error;
  if (result.signal) throw new Error(`pagedigest-generator terminated by ${result.signal}`);
  process.exitCode = result.status ?? 1;
  if (result.status === 0 && digestReminder(args)) {
    console.error(
      "pagedigest: digests hash on-disk build output. After deploy, run tools/reconcile_served_digests.py --apply if the CDN rewrites HTML (CONTENT_HYGIENE.md).",
    );
  }
}

const invokedDirectly = process.argv[1] && realpathSync(process.argv[1]) === fileURLToPath(import.meta.url);
if (invokedDirectly) {
  main().catch((error) => {
    console.error(`pagedigest: ${error.message}`);
    process.exitCode = 1;
  });
}
