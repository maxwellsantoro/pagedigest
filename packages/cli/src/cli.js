#!/usr/bin/env node

import { createHash } from "node:crypto";
import { realpathSync } from "node:fs";
import { chmod, copyFile, mkdir, mkdtemp, rename, rm, stat, writeFile } from "node:fs/promises";
import { homedir } from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

export const GENERATOR_VERSION = "0.1.0";
const RELEASE_ROOT = `https://github.com/maxwellsantoro/pagedigest/releases/download/generator-v${GENERATOR_VERSION}`;
const MAX_ARCHIVE_BYTES = 10 * 1024 * 1024;

export const ASSETS = Object.freeze({
  "darwin-arm64": {
    target: "aarch64-apple-darwin",
    sha256: "557a42ec51840f9c7554f50836d784cef2ed405265b8d5739e8351277e9062ad",
    extension: "tar.gz",
  },
  "darwin-x64": {
    target: "x86_64-apple-darwin",
    sha256: "4772d27f13aa411584684611fa0a41eaba683b700eb54747743bb733181599c0",
    extension: "tar.gz",
  },
  "linux-x64": {
    target: "x86_64-unknown-linux-gnu",
    sha256: "d676e8158671a04c17481d210927d531f7cfac90d10895c723114a3534cf4ac4",
    extension: "tar.gz",
  },
  "win32-x64": {
    target: "x86_64-pc-windows-msvc",
    sha256: "6b06c958a857b92bc26330571ad1c031f7974b1f07a19605b270a53f463e2bea",
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

function cacheDirectory(env = process.env) {
  const base = env.PAGEDIGEST_CACHE_DIR || env.XDG_CACHE_HOME || path.join(homedir(), ".cache");
  return path.join(base, "pagedigest", GENERATOR_VERSION, `${process.platform}-${process.arch}`);
}

async function isFile(filename) {
  try {
    return (await stat(filename)).isFile();
  } catch (error) {
    if (error.code === "ENOENT") return false;
    throw error;
  }
}

async function download(asset) {
  const response = await fetch(asset.url, { redirect: "follow" });
  if (!response.ok) {
    throw new Error(`failed to download generator (${response.status} ${response.statusText})`);
  }
  const declaredLength = Number(response.headers.get("content-length") || 0);
  if (declaredLength > MAX_ARCHIVE_BYTES) {
    throw new Error("generator archive exceeds the download size limit");
  }
  const bytes = new Uint8Array(await response.arrayBuffer());
  if (bytes.byteLength > MAX_ARCHIVE_BYTES) {
    throw new Error("generator archive exceeds the download size limit");
  }
  const actualDigest = sha256(bytes);
  if (actualDigest !== asset.sha256) {
    throw new Error(`generator archive digest mismatch: expected ${asset.sha256}, received ${actualDigest}`);
  }
  return bytes;
}

async function installBinary(asset, destination) {
  const cacheRoot = path.dirname(destination);
  await mkdir(cacheRoot, { recursive: true });
  const tempRoot = await mkdtemp(path.join(cacheRoot, ".install-"));
  try {
    const archivePath = path.join(tempRoot, asset.archiveName);
    await writeFile(archivePath, await download(asset), { flag: "wx" });
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
    const binaryName = process.platform === "win32" ? "pagedigest-generator.exe" : "pagedigest-generator";
    const archiveStem = asset.archiveName.replace(/\.(?:tar\.gz|zip)$/, "");
    const source = path.join(extractRoot, archiveStem, binaryName);
    if (!(await isFile(source))) {
      throw new Error("generator archive did not contain the expected binary");
    }
    const staged = path.join(tempRoot, binaryName);
    await copyFile(source, staged);
    if (process.platform !== "win32") await chmod(staged, 0o755);
    try {
      await rename(staged, destination);
    } catch (error) {
      if (!(await isFile(destination))) throw error;
    }
  } finally {
    await rm(tempRoot, { recursive: true, force: true });
  }
}

export async function generatorBinary() {
  const binaryName = process.platform === "win32" ? "pagedigest-generator.exe" : "pagedigest-generator";
  const destination = path.join(cacheDirectory(), binaryName);
  if (!(await isFile(destination))) await installBinary(assetFor(), destination);
  return destination;
}

export async function main(args = process.argv.slice(2)) {
  const binary = await generatorBinary();
  const result = spawnSync(binary, args, { stdio: "inherit", windowsHide: false });
  if (result.error) throw result.error;
  if (result.signal) throw new Error(`pagedigest-generator terminated by ${result.signal}`);
  process.exitCode = result.status ?? 1;
}

const invokedDirectly = process.argv[1] && realpathSync(process.argv[1]) === fileURLToPath(import.meta.url);
if (invokedDirectly) {
  main().catch((error) => {
    console.error(`pagedigest: ${error.message}`);
    process.exitCode = 1;
  });
}
