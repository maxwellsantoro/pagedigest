import type { AstroIntegration } from "astro";

export interface PageDigestAstroOptions {
  /** @default ".well-known/pagedigest.json" */
  output?: string;

  /**
   * Persistent revision-state path, relative to the Astro project root unless
   * absolute.
   * @default ".astro/pagedigest-state.json"
   */
  state?: string;

  /** @default [".html", ".htm"] */
  includeExtensions?: string[];

  /**
   * Emit per-entry SHA-256 digests of generated identity bytes.
   * Digests are of build output; reconcile after deploy when CDNs rewrite HTML.
   * @default true
   */
  withDigest?: boolean;

  /**
   * Emit stable per-entry `modified` timestamps (content-observation time,
   * not filesystem mtime). Matches the Rust generator's `--with-modified`.
   * @default false
   */
  withModified?: boolean;

  /** @default { mode: "complete" } */
  coverage?: { mode: "complete" } | { mode: "prefixes"; prefixes: string[] } | false;
}

export interface GenerateManifestOptions {
  outputDir: string;
  statePath: string;
  output?: string;
  includeExtensions?: string[];
  withDigest?: boolean;
  withModified?: boolean;
  coverage?: PageDigestAstroOptions["coverage"];
  /** Fixed `generated` / observation timestamp for tests. */
  generated?: string;
}

export function urlKeyForHtml(relativePath: string): string;

export function generateManifest(options: GenerateManifestOptions): Promise<{
  manifest: Record<string, unknown>;
  manifestPath: string;
  statePath: string;
}>;

export default function pagedigest(options?: PageDigestAstroOptions): AstroIntegration;
