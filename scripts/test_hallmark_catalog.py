#!/usr/bin/env python3
"""Behavioral tests for the bundled Hallmark catalog helper."""

from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest import mock
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parent.parent
HELPER_PATH = ROOT / "skills" / "sdlc-prototype" / "scripts" / "hallmark_catalog.py"
HELPER_SPEC = importlib.util.spec_from_file_location("hallmark_catalog", HELPER_PATH)
assert HELPER_SPEC is not None and HELPER_SPEC.loader is not None
catalog_helper = importlib.util.module_from_spec(HELPER_SPEC)
sys.modules[HELPER_SPEC.name] = catalog_helper
HELPER_SPEC.loader.exec_module(catalog_helper)


def git_blob_sha(content: str) -> str:
    encoded = content.encode("utf-8")
    return hashlib.sha1(f"blob {len(encoded)}\0".encode("ascii") + encoded).hexdigest()


def theme_entry(slug: str, keywords: list[str], material: str = "paper, ink, and a deliberate component rhythm") -> dict[str, object]:
    return {
        "name": slug.title(),
        "slug": slug,
        "genre": "modern-minimal",
        "posture": "restrained",
        "keywords": keywords,
        "material": material,
        "file": f"references/themes/{slug}.md",
    }


def theme_document(theme: dict[str, object], suffix: str = "") -> str:
    return (
        f"---\nname: {theme['name']}\nslug: {theme['slug']}\n---\n\n"
        f"# {theme['name']}\n\nImported reference text.{suffix}\n"
    )


def remote_files(themes: list[dict[str, object]], document_suffixes: dict[str, str] | None = None) -> dict[str, str]:
    document_suffixes = document_suffixes or {}
    index = json.dumps({"themes": themes}, ensure_ascii=False, separators=(",", ":"))
    files = {
        catalog_helper.LICENSE_PATH: "MIT License\n",
        catalog_helper.THEME_INDEX_PATH: index,
    }
    for theme in themes:
        slug = str(theme["slug"])
        files[catalog_helper.required_theme_path(slug)] = theme_document(
            theme,
            document_suffixes.get(slug, ""),
        )
    return files


class FakeGitHub:
    """A local GitHub git-data endpoint with request accounting."""

    def __init__(self) -> None:
        self.revisions: dict[str, dict[str, str]] = {}
        self.head: str | None = None
        self.blobs: dict[str, str] = {}
        self.requests: list[str] = []
        self.fail_blob_hashes: set[str] = set()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), self._handler())
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    @property
    def api_base_url(self) -> str:
        host, port = self.server.server_address
        return f"http://{host}:{port}"

    def close(self) -> None:
        self.server.shutdown()
        self.thread.join(timeout=5)
        self.server.server_close()

    def add_revision(self, revision: str, files: dict[str, str]) -> None:
        self.revisions[revision] = files
        self.head = revision
        for content in files.values():
            self.blobs[git_blob_sha(content)] = content

    def _handler(self):
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, format: str, *args: object) -> None:
                del format, args

            def send_json(self, status: int, value: object) -> None:
                body = json.dumps(value).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
                parsed = urlparse(self.path)
                path = parsed.path
                fake.requests.append(path)
                prefix = f"/repos/{catalog_helper.UPSTREAM_REPOSITORY}/"
                if not path.startswith(prefix) or fake.head is None:
                    self.send_json(404, {"message": "not found"})
                    return
                suffix = path[len(prefix) :]
                if suffix == "commits/main":
                    self.send_json(200, {"sha": fake.head})
                    return
                if suffix.startswith("git/trees/"):
                    revision = suffix.removeprefix("git/trees/")
                    files = fake.revisions.get(revision)
                    if files is None:
                        self.send_json(404, {"message": "unknown revision"})
                        return
                    tree = [
                        {
                            "path": file_path,
                            "type": "blob",
                            "sha": git_blob_sha(content),
                            "size": len(content.encode("utf-8")),
                        }
                        for file_path, content in sorted(files.items())
                    ]
                    self.send_json(200, {"truncated": False, "tree": tree})
                    return
                if suffix.startswith("git/blobs/"):
                    blob_hash = suffix.removeprefix("git/blobs/")
                    if blob_hash in fake.fail_blob_hashes:
                        self.send_json(500, {"message": "simulated network interruption"})
                        return
                    content = fake.blobs.get(blob_hash)
                    if content is None:
                        self.send_json(404, {"message": "unknown blob"})
                        return
                    wrapped = base64.encodebytes(content.encode("utf-8")).decode("ascii")
                    self.send_json(200, {"encoding": "base64", "content": wrapped})
                    return
                self.send_json(404, {"message": "unknown endpoint"})

        return Handler


