use std::collections::{BTreeMap, HashSet};
use std::fs;
use std::io::Write;
use std::path::{Path, PathBuf};

use anyhow::{bail, Context, Result};
use chrono::Utc;
use clap::{Parser, ValueEnum};
use percent_encoding::{utf8_percent_encode, AsciiSet, CONTROLS};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use walkdir::WalkDir;

const PATH_SEGMENT_ENCODE_SET: &AsciiSet = &CONTROLS
    .add(b' ')
    .add(b'"')
    .add(b'#')
    .add(b'<')
    .add(b'>')
    .add(b'`')
    .add(b'?')
    .add(b'{')
    .add(b'}')
    .add(b'/');

#[derive(Parser, Debug)]
#[command(name = "pagedigest-generator")]
#[command(about = "Generate a pagedigest manifest from static files")]
struct Args {
    /// Directory containing publisher content.
    input_dir: PathBuf,

    /// Output manifest path. Defaults to <input_dir>/.well-known/pagedigest.json.
    #[arg(long)]
    output: Option<PathBuf>,

    /// Persistent state file path. Defaults to <input_dir_parent>/.pagedigest/state.json.
    #[arg(long)]
    state: Option<PathBuf>,

    /// Route style for index files.
    #[arg(long, value_enum, default_value_t = IndexStyle::TrailingSlash)]
    index_style: IndexStyle,

    /// Comma-separated extension allowlist for files included in entries.
    #[arg(long, value_delimiter = ',', default_values_t = [
        String::from("html"),
        String::from("htm"),
        String::from("md"),
        String::from("markdown"),
    ])]
    include_ext: Vec<String>,

    /// Include per-entry sha256 digest values.
    #[arg(long, default_value_t = false)]
    with_digest: bool,

    /// Include stable per-entry content observation timestamps.
    #[arg(long, default_value_t = false)]
    with_modified: bool,

    /// Coverage metadata to emit.
    #[arg(long, value_enum, default_value_t = CoverageArg::Complete)]
    coverage: CoverageArg,

    /// Origin-relative URL prefix to include (repeatable). Requires --coverage prefixes.
    #[arg(long, required_if_eq("coverage", "prefixes"))]
    prefix: Vec<String>,
}

#[derive(Copy, Clone, Debug, Eq, PartialEq, ValueEnum)]
enum IndexStyle {
    TrailingSlash,
    File,
}

#[derive(Copy, Clone, Debug, Eq, PartialEq, ValueEnum)]
enum CoverageArg {
    Complete,
    Prefixes,
    None,
}

#[derive(Debug, Serialize)]
struct Manifest {
    version: u8,
    generated: String,
    site_rev: u64,
    #[serde(skip_serializing_if = "Option::is_none")]
    coverage: Option<Coverage>,
    entries: BTreeMap<String, ManifestEntry>,
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]
struct Coverage {
    mode: CoverageMode,
    #[serde(skip_serializing_if = "Option::is_none", default)]
    prefixes: Option<Vec<String>>,
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "kebab-case")]
enum CoverageMode {
    Complete,
    Prefixes,
}

#[derive(Debug, Serialize)]
struct ManifestEntry {
    rev: u64,
    #[serde(skip_serializing_if = "Option::is_none")]
    digest: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    modified: Option<String>,
}

#[derive(Debug, Default, Serialize, Deserialize)]
struct State {
    site_rev: u64,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    coverage: Option<Coverage>,
    entries: BTreeMap<String, StateEntry>,
}

#[derive(Debug, Serialize, Deserialize)]
struct StateEntry {
    rev: u64,
    digest: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    modified: Option<String>,
}

