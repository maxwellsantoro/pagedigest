import { createHash } from "node:crypto";
import { mkdir, readFile, readdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const DEFAULT_OUTPUT = ".well-known/pagedigest.json";
const DEFAULT_STATE = ".astro/pagedigest-state.json";
const DEFAULT_EXTENSIONS = [".html", ".htm"];

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

function urlKeyForHtml(relativePath) {
  const normalized = relativePath.replaceAll(path.sep, "/");
  if (normalized === "index.html" || normalized === "index.htm") {
    return "/";
  }
  if (normalized.endsWith("/index.html")) {
    return `/${normalized.slice(0, -"index.html".length)}`;
  }
  if (normalized.endsWith("/index.htm")) {
    return `/${normalized.slice(0, -"index.htm".length)}`;
  }
  return `/${normalized}`;
}

async function walkFiles(root, includeExtensions, outputPath) {
  const files = [];

  async function visit(directory) {
    for (const entry of await readdir(directory, { withFileTypes: true })) {
      const absolute = path.join(directory, entry.name);
      if (entry.isDirectory()) {
        await visit(absolute);
        continue;
      }
      if (!entry.isFile()) {
        continue;
      }
      const relative = path.relative(root, absolute).replaceAll(path.sep, "/");
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
      };
    }
  } catch (error) {
    if (error.code !== "ENOENT") {
      throw error;
    }
  }
  return { site_rev: 0, coverage: undefined, entries: {} };
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

export async function generateManifest(options) {
  const outputDir = path.resolve(options.outputDir);
  const outputPath = normalizeOutputPath(options.output ?? DEFAULT_OUTPUT);
  const statePath = path.resolve(options.statePath);
  const includeExtensions = new Set((options.includeExtensions ?? DEFAULT_EXTENSIONS).map(normalizeExtension));
  const coverage = normalizeCoverage(options.coverage);
  const withDigest = options.withDigest ?? true;
  const generated = options.generated ?? new Date().toISOString().replace(/\.\d{3}Z$/, "Z");

  const previous = await readState(statePath);
  const files = await walkFiles(outputDir, includeExtensions, outputPath);
  const nextEntries = {};
  let changed = changedCoverage(previous.coverage, coverage);

  for (const file of files) {
    const urlKey = urlKeyForHtml(file.relative);
    if (!covered(urlKey, coverage)) {
      continue;
    }
    const body = await readFile(file.absolute);
    const contentHash = sha256(body);
    const previousEntry = previous.entries[urlKey];
    const rev =
      previousEntry && previousEntry.content_hash === contentHash
        ? previousEntry.rev
        : Math.max(1, (previousEntry?.rev ?? 0) + 1);
    if (!previousEntry || previousEntry.content_hash !== contentHash) {
      changed = true;
    }
    nextEntries[urlKey] = {
      rev,
      content_hash: contentHash,
      ...(withDigest ? { digest: `sha256:${contentHash}` } : {}),
    };
  }

  if (Object.keys(previous.entries).some((urlKey) => !(urlKey in nextEntries))) {
    changed = true;
  }

  const siteRev = changed ? previous.site_rev + 1 : previous.site_rev;
  const manifestEntries = {};
  for (const [urlKey, entry] of Object.entries(nextEntries).sort(([a], [b]) => a.localeCompare(b))) {
    manifestEntries[urlKey] = {
      rev: entry.rev,
      ...(entry.digest ? { digest: entry.digest } : {}),
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
  };

  const manifestPath = path.join(outputDir, outputPath);
  await mkdir(path.dirname(manifestPath), { recursive: true });
  await mkdir(path.dirname(statePath), { recursive: true });
  await writeFile(manifestPath, `${JSON.stringify(manifest, null, 2)}\n`);
  await writeFile(statePath, `${JSON.stringify(state, null, 2)}\n`);
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
          coverage: options.coverage,
        });
        logger.info(
          `wrote ${path.relative(outputDir, result.manifestPath)} with ${Object.keys(result.manifest.entries).length} entries`,
        );
      },
    },
  };
}
