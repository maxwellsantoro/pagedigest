// Exercise the exact npm archive that will be published, outside the source tree.
import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { mkdtemp, mkdir, writeFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

const archive = path.resolve(process.argv[2]);
const root = await mkdtemp(path.join(tmpdir(), 'pagedigest-astro-release-'));
try {
  execFileSync('npm', ['install', '--prefix', root, '--ignore-scripts', '--legacy-peer-deps', archive], { stdio: 'inherit' });
  const { generateManifest } = await import(pathToFileURL(path.join(root, 'node_modules/@pagedigest/astro/src/index.js')));
  const outputDir = path.join(root, 'site'), statePath = path.join(root, 'state.json');
  await mkdir(outputDir);
  await writeFile(path.join(outputDir, 'index.html'), 'A');
  await assert.rejects(generateManifest({ outputDir, statePath }), /missing durable state/);
  const first = await generateManifest({ outputDir, statePath, initialize: true });
  assert.equal(first.manifest.site_rev, 1);
  const warm = await generateManifest({ outputDir, statePath });
  assert.equal(warm.manifest.site_rev, 1);
  await writeFile(path.join(outputDir, 'index.html'), 'B');
  const changed = await generateManifest({ outputDir, statePath });
  assert.equal(changed.manifest.entries['/'].rev, 2);
  await rm(statePath);
  await assert.rejects(generateManifest({ outputDir, statePath }), /missing durable state/);
  const recovered = await generateManifest({ outputDir, statePath, recoverFloor: 10 });
  assert.equal(recovered.manifest.entries['/'].rev, 11);
  console.log('exact Astro archive installation and state recovery passed');
} finally { await rm(root, { recursive: true, force: true }); }