fn main() -> Result<()> {
    let args = Args::parse();
    let input_dir = fs::canonicalize(&args.input_dir).with_context(|| {
        format!(
            "failed to resolve input directory {}",
            args.input_dir.display()
        )
    })?;
    let coverage = coverage_for_arg(&args)?;

    let output_path = args
        .output
        .unwrap_or_else(|| input_dir.join(".well-known").join("pagedigest.json"));

    let state_path = args.state.unwrap_or_else(|| {
        input_dir
            .parent()
            .unwrap_or(Path::new("."))
            .join(".pagedigest")
            .join("state.json")
    });

    let previous = load_state(&state_path)?;
    let mut current_digests = collect_digests(&input_dir, args.index_style, &args.include_ext)?;

    if let Some(ref coverage_value) = coverage {
        if let Some(ref prefixes) = coverage_value.prefixes {
            current_digests.retain(|url, _| prefixes.iter().any(|p| url.starts_with(p.as_str())));
        }
    }

    let mut any_change = false;
    let mut entries = BTreeMap::new();
    let mut next_state_entries = BTreeMap::new();
    let observed_at = Utc::now().to_rfc3339_opts(chrono::SecondsFormat::Secs, true);

    for (url, digest) in &current_digests {
        let (rev, changed, modified) = match previous.entries.get(url) {
            Some(prev) if prev.digest == *digest => (
                prev.rev,
                false,
                prev.modified.clone().unwrap_or_else(|| observed_at.clone()),
            ),
            Some(prev) => (prev.rev + 1, true, observed_at.clone()),
            None => (1, true, observed_at.clone()),
        };

        if changed {
            any_change = true;
        }

        entries.insert(
            url.clone(),
            ManifestEntry {
                rev,
                digest: args.with_digest.then(|| format!("sha256:{digest}")),
                modified: args.with_modified.then(|| modified.clone()),
            },
        );
        next_state_entries.insert(
            url.clone(),
            StateEntry {
                rev,
                digest: digest.clone(),
                modified: Some(modified),
            },
        );
    }

    let current_keys: HashSet<&String> = current_digests.keys().collect();
    if previous.entries.keys().any(|k| !current_keys.contains(k)) {
        any_change = true;
    }

    if previous.coverage != coverage {
        any_change = true;
    }

    let site_rev = if any_change {
        previous.site_rev + 1
    } else {
        previous.site_rev
    };

    let manifest = Manifest {
        version: 1,
        generated: observed_at,
        site_rev,
        coverage: coverage.clone(),
        entries,
    };

    let next_state = State {
        site_rev,
        coverage,
        entries: next_state_entries,
    };

    write_json_atomic(&state_path, &next_state)?;
    write_json_atomic(&output_path, &manifest)?;

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
    let state: State = serde_json::from_str(&raw)
        .with_context(|| format!("invalid state JSON {}", path.display()))?;
    Ok(state)
}

fn collect_digests(
    root: &Path,
    index_style: IndexStyle,
    include_ext: &[String],
) -> Result<BTreeMap<String, String>> {
    let mut out = BTreeMap::new();

    for entry in WalkDir::new(root) {
        let entry = entry.with_context(|| format!("failed walking {}", root.display()))?;
        let path = entry.path();
        if !entry.file_type().is_file() {
            continue;
        }

        if path.components().any(|c| c.as_os_str() == ".well-known") {
            continue;
        }

        if !should_include(path, include_ext) {
            continue;
        }

        let rel = path
            .strip_prefix(root)
            .with_context(|| format!("failed to strip root prefix for {}", path.display()))?;

        let url = rel_to_url_key(rel, index_style)?;
        if out.contains_key(&url) {
            bail!("duplicate URL key {url} from {}", path.display());
        }

        let bytes = fs::read(path).with_context(|| format!("failed reading {}", path.display()))?;
        let digest = sha256_hex(&bytes);
        out.insert(url, digest);
    }

    Ok(out)
}

fn should_include(path: &Path, include_ext: &[String]) -> bool {
    match path.extension().and_then(|e| e.to_str()) {
        Some(ext) => include_ext
            .iter()
            .any(|allowed| allowed.eq_ignore_ascii_case(ext)),
        None => false,
    }
}

