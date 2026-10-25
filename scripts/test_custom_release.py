"""Pure selection/parser tests; never connect to GitHub or publish anything."""

import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import custom_release as release


def upstream(number, day=None, **changes):
    item = {"id": number, "tag_name": f"v{number}", "draft": False, "prerelease": False,
            "published_at": f"2026-10-{day or number:02d}T00:00:00Z"}
    item.update(changes)
    return item


def completed(number, **changes):
    item = {"id": 1000 + number, "tag_name": f"custom-upstream-{number}", "draft": False,
            "assets": [{"name": f"PiliPlus_custom_upstream_{number}_unsigned.hap",
                        "state": "uploaded", "size": 100}]}
    item.update(changes)
    return item


RECIPE = """
jobs:
  release_ohos:
    steps:
      - name: Setup HarmonyOS toolchain
        uses: ErBWs/setup-ohos@v1
        with:
          version: "26.0.0.821"
          cache: true
      - name: Setup JDK17
        uses: actions/setup-java@v4
        with:
          java-version: "17"
          distribution: "temurin"
      - name: Setup flutter-ohos
        run: |
          git clone -b oh-3.44.9-dev https://gitcode.com/CPF-Flutter/flutter_flutter.git $GITHUB_WORKSPACE/flutter
          echo "$GITHUB_WORKSPACE/flutter/bin" >> "$GITHUB_PATH"
      - name: Build
        run: flutter build hap --release --dart-define-from-file=.vscode/env.json
"""
PROFILE = '{targetSdkVersion: "26.0.0"}'


class SelectionTests(unittest.TestCase):
    def ids(self, upstream_releases, custom_releases, tag=""):
        return [item["id"] for item in release.select_releases(upstream_releases, custom_releases, tag)]

    def test_bootstrap_latest_stable_only(self):
        self.assertEqual(self.ids([upstream(1), upstream(2), upstream(3, prerelease=True),
                                   upstream(4, draft=True)], []), [2])

    def test_fill_all_new_releases_in_order_and_retry_failure(self):
        # v3 failed while v4 succeeded; v3 remains eligible on the next schedule.
        self.assertEqual(self.ids([upstream(5), upstream(3), upstream(1), upstream(2), upstream(4)],
                                  [completed(2), completed(4)]), [3, 5])

    def test_artifact_or_draft_is_not_success(self):
        self.assertEqual(self.ids([upstream(1), upstream(2), upstream(3)],
                                  [completed(1), completed(2, draft=True), completed(3, assets=[])]), [2, 3])

    def test_zero_byte_and_incomplete_assets_are_not_success(self):
        item = completed(2)
        item["assets"][0]["size"] = 0
        self.assertEqual(release.success_ids([item]), set())
        item["assets"][0].update(size=1, state="new")
        self.assertEqual(release.success_ids([item]), set())

    def test_manual_tag_can_rebuild_completed_release(self):
        self.assertEqual(self.ids([upstream(1), upstream(2)], [completed(2)], "v2"), [2])

    def test_manual_tag_does_not_allow_prerelease(self):
        with self.assertRaises(RuntimeError):
            self.ids([upstream(1), upstream(2, prerelease=True)], [], "v2")

    def test_no_new_releases(self):
        self.assertEqual(self.ids([upstream(1), upstream(2)], [completed(2)]), [])

    def test_missing_upstream_history_requires_explicit_choice(self):
        with self.assertRaises(RuntimeError):
            self.ids([upstream(3)], [completed(2)])

    def test_same_publish_time_uses_id_tiebreaker(self):
        self.assertEqual(self.ids([upstream(2, day=1), upstream(1, day=1)], [completed(1)]), [2])

    def test_record_tag_requires_exact_numeric_shape(self):
        self.assertEqual(release.success_ids([completed(1, tag_name="custom-upstream-1/../../other")]), set())


class ParserTests(unittest.TestCase):
    def test_extract_current_recipe(self):
        settings = release.extract_toolchain(RECIPE, PROFILE)
        self.assertEqual(settings["ohos_version"], "26.0.0.821")
        self.assertEqual(settings["java_version"], "17")
        self.assertEqual(settings["flutter_ref"], "oh-3.44.9-dev")

    def test_extract_new_version_from_each_release(self):
        changed = RECIPE.replace("26.0.0.821", "27.0.0.100").replace("oh-3.44.9-dev", "oh-3.48.2-dev")
        settings = release.extract_toolchain(changed, PROFILE.replace("26.0.0", "27.0.0"))
        self.assertEqual(settings["ohos_version"], "27.0.0.100")
        self.assertEqual(settings["flutter_ref"], "oh-3.48.2-dev")

    def test_refuses_changed_sdk_contract(self):
        with self.assertRaises(RuntimeError):
            release.extract_toolchain(RECIPE, PROFILE.replace("26.0.0", "27.0.0"))

    def test_refuses_unrecognized_clone_and_command_injection(self):
        for wrong in ["https://example.com/flutter.git", "$(touch /tmp/not-run)"]:
            with self.subTest(wrong=wrong), self.assertRaises(RuntimeError):
                release.extract_toolchain(RECIPE.replace(release.FLUTTER_REPO, wrong), PROFILE)

    def test_refuses_extra_build_flags(self):
        changed = RECIPE.replace(".vscode/env.json", ".vscode/env.json --flavor other")
        with self.assertRaises(RuntimeError):
            release.extract_toolchain(changed, PROFILE)

    def test_refuses_ambiguous_or_dynamic_sdk_version(self):
        with self.assertRaises(RuntimeError):
            release.extract_toolchain(RECIPE.replace('version: "26.0.0.821"', 'version: ${{ env.SDK }}'), PROFILE)
        with self.assertRaises(RuntimeError):
            release.extract_toolchain(RECIPE + RECIPE, PROFILE)


