import { createHash } from "node:crypto";
import { mkdir, readFile, readdir, rename, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const DEFAULT_OUTPUT = ".well-known/pagedigest.json";
const DEFAULT_STATE = ".astro/pagedigest-state.json";
const DEFAULT_EXTENSIONS = [".html", ".htm"];

// Match the Rust generator's practical encode set for path segments
// (controls, space, and selected reserved/specials; does not re-encode '%').
const ENCODE_RE = /[\u0000-\u001f\u007f "#<>?`{}/\\]/g;

function normalizeExtension(extension) {
  return extension.startsWith(".") ? extension.toLowerCase() : `.${extension.toLowerCase()}`;
}

function normalizeOutputPath(output) {
  const normalized = output.replaceAll("\\", "/").replace(/^\/+/, "");
  if (!normalized || normalized.split("/").includes("..")) {
    throw new Error("pagedigest output must be a relative path inside Astro's output directory");
  }
  return normalized;
}

function normalizeCoverage(coverage) {
  if (coverage === false) {
    return undefined;
  }
  if (coverage === undefined || coverage.mode === "complete") {
    return { mode: "complete" };
  }
  if (coverage.mode === "prefixes") {
    if (!Array.isArray(coverage.prefixes) || coverage.prefixes.length === 0) {
      throw new Error("pagedigest coverage.prefixes must be a non-empty array");
    }
    const prefixes = [...new Set(coverage.prefixes)].sort();
    for (const prefix of prefixes) {
      if (typeof prefix !== "string" || !prefix.startsWith("/")) {
        throw new Error("pagedigest coverage prefixes must start with /");
      }
    }
    return { mode: "prefixes", prefixes };
  }
  throw new Error("pagedigest coverage mode must be complete, prefixes, or false");
}

function encodePathSegment(segment) {
  return segment.replace(ENCODE_RE, (ch) => {
    const bytes = Buffer.from(ch, "utf8");
    let out = "";
    for (const byte of bytes) {
      out += `%${byte.toString(16).toUpperCase().padStart(2, "0")}`;
    }
    return out;
  });
}

function trailingSlashUrlKey(encodedRel) {
  for (const indexName of ["index.html", "index.htm"]) {
    if (encodedRel === indexName) {
      return "/";
    }
    const suffix = `/${indexName}`;
    if (encodedRel.endsWith(suffix)) {
      return `/${encodedRel.slice(0, -suffix.length)}/`;
    }
  }
  return `/${encodedRel}`;
}

export function urlKeyForHtml(relativePath) {
  const normalized = relativePath.replaceAll(path.sep, "/");
  const segments = normalized.split("/").map(encodePathSegment);
  const encodedRel = segments.join("/");
  const url = trailingSlashUrlKey(encodedRel);
  if (!url.startsWith("/") || url.includes("#") || url.startsWith("//")) {
    throw new Error(`invalid URL key derived from ${relativePath}`);
  }
  return url;
}

async function walkFiles(root, includeExtensions, outputPath) {
  const files = [];

  async function visit(directory) {
    for (const entry of await readdir(directory, { withFileTypes: true })) {
      const absolute = path.join(directory, entry.name);
      if (entry.isDirectory()) {
        // Match Rust generator: never index anything under .well-known.
        if (entry.name === ".well-known") {
          continue;
        }
        await visit(absolute);
        continue;
      }
      if (!entry.isFile()) {
        continue;
      }
      const relative = path.relative(root, absolute).replaceAll(path.sep, "/");
      if (relative.split("/").includes(".well-known")) {
        continue;
      }
      if (relative !== outputPath && includeExtensions.has(path.extname(entry.name).toLowerCase())) {
        files.push({ absolute, relative });
      }
    }
  }

  await visit(root);
  files.sort((a, b) => a.relative.localeCompare(b.relative));
  return files;
}

async function readState(statePath) {
  try {
    const parsed = JSON.parse(await readFile(statePath, "utf8"));
    if (typeof parsed === "object" && parsed !== null) {
      return {
        site_rev: Number.isInteger(parsed.site_rev) && parsed.site_rev >= 0 ? parsed.site_rev : 0,
        coverage: parsed.coverage,
        entries: typeof parsed.entries === "object" && parsed.entries !== null ? parsed.entries : {},
        retired: typeof parsed.retired === "object" && parsed.retired !== null ? parsed.retired : {},
      };
    }
  } catch (error) {
    if (error.code !== "ENOENT") {
      throw error;
    }
  }
  return { site_rev: 0, coverage: undefined, entries: {}, retired: {} };
}

function sha256(buffer) {
  return createHash("sha256").update(buffer).digest("hex");
}

function changedCoverage(previous, next) {
  return JSON.stringify(previous ?? null) !== JSON.stringify(next ?? null);
}

function covered(urlKey, coverage) {
  return coverage?.mode !== "prefixes" || coverage.prefixes.some((prefix) => urlKey.startsWith(prefix));
}

async function writeJsonAtomic(filePath, value) {
  await mkdir(path.dirname(filePath), { recursive: true });
  const tempPath = path.join(path.dirname(filePath), `.${path.basename(filePath)}.tmp`);
  await writeFile(tempPath, `${JSON.stringify(value, null, 2)}\n`);
  await rename(tempPath, filePath);
}

function utcNowIso(override) {
  if (override) {
    return override;
  }
  // Stable second precision, matching the Rust generator's Secs format.
  return new Date().toISOString().replace(/\.\d{3}Z$/, "Z");
}

export async function generateManifest(options) {
  const outputDir = path.resolve(options.outputDir);
  const outputPath = normalizeOutputPath(options.output ?? DEFAULT_OUTPUT);
  const statePath = path.resolve(options.statePath);
  const includeExtensions = new Set((options.includeExtensions ?? DEFAULT_EXTENSIONS).map(normalizeExtension));
  const coverage = normalizeCoverage(options.coverage);
  const withDigest = options.withDigest ?? true;
  const withModified = options.withModified ?? false;
  const observedAt = utcNowIso(options.generated);
  const generated = observedAt;

  const previous = await readState(statePath);
  const files = await walkFiles(outputDir, includeExtensions, outputPath);
  const nextEntries = {};
  const seenKeys = new Map();
  let changed = changedCoverage(previous.coverage, coverage);

  for (const file of files) {
    const urlKey = urlKeyForHtml(file.relative);
    if (!covered(urlKey, coverage)) {
      continue;
    }
    if (seenKeys.has(urlKey)) {
      throw new Error(
        `duplicate URL key ${urlKey} from ${file.relative} (also ${seenKeys.get(urlKey)})`,
      );
    }
    seenKeys.set(urlKey, file.relative);
    const body = await readFile(file.absolute);
    const contentHash = sha256(body);
    const previousEntry = previous.entries[urlKey] ?? previous.retired[urlKey];
    const wasActive = Object.hasOwn(previous.entries, urlKey);
    let rev;
    let modified;
    if (previousEntry && previousEntry.content_hash === contentHash) {
      rev = previousEntry.rev;
      modified = previousEntry.modified ?? observedAt;
      // Re-adding a retired key with identical content still changes coverage.
      if (!wasActive) {
        changed = true;
      }
    } else {
      rev = Math.max(1, (previousEntry?.rev ?? 0) + 1);
      modified = observedAt;
      changed = true;
    }
    nextEntries[urlKey] = {
      rev,
      content_hash: contentHash,
      modified,
      ...(withDigest ? { digest: `sha256:${contentHash}` } : {}),
    };
  }

  // High-water marks for URLs that left the current scan set (SPEC §4.1.1).
  const nextRetired = { ...previous.retired };
  for (const urlKey of Object.keys(nextEntries)) {
    delete nextRetired[urlKey];
  }
  for (const [urlKey, previousEntry] of Object.entries(previous.entries)) {
    if (urlKey in nextEntries) {
      continue;
    }
    changed = true;
    nextRetired[urlKey] = {
      rev: previousEntry.rev,
      content_hash: previousEntry.content_hash,
      ...(previousEntry.modified ? { modified: previousEntry.modified } : {}),
    };
  }

  const siteRev = changed ? previous.site_rev + 1 : previous.site_rev;
  const manifestEntries = {};
  for (const [urlKey, entry] of Object.entries(nextEntries).sort(([a], [b]) => a.localeCompare(b))) {
    manifestEntries[urlKey] = {
      rev: entry.rev,
      ...(entry.digest ? { digest: entry.digest } : {}),
      ...(withModified ? { modified: entry.modified } : {}),
    };
  }

  const manifest = {
    version: 1,
    generated,
    site_rev: siteRev,
    ...(coverage ? { coverage } : {}),
    entries: manifestEntries,
  };
  const state = {
    site_rev: siteRev,
    coverage,
    entries: nextEntries,
    ...(Object.keys(nextRetired).length > 0 ? { retired: nextRetired } : {}),
  };

  const manifestPath = path.join(outputDir, outputPath);
  await writeJsonAtomic(manifestPath, manifest);
  await writeJsonAtomic(statePath, state);
  return { manifest, manifestPath, statePath };
}

export default function pagedigest(options = {}) {
  let root = process.cwd();
  return {
    name: "@pagedigest/astro",
    hooks: {
      "astro:config:done": ({ config }) => {
        root = fileURLToPath(config.root);
      },
      "astro:build:done": async ({ dir, logger }) => {
        const outputDir = fileURLToPath(dir);
        const statePath = path.isAbsolute(options.state ?? "")
          ? options.state
          : path.join(root, options.state ?? DEFAULT_STATE);
        const result = await generateManifest({
          outputDir,
          statePath,
          output: options.output,
          includeExtensions: options.includeExtensions,
          withDigest: options.withDigest,
          withModified: options.withModified,
          coverage: options.coverage,
        });
        logger.info(
          `wrote ${path.relative(outputDir, result.manifestPath)} with ${Object.keys(result.manifest.entries).length} entries`,
        );
        if (options.withDigest !== false) {
          logger.info(
            "digests hash build output; after deploy run tools/reconcile_served_digests.py --apply if the CDN rewrites HTML (see CONTENT_HYGIENE.md)",
          );
        }
      },
    },
  };
}