fn coverage_for_arg(args: &Args) -> Result<Option<Coverage>> {
    if !args.prefix.is_empty() && args.coverage != CoverageArg::Prefixes {
        bail!("--prefix can only be used with --coverage prefixes");
    }
    Ok(match args.coverage {
        CoverageArg::Complete => Some(Coverage {
            mode: CoverageMode::Complete,
            prefixes: None,
        }),
        CoverageArg::None => None,
        CoverageArg::Prefixes => {
            let prefixes = normalize_prefixes(&args.prefix)?;
            Some(Coverage {
                mode: CoverageMode::Prefixes,
                prefixes: Some(prefixes),
            })
        }
    })
}

fn normalize_prefixes(raw: &[String]) -> Result<Vec<String>> {
    if raw.is_empty() {
        bail!("prefixes coverage requires at least one --prefix beginning with '/'");
    }
    let mut prefixes: Vec<String> = Vec::new();
    for value in raw {
        if !value.starts_with('/') {
            bail!("prefix must begin with '/': {value}");
        }
        if !prefixes.contains(value) {
            prefixes.push(value.clone());
        }
    }
    prefixes.sort();
    Ok(prefixes)
}

fn encode_path_segment(segment: &str) -> String {
    utf8_percent_encode(segment, PATH_SEGMENT_ENCODE_SET).to_string()
}

fn trailing_slash_url_key(encoded_rel: &str) -> String {
    for index_name in ["index.html", "index.htm"] {
        if encoded_rel == index_name {
            return "/".to_string();
        }
        let suffix = format!("/{index_name}");
        if let Some(prefix) = encoded_rel.strip_suffix(suffix.as_str()) {
            return format!("/{prefix}/");
        }
    }
    format!("/{encoded_rel}")
}

fn rel_to_url_key(rel: &Path, index_style: IndexStyle) -> Result<String> {
    let rel_str = rel.to_string_lossy().replace('\\', "/");
    let segments: Vec<&str> = rel_str.split('/').collect();
    let encoded_segments: Vec<String> = segments
        .iter()
        .map(|segment| encode_path_segment(segment))
        .collect();
    let encoded_rel = encoded_segments.join("/");

    let url = match index_style {
        IndexStyle::File => format!("/{encoded_rel}"),
        IndexStyle::TrailingSlash => trailing_slash_url_key(&encoded_rel),
    };

    if !url.starts_with('/') || url.contains('#') {
        bail!("invalid URL key derived from {}", rel.display());
    }

    Ok(url)
}

fn sha256_hex(bytes: &[u8]) -> String {
    let mut hasher = Sha256::new();
    hasher.update(bytes);
    let digest = hasher.finalize();
    format!("{digest:x}")
}

