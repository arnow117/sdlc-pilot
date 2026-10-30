#!/usr/bin/env python3
"""Recall and safely refresh the bundled Hallmark theme catalog.

The catalog is imported data, not instructions.  This helper only reads its
theme metadata and Markdown as text; it never evaluates upstream content.
"""

from __future__ import annotations

import argparse
import base64
import contextlib
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Any, Callable, Iterator
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


SCHEMA_VERSION = 1
UPSTREAM_REPOSITORY = "Nutlope/hallmark"
UPSTREAM_WEB = "https://github.com/Nutlope/hallmark"
OFFICIAL_PREVIEW_ROOT = "https://www.usehallmark.com/themes"
DEFAULT_API_BASE_URL = "https://api.github.com"
THEME_INDEX_PATH = "skills/hallmark/references/themes/index.json"
LICENSE_PATH = "LICENSE"
MAX_INDEX_BYTES = 256 * 1024
MAX_THEME_BYTES = 64 * 1024
MAX_LICENSE_BYTES = 64 * 1024
MAX_TREE_BYTES = 4 * 1024 * 1024
DEFAULT_STALENESS_HOURS = 24
MIN_CONFIDENT_MATCH_SCORE = 6

SCRIPT_PATH = Path(__file__).resolve()
SKILL_ROOT = SCRIPT_PATH.parent.parent
BUNDLED_CATALOG_PATH = SKILL_ROOT / "assets" / "hallmark" / "catalog.json"
BUNDLED_ALIASES_PATH = SKILL_ROOT / "assets" / "hallmark" / "aliases.json"


class CatalogError(RuntimeError):
    """A catalog is invalid, unavailable, or unsafe to replace."""


def canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def snapshot_digest(snapshot: dict[str, Any]) -> str:
    payload = dict(snapshot)
    payload.pop("snapshot_sha256", None)
    return hashlib.sha256(canonical_json(payload)).hexdigest()


def git_blob_sha(content: str) -> str:
    encoded = content.encode("utf-8")
    header = f"blob {len(encoded)}\0".encode("ascii")
    return hashlib.sha1(header + encoded).hexdigest()


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def safe_relative_path(path: str) -> bool:
    parts = Path(path).parts
    return bool(path) and not Path(path).is_absolute() and ".." not in parts


def required_theme_path(slug: str) -> str:
    return f"skills/hallmark/references/themes/{slug}.md"


def source_url(revision: str, path: str) -> str:
    return f"{UPSTREAM_WEB}/blob/{revision}/{path}"


def preview_url(slug: str) -> str:
    return f"{OFFICIAL_PREVIEW_ROOT}/{slug}/"


def parse_json_content(content: str, description: str) -> Any:
    try:
        return json.loads(content)
    except json.JSONDecodeError as error:
        raise CatalogError(f"{description} is not valid JSON: {error.msg}") from error


def validate_theme_index(index: Any) -> list[dict[str, Any]]:
    if not isinstance(index, dict) or set(index) != {"themes"}:
        raise CatalogError("theme index must contain only a themes array")

    themes = index["themes"]
    if not isinstance(themes, list) or not themes:
        raise CatalogError("theme index must contain at least one theme")

    seen_slugs: set[str] = set()
    validated: list[dict[str, Any]] = []
    for theme in themes:
        if not isinstance(theme, dict):
            raise CatalogError("theme index entries must be objects")
        slug = theme.get("slug")
        name = theme.get("name")
        genre = theme.get("genre")
        posture = theme.get("posture")
        keywords = theme.get("keywords")
        material = theme.get("material")
        expected_path = required_theme_path(slug) if isinstance(slug, str) else ""
        if not isinstance(slug, str) or not re.fullmatch(r"[a-z0-9-]+", slug):
            raise CatalogError("theme slug must contain lowercase letters, digits, or hyphens")
        if slug in seen_slugs:
            raise CatalogError(f"theme index duplicates slug: {slug}")
        if not isinstance(name, str) or not name.strip():
            raise CatalogError(f"theme {slug} is missing a name")
        if not isinstance(genre, str) or not genre.strip():
            raise CatalogError(f"theme {slug} is missing a genre")
        if not isinstance(posture, str) or not posture.strip():
            raise CatalogError(f"theme {slug} is missing a posture")
        if not isinstance(keywords, list) or not all(
            isinstance(keyword, str) and keyword.strip() for keyword in keywords
        ):
            raise CatalogError(f"theme {slug} has invalid keywords")
        if not isinstance(material, str) or not material.strip():
            raise CatalogError(f"theme {slug} is missing its material summary")
        if theme.get("file") != f"references/themes/{slug}.md":
            raise CatalogError(f"theme {slug} has an unsupported document path")
        if not safe_relative_path(expected_path):
            raise CatalogError(f"theme {slug} resolved to an unsafe document path")
        seen_slugs.add(slug)
        validated.append(theme)
    return validated


