use std::collections::{BTreeMap, HashSet};
use std::fs;
use std::path::{Path, PathBuf};

use anyhow::{Context, Result};
use chrono::Utc;
use clap::Parser;
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use walkdir::WalkDir;

#[derive(Parser, Debug)]
#[command(name = "pagedigest-generator")]
#[command(about = "Generate a pagedigest manifest from static files")]
struct Args {
    /// Directory containing publisher content.
    input_dir: PathBuf,

    /// Output manifest path. Defaults to <input_dir>/.well-known/pagedigest.json.
    #[arg(long)]
    output: Option<PathBuf>,

    /// Persistent state file path. Defaults to sibling pagedigest-state.json next to output manifest.
    #[arg(long)]
    state: Option<PathBuf>,

    /// Include per-entry sha256 digest values.
    #[arg(long, default_value_t = true)]
    with_digest: bool,
}

#[derive(Debug, Serialize)]
struct Manifest {
    version: u8,
    generated: String,
    site_rev: u64,
    entries: BTreeMap<String, ManifestEntry>,
}

#[derive(Debug, Serialize)]
struct ManifestEntry {
    rev: u64,
    #[serde(skip_serializing_if = "Option::is_none")]
    digest: Option<String>,
}

#[derive(Debug, Default, Serialize, Deserialize)]
struct State {
    site_rev: u64,
    entries: BTreeMap<String, StateEntry>,
}

#[derive(Debug, Serialize, Deserialize)]
struct StateEntry {
    rev: u64,
    digest: String,
}

fn main() -> Result<()> {
    let args = Args::parse();
    let input_dir = fs::canonicalize(&args.input_dir)
        .with_context(|| format!("failed to resolve input directory {}", args.input_dir.display()))?;

    let output_path = args
        .output
        .unwrap_or_else(|| input_dir.join(".well-known").join("pagedigest.json"));

    let state_path = args.state.unwrap_or_else(|| {
        output_path
            .parent()
            .unwrap_or(Path::new("."))
            .join("pagedigest-state.json")
    });

    let previous = load_state(&state_path)?;
    let current_digests = collect_digests(&input_dir)?;

    let mut any_change = false;
    let mut entries = BTreeMap::new();

    for (url, digest) in &current_digests {
        let (rev, changed) = match previous.entries.get(url) {
            Some(prev) if prev.digest == *digest => (prev.rev, false),
            Some(prev) => (prev.rev + 1, true),
            None => (1, true),
        };

        if changed {
            any_change = true;
        }

        entries.insert(
            url.clone(),
            ManifestEntry {
                rev,
                digest: args.with_digest.then(|| format!("sha256:{digest}")),
            },
        );
    }

    let current_keys: HashSet<&String> = current_digests.keys().collect();
    if previous.entries.keys().any(|k| !current_keys.contains(k)) {
        any_change = true;
    }

    let site_rev = if any_change {
        previous.site_rev + 1
    } else {
        previous.site_rev
    };

    let manifest = Manifest {
        version: 1,
        generated: Utc::now().to_rfc3339_opts(chrono::SecondsFormat::Secs, true),
        site_rev,
        entries,
    };

    write_json(&output_path, &manifest)?;

    let next_state = State {
        site_rev,
        entries: current_digests
            .into_iter()
            .map(|(k, digest)| {
                let rev = manifest.entries.get(&k).map(|e| e.rev).unwrap_or(1);
                (k, StateEntry { rev, digest })
            })
            .collect(),
    };
    write_json(&state_path, &next_state)?;

    println!("wrote {}", output_path.display());
    println!("state {}", state_path.display());
    println!("site_rev {}", site_rev);
    Ok(())
}

fn load_state(path: &Path) -> Result<State> {
    if !path.exists() {
        return Ok(State::default());
    }

    let raw = fs::read_to_string(path)
        .with_context(|| format!("failed reading state file {}", path.display()))?;
    let state: State =
        serde_json::from_str(&raw).with_context(|| format!("invalid state JSON {}", path.display()))?;
    Ok(state)
}

fn collect_digests(root: &Path) -> Result<BTreeMap<String, String>> {
    let mut out = BTreeMap::new();

    for entry in WalkDir::new(root).into_iter().filter_map(|e| e.ok()) {
        let path = entry.path();
        if !entry.file_type().is_file() {
            continue;
        }

        if path.components().any(|c| c.as_os_str() == ".well-known") {
            continue;
        }

        let rel = path
            .strip_prefix(root)
            .with_context(|| format!("failed to strip root prefix for {}", path.display()))?;

        let url = format!("/{}", rel.to_string_lossy().replace('\\', "/"));
        let bytes = fs::read(path).with_context(|| format!("failed reading {}", path.display()))?;
        let digest = sha256_hex(&bytes);
        out.insert(url, digest);
    }

    Ok(out)
}

fn sha256_hex(bytes: &[u8]) -> String {
    let mut hasher = Sha256::new();
    hasher.update(bytes);
    let digest = hasher.finalize();
    format!("{digest:x}")
}

fn write_json<T: Serialize>(path: &Path, value: &T) -> Result<()> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent)
            .with_context(|| format!("failed creating directory {}", parent.display()))?;
    }

    let json = serde_json::to_string_pretty(value).context("failed to serialize JSON")?;
    fs::write(path, format!("{json}\n")).with_context(|| format!("failed writing {}", path.display()))?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Write;
    use tempfile::tempdir;

    #[test]
    fn sha256_hex_is_stable() {
        let digest = sha256_hex(b"audit match body\n");
        assert_eq!(
            digest,
            "9336daa82aa3403be4c6d7b1c83ac16d9616909253db1083d35a29c5c4ba3a95"
        );
    }

    #[test]
    fn collect_digests_ignores_well_known_directory() {
        let dir = tempdir().expect("tempdir");
        let root = dir.path();
        fs::create_dir_all(root.join(".well-known")).expect("create .well-known");

        let mut kept = fs::File::create(root.join("index.html")).expect("create index");
        kept.write_all(b"hello").expect("write index");

        let mut skipped = fs::File::create(root.join(".well-known").join("pagedigest.json"))
            .expect("create manifest");
        skipped
            .write_all(b"{}")
            .expect("write manifest fixture");

        let digests = collect_digests(root).expect("collect digests");
        assert!(digests.contains_key("/index.html"));
        assert!(!digests.contains_key("/.well-known/pagedigest.json"));
    }
}