class CatalogFixture(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = Path(tempfile.mkdtemp(prefix="hallmark-catalog-test."))
        self.addCleanup(shutil.rmtree, self.temporary_directory, ignore_errors=True)
        self.remote = FakeGitHub()
        self.addCleanup(self.remote.close)
        self.alpha = theme_entry("alpha", ["developer", "api", "webhook"])
        self.beta = theme_entry("beta", ["health", "care", "mobile"])
        self.remote.add_revision("1" * 40, remote_files([self.alpha]))
        self.cache_dir = self.temporary_directory / "prototype-cache" / "hallmark"

    def refresh(self, **kwargs: object) -> dict[str, object]:
        return catalog_helper.refresh_catalog(
            target_path=catalog_helper.cache_catalog_path(self.cache_dir),
            base_catalog_path=catalog_helper.BUNDLED_CATALOG_PATH,
            api_base_url=self.remote.api_base_url,
            timeout=2.0,
            cache_dir=self.cache_dir,
            **kwargs,
        )

    def cache_bytes(self) -> bytes:
        return catalog_helper.cache_catalog_path(self.cache_dir).read_bytes()


class BundledCatalogTests(unittest.TestCase):
    def test_bundled_catalog_has_fifty_valid_themes_and_provenance(self) -> None:
        catalog = catalog_helper.read_catalog(catalog_helper.BUNDLED_CATALOG_PATH)
        index = json.loads(catalog["files"][catalog_helper.THEME_INDEX_PATH]["content"])
        self.assertEqual(50, len(index["themes"]))
        self.assertEqual("4f6a46c6dc325d40ab268c93e25c7b96676ebccd", catalog["upstream"]["revision"])
        self.assertIn(catalog_helper.LICENSE_PATH, catalog["files"])

    def test_recall_uses_english_and_chinese_terms_with_three_preview_links(self) -> None:
        catalog = catalog_helper.read_catalog(catalog_helper.BUNDLED_CATALOG_PATH)
        aliases = catalog_helper.read_aliases(catalog_helper.BUNDLED_ALIASES_PATH)
        english = catalog_helper.recall_themes(
            catalog,
            brief="A typed webhook API for backend developers",
            aliases=aliases,
        )
        chinese = catalog_helper.recall_themes(
            catalog,
            brief="面向开发者的 webhook API 平台",
            aliases=aliases,
        )
        healthcare = catalog_helper.recall_themes(
            catalog,
            brief="帮助家庭照顾者管理用药的移动应用",
            aliases=aliases,
        )
        photography = catalog_helper.recall_themes(
            catalog,
            brief="黑白摄影作品集与暗房冲印",
            aliases=aliases,
        )
        family_reading = catalog_helper.recall_themes(
            catalog,
            brief="儿童亲子阅读 App，图书馆借阅，温暖轻松，柔和自然，手机触控",
            aliases=aliases,
        )
        finance_risk = catalog_helper.recall_themes(
            catalog,
            brief="量化交易数据后台，专业金融风控，深色界面，高密度表格，克制",
            aliases=aliases,
        )
        unknown = catalog_helper.recall_themes(
            catalog,
            brief="zzzz unrepresented scenario",
            aliases=aliases,
        )
        self.assertEqual("cobalt", english["candidates"][0]["slug"])
        self.assertEqual("cobalt", chinese["candidates"][0]["slug"])
        self.assertEqual("dose", healthcare["candidates"][0]["slug"])
        self.assertEqual("darkroom", photography["candidates"][0]["slug"])
        self.assertEqual(
            ["hum", "almanac", "ink"],
            [candidate["slug"] for candidate in family_reading["candidates"]],
        )
        self.assertNotIn(
            "dose",
            [candidate["slug"] for candidate in family_reading["candidates"]],
        )
        family_terms = {
            term
            for candidate in family_reading["candidates"]
            for term in candidate["matched_terms"]
        }
        self.assertTrue({"reading", "learning", "library", "lending"} & family_terms)
        self.assertEqual(
            ["console", "dusk", "coral"],
            [candidate["slug"] for candidate in finance_risk["candidates"]],
        )
        finance_terms = {
            term
            for candidate in finance_risk["candidates"]
            for term in candidate["matched_terms"]
        }
        self.assertTrue({"data", "audit", "compliance", "fintech", "tables"} & finance_terms)
        self.assertTrue(all(candidate["match_score"] > 0 for candidate in finance_risk["candidates"]))
        self.assertEqual("insufficient", unknown["evidence_status"])
        self.assertIn("not semantic", unknown["evidence_warning"])
        self.assertTrue(all(candidate["match_score"] == 0 for candidate in unknown["candidates"]))
        for result in (english, chinese, healthcare, photography, family_reading, finance_risk):
            candidates = result["candidates"]
            self.assertEqual(3, len(candidates))
            self.assertEqual(3, len({candidate["slug"] for candidate in candidates}))
            for candidate in candidates:
                self.assertEqual(
                    f"https://www.usehallmark.com/themes/{candidate['slug']}/",
                    candidate["official_preview_url"],
                )
                self.assertIn("/blob/4f6a46c6dc325d40ab268c93e25c7b96676ebccd/", candidate["pinned_source_url"])

    def test_selected_theme_document_can_be_read_from_validated_snapshot(self) -> None:
        catalog = catalog_helper.read_catalog(catalog_helper.BUNDLED_CATALOG_PATH)
        cobalt_path = catalog_helper.required_theme_path("cobalt")
        self.assertIn("# Cobalt", catalog["files"][cobalt_path]["content"])


class SyncCatalogTests(CatalogFixture):
    def run_cli(self, *arguments: str) -> dict[str, object]:
        completed = subprocess.run(
            [sys.executable, str(HELPER_PATH), *arguments],
            check=True,
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        return json.loads(completed.stdout)

    def test_cli_exercises_help_status_recall_show_update_and_check(self) -> None:
        help_result = subprocess.run(
            [sys.executable, str(HELPER_PATH), "--help"],
            check=True,
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        self.assertIn("{status,check,update,recall,show,bundle}", help_result.stdout)

        status = self.run_cli("status")
        self.assertEqual(50, status["theme_count"])
        recall = self.run_cli(
            "recall",
            "--brief",
            "面向开发者的 webhook API 平台",
        )
        self.assertEqual("cobalt", recall["candidates"][0]["slug"])
        selected = self.run_cli("show", "--theme", "cobalt")
        self.assertIn("# Cobalt", selected["document"])

        updated = self.run_cli(
            "update",
            "--cache-dir",
            str(self.cache_dir),
            "--api-base-url",
            self.remote.api_base_url,
        )
        self.assertTrue(updated["changed"])
        cached_bytes_before_check = self.cache_bytes()
        checked = self.run_cli(
            "check",
            "--cache-dir",
            str(self.cache_dir),
            "--api-base-url",
            self.remote.api_base_url,
        )
        self.assertFalse(checked["update_available"])
        self.assertEqual(cached_bytes_before_check, self.cache_bytes())

    def test_add_change_remove_and_idempotent_sync_only_fetches_changed_blobs(self) -> None:
        first = self.refresh()
        self.assertTrue(first["changed"])
        self.assertEqual(["alpha"], first["added"])

        self.remote.requests.clear()
        self.remote.add_revision("2" * 40, remote_files([self.alpha, self.beta]))
        added = self.refresh()
        self.assertTrue(added["changed"])
        self.assertEqual(["beta"], added["added"])
        self.assertEqual([], added["updated"])
        self.assertEqual(
            {
                catalog_helper.THEME_INDEX_PATH,
                catalog_helper.required_theme_path("beta"),
            },
            set(added["fetched_paths"]),
        )
        alpha_blob_path = f"/repos/{catalog_helper.UPSTREAM_REPOSITORY}/git/blobs/" + git_blob_sha(
            self.remote.revisions["2" * 40][catalog_helper.required_theme_path("alpha")]
        )
        self.assertNotIn(alpha_blob_path, self.remote.requests)
        refreshed = catalog_helper.read_catalog(catalog_helper.cache_catalog_path(self.cache_dir))
        self.assertEqual("2" * 40, refreshed["upstream"]["revision"])

        changed_alpha = remote_files([self.alpha, self.beta], {"alpha": " v2"})
        self.remote.add_revision("3" * 40, changed_alpha)
        changed = self.refresh()
        self.assertEqual(["alpha"], changed["updated"])
        self.assertEqual([], changed["added"])

        self.remote.add_revision("4" * 40, remote_files([self.alpha], {"alpha": " v2"}))
        removed = self.refresh()
        self.assertEqual(["beta"], removed["removed"])
        self.assertEqual([], removed["updated"])

        stable_bytes = self.cache_bytes()
        self.remote.requests.clear()
        no_op = self.refresh()
        self.assertFalse(no_op["changed"])
        self.assertEqual([], no_op["fetched_paths"])
        self.assertEqual(stable_bytes, self.cache_bytes())

    def test_metadata_only_change_is_updated_without_downloading_theme_markdown(self) -> None:
        self.refresh()
        self.remote.requests.clear()
        metadata_only_alpha = dict(self.alpha)
        metadata_only_alpha["material"] = "revised paper and ink material summary"
        self.remote.add_revision("b" * 40, remote_files([metadata_only_alpha]))

        summary = self.refresh()

        self.assertTrue(summary["changed"])
        self.assertEqual(["alpha"], summary["updated"])
        self.assertEqual([catalog_helper.THEME_INDEX_PATH], summary["fetched_paths"])
        alpha_blob_path = (
            f"/repos/{catalog_helper.UPSTREAM_REPOSITORY}/git/blobs/"
            + git_blob_sha(self.remote.revisions["b" * 40][catalog_helper.required_theme_path("alpha")])
        )
        self.assertNotIn(alpha_blob_path, self.remote.requests)

    def test_unchanged_update_preserves_snapshot_bytes_and_records_freshness(self) -> None:
        first_checked_at = "2030-01-01T00:00:00+00:00"
        second_checked_at = "2030-01-02T00:00:00+00:00"
        with mock.patch.object(catalog_helper, "utc_now", return_value=first_checked_at):
            self.refresh()
        snapshot_bytes = self.cache_bytes()

        with mock.patch.object(catalog_helper, "utc_now", return_value=second_checked_at):
            summary = self.refresh()

        self.assertFalse(summary["changed"])
        self.assertEqual(snapshot_bytes, self.cache_bytes())
        catalog = catalog_helper.read_catalog(catalog_helper.cache_catalog_path(self.cache_dir))
        freshness = catalog_helper.read_cache_status(self.cache_dir)
        self.assertEqual(second_checked_at, freshness["checked_at"])
        self.assertEqual(catalog["upstream"]["revision"], freshness["revision"])
        self.assertEqual(catalog["snapshot_sha256"], freshness["snapshot_sha256"])

    def test_upstream_base64_wrapping_is_normalized_before_strict_decoding(self) -> None:
        self.remote.add_revision("5" * 40, remote_files([self.alpha], {"alpha": "x" * 4096}))
        summary = self.refresh()
        self.assertTrue(summary["changed"])
        catalog = catalog_helper.read_catalog(catalog_helper.cache_catalog_path(self.cache_dir))
        self.assertIn("x" * 4096, catalog["files"][catalog_helper.required_theme_path("alpha")]["content"])

    def test_malformed_schema_path_traversal_and_oversize_keep_previous_snapshot(self) -> None:
        self.refresh()
        previous = self.cache_bytes()

        unsafe_theme = theme_entry("alpha", ["developer"])
        unsafe_theme["file"] = "references/themes/../../escape.md"
        self.remote.add_revision("6" * 40, remote_files([unsafe_theme]))
        with self.assertRaises(catalog_helper.CatalogError):
            self.refresh()
        self.assertEqual(previous, self.cache_bytes())

        missing_genre = dict(self.alpha)
        missing_genre.pop("genre")
        self.remote.add_revision("c" * 40, remote_files([missing_genre]))
        with self.assertRaises(catalog_helper.CatalogError):
            self.refresh()
        self.assertEqual(previous, self.cache_bytes())

        missing_posture = dict(self.alpha)
        missing_posture.pop("posture")
        self.remote.add_revision("d" * 40, remote_files([missing_posture]))
        with self.assertRaises(catalog_helper.CatalogError):
            self.refresh()
        self.assertEqual(previous, self.cache_bytes())

        oversized = remote_files([self.alpha], {"alpha": "x" * catalog_helper.MAX_THEME_BYTES})
        self.remote.add_revision("7" * 40, oversized)
        with self.assertRaises(catalog_helper.CatalogError):
            self.refresh()
        self.assertEqual(previous, self.cache_bytes())

        malformed = remote_files([self.alpha])
        malformed[catalog_helper.THEME_INDEX_PATH] = "{not-json"
        self.remote.add_revision("8" * 40, malformed)
        with self.assertRaises(catalog_helper.CatalogError):
            self.refresh()
        self.assertEqual(previous, self.cache_bytes())

    def test_partial_network_failure_drift_and_external_edit_preserve_previous_bytes_and_aliases(self) -> None:
        self.refresh()
        aliases_path = self.cache_dir / "aliases.json"
        aliases_path.parent.mkdir(parents=True, exist_ok=True)
        aliases_path.write_text('{"local": "keep"}\n', encoding="utf-8")
        previous = self.cache_bytes()

        changed_files = remote_files([self.alpha], {"alpha": " new"})
        changed_hash = git_blob_sha(changed_files[catalog_helper.required_theme_path("alpha")])
        self.remote.add_revision("9" * 40, changed_files)
        self.remote.fail_blob_hashes.add(changed_hash)
        with self.assertRaises(catalog_helper.CatalogError):
            self.refresh()
        self.assertEqual(previous, self.cache_bytes())
        self.assertEqual('{"local": "keep"}\n', aliases_path.read_text(encoding="utf-8"))
        self.remote.fail_blob_hashes.clear()

        catalog_path = catalog_helper.cache_catalog_path(self.cache_dir)
        catalog_path.write_text("{}\n", encoding="utf-8")
        with self.assertRaises(catalog_helper.CatalogError):
            self.refresh()
        self.assertEqual(b"{}\n", self.cache_bytes())

    def test_invalid_cache_and_freshness_fall_back_without_overwriting_local_bytes(self) -> None:
        self.refresh()
        catalog_path = catalog_helper.cache_catalog_path(self.cache_dir)
        catalog_path.write_text("{}\n", encoding="utf-8")
        invalid_bytes = self.cache_bytes()

        status = self.run_cli("status", "--cache-dir", str(self.cache_dir))
        self.assertEqual(str(catalog_helper.BUNDLED_CATALOG_PATH), status["catalog_path"])
        self.assertTrue(status["check_due"])
        self.assertTrue(any("invalid" in warning.lower() for warning in status["warnings"]))

        checked = self.run_cli(
            "check",
            "--cache-dir",
            str(self.cache_dir),
            "--api-base-url",
            self.remote.api_base_url,
        )
        self.assertTrue(any("invalid" in warning.lower() for warning in checked["warnings"]))
        recall = self.run_cli(
            "recall",
            "--cache-dir",
            str(self.cache_dir),
            "--brief",
            "developer api",
        )
        self.assertTrue(recall["catalog_warnings"])
        shown = self.run_cli("show", "--cache-dir", str(self.cache_dir), "--theme", "cobalt")
        self.assertTrue(shown["warnings"])
        self.assertEqual(invalid_bytes, self.cache_bytes())

        with self.assertRaises(catalog_helper.CatalogError):
            self.refresh()
        self.assertEqual(invalid_bytes, self.cache_bytes())

        bundled_catalog = catalog_helper.read_catalog(catalog_helper.BUNDLED_CATALOG_PATH)
        catalog_path.write_bytes(catalog_helper.canonical_json(bundled_catalog) + b"\n")
        catalog_helper.cache_status_path(self.cache_dir).write_text("not-json\n", encoding="utf-8")
        malformed_status = self.run_cli("status", "--cache-dir", str(self.cache_dir))
        self.assertTrue(malformed_status["check_due"])
        self.assertTrue(any("status" in warning.lower() for warning in malformed_status["warnings"]))

    def test_foreign_lock_interruption_and_compare_before_replace_preserve_snapshot(self) -> None:
        self.refresh()
        previous = self.cache_bytes()
        target_path = catalog_helper.cache_catalog_path(self.cache_dir)
        lock_path = catalog_helper.catalog_lock_path(target_path)
        lock_path.write_text("foreign lock\n", encoding="utf-8")
        with self.assertRaises(catalog_helper.CatalogError):
            self.refresh()
        with self.assertRaises(catalog_helper.CatalogError):
            catalog_helper.refresh_catalog(
                target_path=target_path,
                base_catalog_path=catalog_helper.BUNDLED_CATALOG_PATH,
                api_base_url=self.remote.api_base_url,
                timeout=2.0,
            )
        self.assertEqual(previous, self.cache_bytes())
        lock_path.unlink()

        changed_files = remote_files([self.alpha], {"alpha": " changed"})
        self.remote.add_revision("a" * 40, changed_files)
        with self.assertRaises(OSError):
            self.refresh(before_replace=lambda: (_ for _ in ()).throw(OSError("interrupted")))
        self.assertEqual(previous, self.cache_bytes())

        current = catalog_helper.read_catalog(catalog_helper.cache_catalog_path(self.cache_dir))
        reformatted_editor_copy = (
            json.dumps(current, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")
            + b"\n"
        )
        with self.assertRaises(catalog_helper.CatalogError):
            self.refresh(
                before_replace=lambda: catalog_helper.write_atomically(
                    catalog_helper.cache_catalog_path(self.cache_dir),
                    reformatted_editor_copy,
                )
            )
        self.assertEqual(reformatted_editor_copy, self.cache_bytes())


if __name__ == "__main__":
    unittest.main()