fn write_json_atomic<T: Serialize>(path: &Path, value: &T) -> Result<()> {
    let parent = path.parent().with_context(|| {
        format!(
            "destination path {} has no parent directory",
            path.display()
        )
    })?;
    fs::create_dir_all(parent)
        .with_context(|| format!("failed creating directory {}", parent.display()))?;

    let file_name = path
        .file_name()
        .and_then(|name| name.to_str())
        .with_context(|| format!("destination path {} has no file name", path.display()))?;
    let temp_path = parent.join(format!(".{file_name}.tmp"));

    let json = serde_json::to_string_pretty(value).context("failed to serialize JSON")?;
    {
        let mut file = fs::File::create(&temp_path)
            .with_context(|| format!("failed creating temporary file {}", temp_path.display()))?;
        file.write_all(format!("{json}\n").as_bytes())
            .with_context(|| format!("failed writing temporary file {}", temp_path.display()))?;
        file.sync_all()
            .with_context(|| format!("failed syncing temporary file {}", temp_path.display()))?;
    }

    fs::rename(&temp_path, path).with_context(|| {
        format!(
            "failed replacing {} with {}",
            path.display(),
            temp_path.display()
        )
    })?;
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
        skipped.write_all(b"{}").expect("write manifest fixture");

        let include_ext = vec!["html".to_string()];
        let digests = collect_digests(root, IndexStyle::TrailingSlash, &include_ext)
            .expect("collect digests");
        assert!(digests.contains_key("/"));
        assert!(!digests.contains_key("/.well-known/pagedigest.json"));
    }

    #[test]
    fn rel_to_url_key_trailing_slash_style_maps_index_routes() {
        assert_eq!(
            rel_to_url_key(Path::new("index.html"), IndexStyle::TrailingSlash).expect("url key"),
            "/"
        );
        assert_eq!(
            rel_to_url_key(Path::new("about/index.html"), IndexStyle::TrailingSlash)
                .expect("url key"),
            "/about/"
        );
        assert_eq!(
            rel_to_url_key(Path::new("index.htm"), IndexStyle::TrailingSlash).expect("url key"),
            "/"
        );
        assert_eq!(
            rel_to_url_key(Path::new("docs/index.htm"), IndexStyle::TrailingSlash)
                .expect("url key"),
            "/docs/"
        );
    }

    #[test]
    fn rel_to_url_key_file_style_preserves_index_filename() {
        assert_eq!(
            rel_to_url_key(Path::new("index.html"), IndexStyle::File).expect("url key"),
            "/index.html"
        );
        assert_eq!(
            rel_to_url_key(Path::new("about/index.html"), IndexStyle::File).expect("url key"),
            "/about/index.html"
        );
    }

    #[test]
    fn rel_to_url_key_percent_encodes_spaces_and_specials() {
        assert_eq!(
            rel_to_url_key(Path::new("hello world.html"), IndexStyle::File).expect("url key"),
            "/hello%20world.html"
        );
        assert_eq!(
            rel_to_url_key(Path::new("a\"b.html"), IndexStyle::File).expect("url key"),
            "/a%22b.html"
        );
        assert_eq!(
            rel_to_url_key(Path::new("q?x.html"), IndexStyle::File).expect("url key"),
            "/q%3Fx.html"
        );
    }

    #[test]
    fn collect_digests_empty_tree_is_empty() {
        let dir = tempdir().expect("tempdir");
        let include_ext = vec!["html".to_string()];
        let digests = collect_digests(dir.path(), IndexStyle::TrailingSlash, &include_ext)
            .expect("collect digests");
        assert!(digests.is_empty());
    }

    #[test]
    fn collect_digests_detects_url_key_collision() {
        let dir = tempdir().expect("tempdir");
        let root = dir.path();
        // Literal space encodes to %20; a filename that already contains %20
        // is left as-is for that segment and collides with the encoded form.
        fs::write(root.join("hello world.html"), b"a").expect("write spaced name");
        fs::write(root.join("hello%20world.html"), b"b").expect("write pre-encoded name");

        let include_ext = vec!["html".to_string()];
        let result = collect_digests(root, IndexStyle::File, &include_ext);
        assert!(result.is_err());
        let message = format!("{:#}", result.unwrap_err());
        assert!(
            message.contains("duplicate URL key"),
            "unexpected error: {message}"
        );
    }

    #[test]
    fn normalize_prefixes_validates_sorts_and_dedupes() {
        assert!(normalize_prefixes(&[]).is_err());
        assert!(normalize_prefixes(&["blog".to_string()]).is_err());

        let sorted = normalize_prefixes(&[
            "/docs/".to_string(),
            "/blog/".to_string(),
            "/blog/".to_string(),
        ])
        .expect("normalize");
        assert_eq!(sorted, vec!["/blog/", "/docs/"]);
    }

    #[cfg(unix)]
    #[test]
    fn collect_digests_fails_on_unreadable_subdirectory() {
        use std::os::unix::fs::PermissionsExt;

        let dir = tempdir().expect("tempdir");
        let root = dir.path();
        let blocked = root.join("blocked");
        fs::create_dir(&blocked).expect("create blocked dir");
        fs::write(blocked.join("secret.html"), b"nope").expect("write secret");
        fs::set_permissions(&blocked, fs::Permissions::from_mode(0o644))
            .expect("remove traverse permission");

        let include_ext = vec!["html".to_string()];
        let result = collect_digests(root, IndexStyle::TrailingSlash, &include_ext);
        assert!(result.is_err());
    }
}
