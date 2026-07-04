#!/usr/bin/env node

import { createHash } from "node:crypto";
import { realpathSync } from "node:fs";
import { chmod, copyFile, mkdir, mkdtemp, rename, rm, stat, writeFile } from "node:fs/promises";
import { homedir } from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

export const GENERATOR_VERSION = "0.2.0";
const RELEASE_ROOT = `https://github.com/maxwellsantoro/pagedigest/releases/download/generator-v${GENERATOR_VERSION}`;
const MAX_ARCHIVE_BYTES = 10 * 1024 * 1024;

export const ASSETS = Object.freeze({
  "darwin-arm64": {
    target: "aarch64-apple-darwin",
    sha256: "7da52a4780166be4b65ce1549fe46b0a874b5bc4a742540f440eff3339b395ce",
    extension: "tar.gz",
  },
  "darwin-x64": {
    target: "x86_64-apple-darwin",
    sha256: "c833ce5fc7ff814762ea69a55f58287eb3c0502f9281071454349d96713c1fd2",
    extension: "tar.gz",
  },
  "linux-x64": {
    target: "x86_64-unknown-linux-gnu",
    sha256: "46705796ff1c681c60eb80bbd3ae5cecb6b8454c1604ef379fb3e92553c4f8e4",
    extension: "tar.gz",
  },
  "win32-x64": {
    target: "x86_64-pc-windows-msvc",
    sha256: "62cbf491bb4a7a92aadcf2a537b49718e071abd8a5a191351c0a9d3924f52fef",
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
