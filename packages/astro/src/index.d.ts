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

  /** @default true */
  withDigest?: boolean;

  /** @default { mode: "complete" } */
  coverage?: { mode: "complete" } | { mode: "prefixes"; prefixes: string[] } | false;
}

export default function pagedigest(options?: PageDigestAstroOptions): AstroIntegration;