class PaginationTests(unittest.TestCase):
    @patch.object(release, "api")
    def test_reads_beyond_first_page(self, mock_api):
        mock_api.side_effect = [[{"id": n} for n in range(100)], [{"id": 100}]]
        self.assertEqual(len(release.pages("/repos/owner/repo/releases")), 101)
        self.assertEqual(mock_api.call_args_list[1].args[0], "/repos/owner/repo/releases?per_page=100&page=2")

    @patch.object(release, "api")
    def test_exact_page_size_fetches_final_empty_page(self, mock_api):
        mock_api.side_effect = [[{}] * 100, []]
        self.assertEqual(len(release.pages("/x?existing=1")), 100)
        self.assertEqual(mock_api.call_args_list[1].args[0], "/x?existing=1&per_page=100&page=2")


class PublishTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.output = Path(self.temp.name)
        self.state = {"upstream_release_id": 42, "upstream_url": "https://github.com/dev4harmony/PiliPlus/releases/tag/v42",
                      "upstream_tag": "v42", "upstream_commit": "a" * 40,
                      "patch_set_sha256": "b" * 64, "kit_commit": "c" * 40,
                      "hap_sha256": "d" * 64, "hap_filename": "PiliPlus_custom_upstream_42_unsigned.hap",
                      "source_filename": "PiliPlus_custom_upstream_42_source.tar.gz"}
        for name in [self.state["hap_filename"], self.state["source_filename"], "build-provenance.json"]:
            (self.output / name).write_bytes(b"data")
        self.draft = {"id": 900, "tag_name": "custom-upstream-42", "draft": True,
                      "upload_url": "https://uploads.github.com/repos/me/custom/releases/900/assets{?name,label}"}
        self.published = {**self.draft, "draft": False, "html_url": "https://github.com/me/custom/releases/tag/custom-upstream-42"}
        for patcher in [patch.object(release, "OUTPUT", self.output),
                        patch.object(release, "load_state", return_value=self.state),
                        patch.dict(os.environ, {"GITHUB_REPOSITORY": "me/custom"})]:
            patcher.start()
            self.addCleanup(patcher.stop)

    @patch.object(release, "pages", side_effect=[[], []])
    @patch.object(release, "api")
    def test_publish_success_marker_only_after_all_uploads(self, mock_api, _pages):
        uploaded = {"state": "uploaded", "size": 4}
        mock_api.side_effect = [self.draft, uploaded, uploaded, uploaded, self.published]
        release.publish()
        calls = mock_api.call_args_list
        self.assertTrue(calls[0].kwargs["data"]["draft"])
        self.assertFalse(calls[-1].kwargs["data"]["draft"])
        self.assertTrue(all("raw" in call.kwargs for call in calls[1:-1]))

    @patch.object(release, "pages", side_effect=[[], []])
    @patch.object(release, "api")
    def test_failed_upload_leaves_draft_without_success_mutation(self, mock_api, _pages):
        mock_api.side_effect = [self.draft, {"state": "uploaded", "size": 4}, OSError("connection lost")]
        with self.assertRaises(OSError):
            release.publish()
        self.assertFalse(any(call.kwargs.get("data", {}).get("draft") is False
                             for call in mock_api.call_args_list))

    @patch.object(release, "pages")
    @patch.object(release, "api")
    def test_retry_reuses_draft_and_replaces_only_known_assets(self, mock_api, mock_pages):
        mock_pages.side_effect = [[self.draft], [
            {"id": 1, "name": self.state["hap_filename"]}, {"id": 2, "name": "user-notes.txt"}]]
        uploaded = {"state": "uploaded", "size": 4}
        mock_api.side_effect = [self.draft, None, uploaded, uploaded, uploaded, self.published]
        release.publish()
        deleted = [call.args[0] for call in mock_api.call_args_list if call.args[1] == "DELETE"]
        self.assertEqual(deleted, ["/repos/me/custom/releases/assets/1"])
        self.assertEqual(mock_api.call_args_list[0].args[1], "PATCH")


if __name__ == "__main__":
    unittest.main()