def validate_file_record(path: str, record: Any, maximum_bytes: int) -> None:
    if not isinstance(record, dict) or set(record) != {"sha", "content"}:
        raise CatalogError(f"{path} must contain only sha and content")
    content = record["content"]
    sha = record["sha"]
    if not isinstance(content, str) or not isinstance(sha, str):
        raise CatalogError(f"{path} has invalid content or blob hash")
    if len(content.encode("utf-8")) > maximum_bytes:
        raise CatalogError(f"{path} exceeds its size limit")
    if not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise CatalogError(f"{path} has an invalid Git blob hash")
    if git_blob_sha(content) != sha:
        raise CatalogError(f"{path} differs from its recorded Git blob hash")


def validate_catalog(snapshot: Any) -> dict[str, Any]:
    if not isinstance(snapshot, dict):
        raise CatalogError("catalog snapshot must be a JSON object")
    required_keys = {
        "schema_version",
        "upstream",
        "files",
        "snapshot_sha256",
    }
    if set(snapshot) != required_keys:
        raise CatalogError("catalog snapshot has unexpected top-level fields")
    if snapshot["schema_version"] != SCHEMA_VERSION:
        raise CatalogError("catalog schema version is unsupported")
    if not isinstance(snapshot["snapshot_sha256"], str):
        raise CatalogError("catalog snapshot is missing its integrity hash")
    if snapshot_digest(snapshot) != snapshot["snapshot_sha256"]:
        raise CatalogError("catalog snapshot differs from its recorded baseline hash")

    upstream = snapshot["upstream"]
    if not isinstance(upstream, dict) or set(upstream) != {
        "repository",
        "ref",
        "revision",
        "fetched_at",
    }:
        raise CatalogError("catalog upstream provenance is invalid")
    if upstream["repository"] != UPSTREAM_REPOSITORY or upstream["ref"] != "main":
        raise CatalogError("catalog must retain the approved Hallmark upstream")
    if not isinstance(upstream["revision"], str) or not re.fullmatch(
        r"[0-9a-f]{40}", upstream["revision"]
    ):
        raise CatalogError("catalog upstream revision is invalid")
    if not isinstance(upstream["fetched_at"], str):
        raise CatalogError("catalog fetched_at provenance is invalid")

    files = snapshot["files"]
    if not isinstance(files, dict):
        raise CatalogError("catalog files must be an object")
    for path in files:
        if not safe_relative_path(path):
            raise CatalogError(f"catalog contains an unsafe path: {path}")
    if LICENSE_PATH not in files or THEME_INDEX_PATH not in files:
        raise CatalogError("catalog must contain the license and theme index")
    validate_file_record(LICENSE_PATH, files[LICENSE_PATH], MAX_LICENSE_BYTES)
    validate_file_record(THEME_INDEX_PATH, files[THEME_INDEX_PATH], MAX_INDEX_BYTES)

    index = parse_json_content(files[THEME_INDEX_PATH]["content"], "theme index")
    themes = validate_theme_index(index)
    expected_paths = {LICENSE_PATH, THEME_INDEX_PATH}
    for theme in themes:
        path = required_theme_path(theme["slug"])
        expected_paths.add(path)
        if path not in files:
            raise CatalogError(f"catalog is missing active theme document: {path}")
        validate_file_record(path, files[path], MAX_THEME_BYTES)

    if set(files) != expected_paths:
        raise CatalogError("catalog contains inactive or unexpected upstream documents")
    return snapshot


def read_catalog_with_digest(path: Path) -> tuple[dict[str, Any], str]:
    try:
        raw = path.read_bytes()
        content = raw.decode("utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise CatalogError(f"cannot read catalog {path}: {error}") from error
    catalog = validate_catalog(parse_json_content(content, f"catalog {path}"))
    return catalog, hashlib.sha256(raw).hexdigest()


def read_catalog(path: Path) -> dict[str, Any]:
    catalog, _ = read_catalog_with_digest(path)
    return catalog


def catalog_file_digest(path: Path) -> str:
    try:
        content = path.read_bytes()
    except OSError as error:
        raise CatalogError(f"cannot read catalog bytes {path}: {error}") from error
    return hashlib.sha256(content).hexdigest()


def make_catalog(
    *,
    revision: str,
    fetched_at: str,
    files: dict[str, dict[str, str]],
) -> dict[str, Any]:
    snapshot: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "upstream": {
            "repository": UPSTREAM_REPOSITORY,
            "ref": "main",
            "revision": revision,
            "fetched_at": fetched_at,
        },
        "files": files,
        "snapshot_sha256": "",
    }
    snapshot["snapshot_sha256"] = snapshot_digest(snapshot)
    return validate_catalog(snapshot)


