import assert from "node:assert/strict";
import { mkdir, mkdtemp, readFile, rm, symlink, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { pathToFileURL } from "node:url";
import test from "node:test";

import pagedigest, { generateManifest } from "../src/index.js";
import { build } from "astro";

async function fixture() {
  return mkdtemp(path.join(tmpdir(), "pagedigest-astro-"));
}

test("generates stable revisions for unchanged output", async () => {
  const root = await fixture();
  try {
    const out = path.join(root, "dist");
    const state = path.join(root, ".astro", "pagedigest-state.json");
    await mkdir(path.join(out, "blog"), { recursive: true });
    await writeFile(path.join(out, "index.html"), "<h1>Home</h1>\n", "utf8");
    await writeFile(path.join(out, "blog", "index.html"), "<h1>Blog</h1>\n", "utf8");

    const first = await generateManifest({
      outputDir: out,
      statePath: state,
      generated: "2026-07-04T00:00:00Z",
    });
    const second = await generateManifest({
      outputDir: out,
      statePath: state,
      generated: "2026-07-04T00:01:00Z",
    });

    assert.equal(first.manifest.site_rev, 1);
    assert.equal(second.manifest.site_rev, 1);
    assert.deepEqual(Object.keys(second.manifest.entries), ["/", "/blog/"]);
    assert.match(second.manifest.entries["/"].digest, /^sha256:[a-f0-9]{64}$/);
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test("increments entry and site revisions when output changes", async () => {
  const root = await fixture();
  try {
    const out = path.join(root, "dist");
    const state = path.join(root, ".astro", "pagedigest-state.json");
    await mkdir(out, { recursive: true });
    await writeFile(path.join(out, "index.html"), "one\n", "utf8");
    await generateManifest({ outputDir: out, statePath: state, generated: "2026-07-04T00:00:00Z" });

    await writeFile(path.join(out, "index.html"), "two\n", "utf8");
    const result = await generateManifest({
      outputDir: out,
      statePath: state,
      generated: "2026-07-04T00:01:00Z",
    });

    assert.equal(result.manifest.site_rev, 2);
    assert.equal(result.manifest.entries["/"].rev, 2);
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test("prefix coverage filters generated entries", async () => {
  const root = await fixture();
  try {
    const out = path.join(root, "dist");
    const state = path.join(root, "state.json");
    await mkdir(path.join(out, "blog"), { recursive: true });
    await writeFile(path.join(out, "index.html"), "home\n", "utf8");
    await writeFile(path.join(out, "blog", "index.html"), "blog\n", "utf8");

    const result = await generateManifest({
      outputDir: out,
      statePath: state,
      coverage: { mode: "prefixes", prefixes: ["/blog/"] },
      generated: "2026-07-04T00:00:00Z",
    });

    assert.deepEqual(Object.keys(result.manifest.entries), ["/blog/"]);
    assert.deepEqual(result.manifest.coverage, { mode: "prefixes", prefixes: ["/blog/"] });
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test("rejects duplicate URL keys from index.html and index.htm", async () => {
  const root = await fixture();
  try {
    const out = path.join(root, "dist");
    const state = path.join(root, "state.json");
    await mkdir(out, { recursive: true });
    await writeFile(path.join(out, "index.html"), "html\n", "utf8");
    await writeFile(path.join(out, "index.htm"), "htm\n", "utf8");
    await assert.rejects(
      () => generateManifest({ outputDir: out, statePath: state, generated: "2026-07-04T00:00:00Z" }),
      /duplicate URL key/,
    );
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test("skips .well-known files and retains rev high-water after removal", async () => {
  const root = await fixture();
  try {
    const out = path.join(root, "dist");
    const state = path.join(root, "state.json");
    await mkdir(path.join(out, ".well-known"), { recursive: true });
    await writeFile(path.join(out, "index.html"), "one\n", "utf8");
    await writeFile(path.join(out, ".well-known", "other.html"), "secret\n", "utf8");

    const first = await generateManifest({
      outputDir: out,
      statePath: state,
      generated: "2026-07-04T00:00:00Z",
    });
    assert.deepEqual(Object.keys(first.manifest.entries), ["/"]);
    assert.equal(first.manifest.entries["/"].rev, 1);

    await writeFile(path.join(out, "index.html"), "two\n", "utf8");
    await generateManifest({
      outputDir: out,
      statePath: state,
      generated: "2026-07-04T00:01:00Z",
    });

    await rm(path.join(out, "index.html"));
    const removed = await generateManifest({
      outputDir: out,
      statePath: state,
      generated: "2026-07-04T00:02:00Z",
    });
    assert.deepEqual(Object.keys(removed.manifest.entries), []);
    const stateJson = JSON.parse(await readFile(state, "utf8"));
    assert.equal(stateJson.retired["/"].rev, 2);

    await writeFile(path.join(out, "index.html"), "two\n", "utf8");
    const restored = await generateManifest({
      outputDir: out,
      statePath: state,
      generated: "2026-07-04T00:03:00Z",
    });
    assert.equal(restored.manifest.entries["/"].rev, 2);
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test("percent-encodes spaces in path segments", async () => {
  const root = await fixture();
  try {
    const out = path.join(root, "dist");
    const state = path.join(root, "state.json");
    await mkdir(out, { recursive: true });
    await writeFile(path.join(out, "hello world.html"), "hi\n", "utf8");
    const result = await generateManifest({
      outputDir: out,
      statePath: state,
      generated: "2026-07-04T00:00:00Z",
    });
    assert.deepEqual(Object.keys(result.manifest.entries), ["/hello%20world.html"]);
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test("withModified emits stable observation timestamps across rebuilds", async () => {
  const root = await fixture();
  try {
    const out = path.join(root, "dist");
    const state = path.join(root, "state.json");
    await mkdir(out, { recursive: true });
    await writeFile(path.join(out, "index.html"), "stable\n", "utf8");

    const first = await generateManifest({
      outputDir: out,
      statePath: state,
      withModified: true,
      generated: "2026-07-04T00:00:00Z",
    });
    assert.equal(first.manifest.entries["/"].modified, "2026-07-04T00:00:00Z");

    const second = await generateManifest({
      outputDir: out,
      statePath: state,
      withModified: true,
      generated: "2026-07-04T12:00:00Z",
    });
    assert.equal(second.manifest.site_rev, 1);
    assert.equal(second.manifest.entries["/"].modified, "2026-07-04T00:00:00Z");

    await writeFile(path.join(out, "index.html"), "changed\n", "utf8");
    const third = await generateManifest({
      outputDir: out,
      statePath: state,
      withModified: true,
      generated: "2026-07-05T00:00:00Z",
    });
    assert.equal(third.manifest.site_rev, 2);
    assert.equal(third.manifest.entries["/"].modified, "2026-07-05T00:00:00Z");
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test("integration exposes Astro build hooks", () => {
  const integration = pagedigest();
  assert.equal(integration.name, "@pagedigest/astro");
  assert.equal(typeof integration.hooks["astro:build:done"], "function");
  assert.equal(typeof integration.hooks["astro:config:done"], "function");
});

test("writes a custom output path without indexing the manifest", async () => {
  const root = await fixture();
  try {
    const out = path.join(root, "dist");
    const state = path.join(root, "state.json");
    await mkdir(out, { recursive: true });
    await writeFile(path.join(out, "index.html"), "home\n", "utf8");

    const result = await generateManifest({
      outputDir: out,
      statePath: state,
      output: "manifest/pagedigest.json",
      generated: "2026-07-04T00:00:00Z",
    });
    const manifest = JSON.parse(await readFile(result.manifestPath, "utf8"));

    assert.equal(path.relative(out, result.manifestPath), path.join("manifest", "pagedigest.json"));
    assert.deepEqual(Object.keys(manifest.entries), ["/"]);
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test("runs inside a real Astro build", async () => {
  const root = await fixture();
  try {
    const pageDir = path.join(root, "src", "pages");
    await mkdir(pageDir, { recursive: true });
    await symlink(path.resolve("node_modules"), path.join(root, "node_modules"), "dir");
    await writeFile(path.join(pageDir, "index.astro"), "<h1>Astro PageDigest</h1>\n", "utf8");

    const integrationUrl = pathToFileURL(path.resolve("src/index.js")).href;
    await writeFile(
      path.join(root, "astro.config.mjs"),
      [
        `import pagedigest from ${JSON.stringify(integrationUrl)};`,
        "export default {",
        '  output: "static",',
        '  integrations: [pagedigest({ state: "pagedigest-state.json" })],',
        "};",
        "",
      ].join("\n"),
      "utf8",
    );

    await build({ root });

    const manifest = JSON.parse(
      await readFile(path.join(root, "dist", ".well-known", "pagedigest.json"), "utf8"),
    );
    assert.equal(manifest.version, 1);
    assert.equal(manifest.site_rev, 1);
    assert.deepEqual(Object.keys(manifest.entries), ["/"]);
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});