def build_catalog_from_input(input_path: Path) -> dict[str, Any]:
    """Build a validated immutable snapshot from the supplied pinned input."""
    source = parse_json_content(input_path.read_text(encoding="utf-8"), "upstream input")
    if not isinstance(source, dict) or set(source) != {
        "repository",
        "ref",
        "commit",
        "fetched_at",
        "files",
    }:
        raise CatalogError("upstream input has an unsupported schema")
    if source["repository"] != UPSTREAM_REPOSITORY or source["ref"] != "main":
        raise CatalogError("upstream input is not the approved Hallmark source")
    if not isinstance(source["files"], dict):
        raise CatalogError("upstream input files must be an object")
    files: dict[str, dict[str, str]] = {}
    for path, record in source["files"].items():
        if not isinstance(path, str) or not safe_relative_path(path):
            raise CatalogError("upstream input has an unsafe file path")
        if not isinstance(record, dict) or set(record) != {"sha", "content"}:
            raise CatalogError(f"upstream input record is invalid: {path}")
        files[path] = {"sha": record["sha"], "content": record["content"]}
    return make_catalog(
        revision=source["commit"],
        fetched_at=source["fetched_at"],
        files=files,
    )


def write_atomically(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    file_descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(file_descriptor, "wb") as temporary_file:
            temporary_file.write(content)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
        os.replace(temporary_path, path)
        directory_descriptor = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    except BaseException:
        with contextlib.suppress(FileNotFoundError):
            temporary_path.unlink()
        raise


@contextlib.contextmanager
def catalog_lock(lock_path: Path) -> Iterator[None]:
    """Hold a non-stealing ownership lock for a catalog mutation."""
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as error:
        raise CatalogError(f"catalog is locked by another owner: {lock_path}") from error
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as lock_file:
            lock_file.write(f"pid={os.getpid()} created_at={utc_now()}\n")
            lock_file.flush()
            os.fsync(lock_file.fileno())
        yield
    finally:
        with contextlib.suppress(FileNotFoundError):
            lock_path.unlink()


def request_json(url: str, timeout: float, maximum_bytes: int = MAX_INDEX_BYTES) -> dict[str, Any]:
    request = Request(url, headers={"Accept": "application/vnd.github+json", "User-Agent": "sdlc-prototype"})
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read(maximum_bytes + 1)
    except (HTTPError, URLError, TimeoutError, OSError) as error:
        raise CatalogError(f"upstream request failed for {url}: {error}") from error
    if len(raw) > maximum_bytes:
        raise CatalogError(f"upstream response exceeded the JSON size limit: {url}")
    value = parse_json_content(raw.decode("utf-8"), f"upstream response {url}")
    if not isinstance(value, dict):
        raise CatalogError(f"upstream response must be a JSON object: {url}")
    return value


def api_url(api_base_url: str, suffix: str) -> str:
    base = api_base_url.rstrip("/")
    if not base.startswith(("https://", "http://")):
        raise CatalogError("api base URL must use HTTP(S)")
    return f"{base}/repos/{UPSTREAM_REPOSITORY}/{suffix.lstrip('/')}"


def resolve_revision(api_base_url: str, timeout: float) -> str:
    commit = request_json(api_url(api_base_url, "commits/main"), timeout)
    revision = commit.get("sha")
    if not isinstance(revision, str) or not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise CatalogError("upstream main did not resolve to a full commit SHA")
    return revision


def fetch_tree(api_base_url: str, revision: str, timeout: float) -> dict[str, dict[str, Any]]:
    payload = request_json(
        api_url(api_base_url, f"git/trees/{revision}?recursive=1"),
        timeout,
        MAX_TREE_BYTES,
    )
    if payload.get("truncated"):
        raise CatalogError("upstream tree was truncated")
    entries = payload.get("tree")
    if not isinstance(entries, list):
        raise CatalogError("upstream tree is missing its entries")

    tree: dict[str, dict[str, Any]] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            raise CatalogError("upstream tree contains an invalid entry")
        path = entry.get("path")
        sha = entry.get("sha")
        size = entry.get("size")
        if not isinstance(path, str) or not safe_relative_path(path):
            raise CatalogError("upstream tree contains an unsafe path")
        if entry.get("type") != "blob" or not isinstance(sha, str) or not re.fullmatch(
            r"[0-9a-f]{40}", sha
        ):
            continue
        if not isinstance(size, int) or size < 0:
            raise CatalogError(f"upstream tree has an invalid blob size: {path}")
        tree[path] = {"sha": sha, "size": size}
    return tree


def max_size_for_path(path: str) -> int:
    if path == LICENSE_PATH:
        return MAX_LICENSE_BYTES
    if path == THEME_INDEX_PATH:
        return MAX_INDEX_BYTES
    return MAX_THEME_BYTES


def fetch_blob(
    api_base_url: str,
    tree: dict[str, dict[str, Any]],
    path: str,
    timeout: float,
) -> dict[str, str]:
    if path not in tree:
        raise CatalogError(f"upstream tree is missing required file: {path}")
    metadata = tree[path]
    if metadata["size"] > max_size_for_path(path):
        raise CatalogError(f"upstream file exceeds its size limit: {path}")
    payload = request_json(api_url(api_base_url, f"git/blobs/{metadata['sha']}"), timeout)
    if payload.get("encoding") != "base64" or not isinstance(payload.get("content"), str):
        raise CatalogError(f"upstream blob has unsupported encoding: {path}")
    try:
        encoded_content = payload["content"].replace("\n", "").replace("\r", "")
        raw = base64.b64decode(encoded_content, validate=True)
        content = raw.decode("utf-8")
    except (ValueError, UnicodeDecodeError) as error:
        raise CatalogError(f"upstream blob is not UTF-8 text: {path}") from error
    if len(raw) > max_size_for_path(path):
        raise CatalogError(f"upstream file exceeds its size limit: {path}")
    if git_blob_sha(content) != metadata["sha"]:
        raise CatalogError(f"upstream blob hash did not match its tree entry: {path}")
    return {"sha": metadata["sha"], "content": content}


def reuse_or_fetch_file(
    *,
    path: str,
    current_files: dict[str, dict[str, str]],
    tree: dict[str, dict[str, Any]],
    api_base_url: str,
    timeout: float,
    fetched_paths: list[str],
) -> dict[str, str]:
    current = current_files.get(path)
    if current is not None and path in tree and current["sha"] == tree[path]["sha"]:
        return current
    record = fetch_blob(api_base_url, tree, path, timeout)
    fetched_paths.append(path)
    return record


def prepare_updated_catalog(
    current: dict[str, Any],
    *,
    api_base_url: str,
    timeout: float,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Download and fully validate a candidate without changing local files."""
    revision = resolve_revision(api_base_url, timeout)
    tree = fetch_tree(api_base_url, revision, timeout)
    current_files = current["files"]
    fetched_paths: list[str] = []

    index_record = reuse_or_fetch_file(
        path=THEME_INDEX_PATH,
        current_files=current_files,
        tree=tree,
        api_base_url=api_base_url,
        timeout=timeout,
        fetched_paths=fetched_paths,
    )
    index = parse_json_content(index_record["content"], "upstream theme index")
    themes = validate_theme_index(index)

    next_files: dict[str, dict[str, str]] = {
        LICENSE_PATH: reuse_or_fetch_file(
            path=LICENSE_PATH,
            current_files=current_files,
            tree=tree,
            api_base_url=api_base_url,
            timeout=timeout,
            fetched_paths=fetched_paths,
        ),
        THEME_INDEX_PATH: index_record,
    }
    for theme in themes:
        path = required_theme_path(theme["slug"])
        next_files[path] = reuse_or_fetch_file(
            path=path,
            current_files=current_files,
            tree=tree,
            api_base_url=api_base_url,
            timeout=timeout,
            fetched_paths=fetched_paths,
        )

    if revision == current["upstream"]["revision"] and next_files == current_files:
        candidate = current
    else:
        candidate = make_catalog(
            revision=revision,
            fetched_at=utc_now(),
            files=next_files,
        )
    old_themes = {
        theme["slug"]: theme
        for theme in validate_theme_index(
            parse_json_content(current_files[THEME_INDEX_PATH]["content"], "current theme index")
        )
    }
    new_themes = {theme["slug"]: theme for theme in themes}
    added = sorted(set(new_themes) - set(old_themes))
    removed = sorted(set(old_themes) - set(new_themes))
    updated = sorted(
        slug
        for slug in set(new_themes) & set(old_themes)
        if (
            new_themes[slug] != old_themes[slug]
            or next_files[required_theme_path(slug)]["sha"]
            != current_files[required_theme_path(slug)]["sha"]
        )
    )
    unchanged = sorted(
        slug
        for slug in set(new_themes) & set(old_themes)
        if slug not in updated
    )
    return candidate, {
        "source_revision": revision,
        "added": added,
        "updated": updated,
        "removed": removed,
        "unchanged": unchanged,
        "fetched_paths": fetched_paths,
    }


def cache_catalog_path(cache_dir: Path) -> Path:
    return cache_dir / "hallmark-catalog.json"


def cache_status_path(cache_dir: Path) -> Path:
    return cache_dir / "hallmark-refresh-status.json"


def catalog_lock_path(target_path: Path) -> Path:
    """Return the one ownership lock path for a normalized catalog target."""
    normalized_target = target_path.expanduser().resolve()
    return normalized_target.with_name(f".{normalized_target.name}.lock")


def read_cache_status(cache_dir: Path) -> dict[str, Any] | None:
    path = cache_status_path(cache_dir)
    if not path.exists():
        return None
    try:
        value = parse_json_content(path.read_text(encoding="utf-8"), "refresh status")
    except OSError as error:
        raise CatalogError(f"cannot read refresh status {path}: {error}") from error
    if not isinstance(value, dict) or set(value) != {
        "checked_at",
        "revision",
        "snapshot_sha256",
    }:
        raise CatalogError("refresh status has an unsupported schema")
    if not isinstance(value["checked_at"], str):
        raise CatalogError("refresh status has an invalid check time")
    if not isinstance(value["revision"], str) or not re.fullmatch(r"[0-9a-f]{40}", value["revision"]):
        raise CatalogError("refresh status has an invalid revision")
    if not isinstance(value["snapshot_sha256"], str) or not re.fullmatch(
        r"[0-9a-f]{64}", value["snapshot_sha256"]
    ):
        raise CatalogError("refresh status has an invalid snapshot hash")
    return value


def cached_or_bundled_catalog(
    cache_dir: Path | None,
    bundled_path: Path,
) -> tuple[dict[str, Any], Path, list[str]]:
    if cache_dir is not None:
        cached_path = cache_catalog_path(cache_dir)
        if cached_path.exists():
            try:
                return read_catalog(cached_path), cached_path, []
            except CatalogError as error:
                bundled_catalog = read_catalog(bundled_path)
                warning = (
                    f"Cached catalog is invalid and was not modified; using bundled catalog instead: {error}"
                )
                return bundled_catalog, bundled_path, [warning]
    return read_catalog(bundled_path), bundled_path, []


def write_refresh_status(cache_dir: Path, catalog: dict[str, Any]) -> None:
    status = {
        "checked_at": utc_now(),
        "revision": catalog["upstream"]["revision"],
        "snapshot_sha256": catalog["snapshot_sha256"],
    }
    write_atomically(cache_status_path(cache_dir), canonical_json(status) + b"\n")


def refresh_catalog(
    *,
    target_path: Path,
    base_catalog_path: Path,
    api_base_url: str,
    timeout: float,
    cache_dir: Path | None = None,
    before_replace: Callable[[], None] | None = None,
) -> dict[str, Any]:
    """Synchronize one cache or explicit bundled target, preserving prior bytes on failure."""
    current = read_catalog(target_path if target_path.exists() else base_catalog_path)
    lock_path = catalog_lock_path(target_path)
    with catalog_lock(lock_path):
        original_target_digest: str | None = None
        if target_path.exists():
            current, original_target_digest = read_catalog_with_digest(target_path)
        candidate, summary = prepare_updated_catalog(
            current,
            api_base_url=api_base_url,
            timeout=timeout,
        )
        changed = candidate["snapshot_sha256"] != current["snapshot_sha256"]
        if changed:
            if before_replace is not None:
                before_replace()
            target_still_exists = target_path.exists()
            latest_target_digest = (
                catalog_file_digest(target_path) if target_still_exists else None
            )
            if latest_target_digest != original_target_digest:
                raise CatalogError("catalog changed during refresh; refusing to overwrite local edits")
            write_atomically(target_path, canonical_json(candidate) + b"\n")
        if cache_dir is not None:
            write_refresh_status(cache_dir, candidate)
        return {"changed": changed, **summary}


def normalize_text(value: str) -> str:
    lowered = value.casefold().replace("_", " ").replace("-", " ")
    return re.sub(r"\s+", " ", lowered).strip()


def read_aliases(path: Path) -> dict[str, list[str]]:
    try:
        value = parse_json_content(path.read_text(encoding="utf-8"), "local aliases")
    except OSError as error:
        raise CatalogError(f"cannot read local aliases {path}: {error}") from error
    if not isinstance(value, dict) or set(value) != {"schema_version", "aliases"}:
        raise CatalogError("local aliases have an unsupported schema")
    if value["schema_version"] != 1 or not isinstance(value["aliases"], dict):
        raise CatalogError("local aliases have an unsupported version")
    aliases: dict[str, list[str]] = {}
    for phrase, terms in value["aliases"].items():
        if not isinstance(phrase, str) or not isinstance(terms, list):
            raise CatalogError("local aliases have invalid entries")
        if not all(isinstance(term, str) and term.strip() for term in terms):
            raise CatalogError("local aliases have invalid English expansion terms")
        aliases[normalize_text(phrase)] = [normalize_text(term) for term in terms]
    return aliases


def query_terms(query: str, aliases: dict[str, list[str]]) -> tuple[str, list[str]]:
    normalized = normalize_text(query)
    terms = set(re.findall(r"[a-z0-9]+", normalized))
    for phrase, expansion in aliases.items():
        if phrase and phrase in normalized:
            terms.update(expansion)
    return normalized, sorted(terms)


def candidate_score(
    *,
    theme: dict[str, Any],
    normalized_query: str,
    terms: list[str],
) -> tuple[int, list[str]]:
    keyword_phrases = [normalize_text(keyword) for keyword in theme["keywords"]]
    matches: list[str] = []
    score = 0
    for keyword in keyword_phrases:
        if keyword in normalized_query:
            score += 8 if " " in keyword else 4
            matches.append(keyword)
    for term in terms:
        if term in keyword_phrases and term not in matches:
            score += 3
            matches.append(term)
        else:
            normalized_matches = [
                keyword
                for keyword in keyword_phrases
                if len(term) > 3
                and len(keyword) > 3
                and keyword.rstrip("s") == term.rstrip("s")
            ]
            normalized_match = normalized_matches[0] if normalized_matches else None
            if normalized_match is not None and normalized_match not in matches:
                score += 3
                matches.append(normalized_match)
    for metadata_name in ("genre", "posture"):
        metadata_term = normalize_text(theme[metadata_name])
        if metadata_term in terms:
            score += 1
            matches.append(f"{metadata_name}:{metadata_term}")
    if normalize_text(theme["slug"]) in normalized_query:
        score += 12
        matches.append(theme["slug"])
    return score, sorted(set(matches))


def recall_themes(
    catalog: dict[str, Any],
    *,
    brief: str,
    aliases: dict[str, list[str]],
    limit: int = 3,
) -> dict[str, Any]:
    if limit != 3:
        raise CatalogError("style recall always returns exactly three candidates")
    index = parse_json_content(catalog["files"][THEME_INDEX_PATH]["content"], "theme index")
    themes = validate_theme_index(index)
    normalized_query, terms = query_terms(brief, aliases)
    ranked: list[tuple[int, str, dict[str, Any], list[str]]] = []
    for theme in themes:
        score, matches = candidate_score(
            theme=theme,
            normalized_query=normalized_query,
            terms=terms,
        )
        tie_breaker = hashlib.sha256(
            f"{normalized_query}\0{theme['slug']}".encode("utf-8")
        ).hexdigest()
        ranked.append((score, tie_breaker, theme, matches))
    ranked.sort(key=lambda item: (-item[0], item[1], item[2]["name"]))

    revision = catalog["upstream"]["revision"]
    candidates = []
    for score, _, theme, matches in ranked[:limit]:
        path = required_theme_path(theme["slug"])
        candidates.append(
            {
                "name": theme["name"],
                "slug": theme["slug"],
                "genre": theme["genre"],
                "posture": theme["posture"],
                "matched_terms": matches,
                "match_score": score,
                "material": theme["material"],
                "official_preview_url": preview_url(theme["slug"]),
                "pinned_source_url": source_url(revision, path),
                "source_revision": revision,
            }
        )
    highest_score = candidates[0]["match_score"] if candidates else 0
    evidence_status = (
        "matched" if highest_score >= MIN_CONFIDENT_MATCH_SCORE else "insufficient"
    )
    evidence_warning = None
    if evidence_status == "insufficient":
        evidence_warning = (
            "Catalog vocabulary evidence is weak or absent. Stable hash ordering only breaks ties; "
            "it is not semantic matching. Expand the known brief into English catalog scenario and "
            "visual terms, then recall again before presenting unrelated candidates."
        )
    return {
        "catalog": {
            "repository": catalog["upstream"]["repository"],
            "revision": revision,
            "snapshot_sha256": catalog["snapshot_sha256"],
        },
        "query": {
            "brief": brief,
            "expanded_terms": terms,
        },
        "ranking_note": (
            "Lexical matching against validated keywords plus genre/posture metadata and local bilingual "
            "aliases. Stable hashes only make equal scores deterministic; they are not semantic evidence."
        ),
        "evidence_status": evidence_status,
        "evidence_warning": evidence_warning,
        "candidates": candidates,
    }


def markdown_recall(result: dict[str, Any]) -> str:
    lines = [
        "Hallmark 风格候选（词汇匹配辅助，最终选择仍需结合产品判断）：",
        "",
    ]
    for warning in result.get("catalog_warnings", []):
        lines.extend([f"目录警告：{warning}", ""])
    if result["evidence_warning"]:
        lines.extend(
            [
                f"证据不足：{result['evidence_warning']}",
                "",
            ]
        )
    for position, candidate in enumerate(result["candidates"], start=1):
        matched_terms = ", ".join(candidate["matched_terms"]) or "未命中目录词汇；不把同分排序当作语义推荐"
        lines.extend(
            [
                f"{position}. {candidate['name']}（{candidate['genre']} / {candidate['posture']}）",
                f"   - 匹配：{matched_terms}",
                f"   - 材质：{candidate['material']}",
                f"   - 官方预览：{candidate['official_preview_url']}",
                f"   - 固定源码：{candidate['pinned_source_url']}（{candidate['source_revision']}）",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def selected_cache_status(
    catalog: dict[str, Any],
    cache_dir: Path | None,
) -> tuple[dict[str, Any] | None, list[str]]:
    if cache_dir is None:
        return None, []
    try:
        status = read_cache_status(cache_dir)
    except CatalogError as error:
        return None, [f"Refresh status is invalid and is treated as stale: {error}"]
    if status is None:
        return None, []
    if (
        status["revision"] != catalog["upstream"]["revision"]
        or status["snapshot_sha256"] != catalog["snapshot_sha256"]
    ):
        return None, ["Refresh status does not belong to the selected catalog and is treated as stale."]
    return status, []


def catalog_status(
    catalog: dict[str, Any],
    cache_dir: Path | None,
    *,
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    status, status_warnings = selected_cache_status(catalog, cache_dir)
    all_warnings = list(warnings or []) + status_warnings
    now = dt.datetime.now(dt.timezone.utc)
    stale = True
    if status is not None:
        try:
            checked_at = dt.datetime.fromisoformat(status["checked_at"])
            if checked_at.tzinfo is None:
                raise ValueError("refresh status is missing a time zone")
            stale = now - checked_at > dt.timedelta(hours=DEFAULT_STALENESS_HOURS)
        except (TypeError, ValueError):
            stale = True
            all_warnings.append("Refresh status check time is invalid and is treated as stale.")
    return {
        "revision": catalog["upstream"]["revision"],
        "fetched_at": catalog["upstream"]["fetched_at"],
        "snapshot_sha256": catalog["snapshot_sha256"],
        "theme_count": len(
            parse_json_content(catalog["files"][THEME_INDEX_PATH]["content"], "theme index")["themes"]
        ),
        "cache_status": status,
        "check_due": stale,
        "staleness_hours": DEFAULT_STALENESS_HOURS,
        "warnings": all_warnings,
    }


def command_status(args: argparse.Namespace) -> dict[str, Any]:
    catalog, selected_path, warnings = cached_or_bundled_catalog(args.cache_dir, args.catalog)
    return {
        "catalog_path": str(selected_path),
        **catalog_status(catalog, args.cache_dir, warnings=warnings),
    }


def command_check(args: argparse.Namespace) -> dict[str, Any]:
    catalog, selected_path, warnings = cached_or_bundled_catalog(args.cache_dir, args.catalog)
    _, freshness_warnings = selected_cache_status(catalog, args.cache_dir)
    remote_revision = resolve_revision(args.api_base_url, args.timeout)
    return {
        "catalog_path": str(selected_path),
        "current_revision": catalog["upstream"]["revision"],
        "remote_revision": remote_revision,
        "update_available": remote_revision != catalog["upstream"]["revision"],
        "mutated": False,
        "warnings": warnings + freshness_warnings,
    }


def command_update(args: argparse.Namespace) -> dict[str, Any]:
    if args.cache_dir is None and not args.allow_bundled_write:
        raise CatalogError(
            "update requires --cache-dir, or --allow-bundled-write with an explicit --catalog target"
        )
    if args.cache_dir is not None:
        target_path = cache_catalog_path(args.cache_dir)
        base_catalog_path = args.catalog
    else:
        target_path = args.catalog
        base_catalog_path = args.catalog
        if target_path == BUNDLED_CATALOG_PATH and not args.allow_bundled_write:
            raise CatalogError("writing the bundled catalog requires --allow-bundled-write")
    summary = refresh_catalog(
        target_path=target_path,
        base_catalog_path=base_catalog_path,
        api_base_url=args.api_base_url,
        timeout=args.timeout,
        cache_dir=args.cache_dir,
    )
    return {"target_path": str(target_path), **summary}


def command_recall(args: argparse.Namespace) -> dict[str, Any] | str:
    catalog, _, warnings = cached_or_bundled_catalog(args.cache_dir, args.catalog)
    _, freshness_warnings = selected_cache_status(catalog, args.cache_dir)
    aliases = read_aliases(args.aliases)
    result = recall_themes(catalog, brief=args.brief, aliases=aliases)
    result["catalog_warnings"] = warnings + freshness_warnings
    return markdown_recall(result) if args.format == "markdown" else result


def command_show(args: argparse.Namespace) -> dict[str, Any]:
    catalog, _, warnings = cached_or_bundled_catalog(args.cache_dir, args.catalog)
    _, freshness_warnings = selected_cache_status(catalog, args.cache_dir)
    index = parse_json_content(catalog["files"][THEME_INDEX_PATH]["content"], "theme index")
    themes = {theme["slug"]: theme for theme in validate_theme_index(index)}
    if args.theme not in themes:
        raise CatalogError(f"unknown Hallmark theme: {args.theme}")
    theme = themes[args.theme]
    path = required_theme_path(args.theme)
    return {
        "theme": theme,
        "document": catalog["files"][path]["content"],
        "official_preview_url": preview_url(args.theme),
        "pinned_source_url": source_url(catalog["upstream"]["revision"], path),
        "source_revision": catalog["upstream"]["revision"],
        "warnings": warnings + freshness_warnings,
    }


def command_bundle(args: argparse.Namespace) -> dict[str, Any]:
    snapshot = build_catalog_from_input(args.input)
    write_atomically(args.output, canonical_json(snapshot) + b"\n")
    return {
        "output": str(args.output),
        "revision": snapshot["upstream"]["revision"],
        "theme_count": len(
            parse_json_content(snapshot["files"][THEME_INDEX_PATH]["content"], "theme index")["themes"]
        ),
        "snapshot_sha256": snapshot["snapshot_sha256"],
    }


def path_argument(value: str) -> Path:
    return Path(value).expanduser().resolve()


def add_catalog_arguments(parser: argparse.ArgumentParser, *, include_aliases: bool = False) -> None:
    parser.add_argument(
        "--catalog",
        type=path_argument,
        default=BUNDLED_CATALOG_PATH,
        help="bundled catalog or an explicit maintainer target",
    )
    parser.add_argument(
        "--cache-dir",
        type=path_argument,
        help="explicit prototype/workspace cache directory; never defaults to an installed package",
    )
    if include_aliases:
        parser.add_argument(
            "--aliases",
            type=path_argument,
            default=BUNDLED_ALIASES_PATH,
            help="local bilingual aliases kept separate from imported upstream data",
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    status_parser = subparsers.add_parser("status", help="read local catalog and cache status")
    add_catalog_arguments(status_parser)
    status_parser.set_defaults(handler=command_status)

    check_parser = subparsers.add_parser("check", help="read upstream revision without writing a snapshot")
    add_catalog_arguments(check_parser)
    check_parser.add_argument("--api-base-url", default=DEFAULT_API_BASE_URL)
    check_parser.add_argument("--timeout", type=float, default=10.0)
    check_parser.set_defaults(handler=command_check)

    update_parser = subparsers.add_parser("update", help="atomically refresh an explicit cache or bundled target")
    add_catalog_arguments(update_parser)
    update_parser.add_argument("--allow-bundled-write", action="store_true")
    update_parser.add_argument("--api-base-url", default=DEFAULT_API_BASE_URL)
    update_parser.add_argument("--timeout", type=float, default=10.0)
    update_parser.set_defaults(handler=command_update)

    recall_parser = subparsers.add_parser("recall", help="return three scenario-matched theme candidates")
    add_catalog_arguments(recall_parser, include_aliases=True)
    recall_parser.add_argument("--brief", required=True)
    recall_parser.add_argument("--format", choices=("json", "markdown"), default="json")
    recall_parser.set_defaults(handler=command_recall)

    show_parser = subparsers.add_parser("show", help="read one validated imported theme document")
    add_catalog_arguments(show_parser)
    show_parser.add_argument("--theme", required=True)
    show_parser.set_defaults(handler=command_show)

    bundle_parser = subparsers.add_parser("bundle", help="build a bundled snapshot from a pinned input file")
    bundle_parser.add_argument("--input", type=path_argument, required=True)
    bundle_parser.add_argument("--output", type=path_argument, required=True)
    bundle_parser.set_defaults(handler=command_bundle)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        result = args.handler(args)
    except CatalogError as error:
        parser.exit(2, f"error: {error}\n")
    if isinstance(result, str):
        print(result, end="")
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
