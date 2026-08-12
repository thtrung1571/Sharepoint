"""Tests for pure SharePoint path helpers (no browser required)."""

import os
import sys
import unittest
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services import sharepoint


SAMPLE_ROOT = (
    "%2Fpersonal%2Fnle%5Falltech%5Fcom%2FDocuments%2FNgoc%20Nga%20Documents%20%2D%20PDMM"
    "%2FPDMM%2F3%2E%20DOMESTIC%2FDOMESTIC%2FDomestic%20%2D2026%2FVI%E1%BB%86T%20%C3%82U"
)

SAMPLE_URL_AT_05 = (
    "https://alltech-my.sharepoint.com/personal/nle_alltech_com/_layouts/15/onedrive.aspx"
    f"?id={SAMPLE_ROOT}%2F05"
    "&viewid=d1d7e269%2D4e2a%2D4684%2D9d90%2D1abf7848ac9d"
    "&sharingv2=true&fromShare=true&at=9"
    "&CID=3d134348%2Da0e4%2D4f09%2Db0b1%2D576c4052d34e"
    "&FolderCTID=0x012000357D47895F012E4FA6DB93BD359D1324&view=0"
)


def _query_id(url: str) -> str:
    return urllib.parse.parse_qs(urllib.parse.urlparse(url).query)["id"][0]


class BuildLibraryIdTest(unittest.TestCase):
    def test_root_only(self):
        built = sharepoint.build_library_id([], base_id=SAMPLE_ROOT)
        self.assertEqual(urllib.parse.unquote(built), urllib.parse.unquote(SAMPLE_ROOT))

    def test_single_segment_not_double_encoded(self):
        built = sharepoint.build_library_id(["05"], base_id=SAMPLE_ROOT)
        self.assertNotIn("%252F", built)
        self.assertTrue(urllib.parse.unquote(built).endswith("/05"))
        self.assertEqual(urllib.parse.unquote(built).count("/05"), 1)

    def test_nested_path(self):
        built = sharepoint.build_library_id(
            ["05", "EXPORT", "PDMM 111-2026 Done"], base_id=SAMPLE_ROOT
        )
        decoded = urllib.parse.unquote(built)
        self.assertTrue(decoded.endswith("/05/EXPORT/PDMM 111-2026 Done"))
        self.assertNotIn("%252F", built)

    def test_refresh_idempotent(self):
        first = sharepoint.build_library_id(["05"], base_id=SAMPLE_ROOT)
        second = sharepoint.build_library_id(["05"], base_id=SAMPLE_ROOT)
        self.assertEqual(first, second)


class LibraryRootFromIdTest(unittest.TestCase):
    def test_strips_current_path_suffix(self):
        current_id = SAMPLE_ROOT + "%2F05"
        root = sharepoint.library_root_from_id(current_id, ["05"])
        self.assertEqual(urllib.parse.unquote(root), urllib.parse.unquote(SAMPLE_ROOT))

    def test_nested_suffix(self):
        current_id = SAMPLE_ROOT + "%2F05%2FEXPORT"
        root = sharepoint.library_root_from_id(current_id, ["05", "EXPORT"])
        self.assertEqual(urllib.parse.unquote(root), urllib.parse.unquote(SAMPLE_ROOT))


class BuildOneDriveUrlTest(unittest.TestCase):
    def test_refresh_at_05_keeps_single_encoding(self):
        new_url = sharepoint.build_onedrive_url(SAMPLE_URL_AT_05, ["05"])
        raw_query = urllib.parse.urlparse(new_url).query
        self.assertNotIn("%252F", raw_query)
        self.assertNotIn("%2520", raw_query)
        decoded_id = _query_id(new_url)
        self.assertTrue(decoded_id.endswith("/05"))
        self.assertEqual(decoded_id.count("/05"), 1)
        self.assertEqual(
            decoded_id[: -len("/05")],
            urllib.parse.unquote(SAMPLE_ROOT),
        )

    def test_refresh_does_not_duplicate_root_or_segment(self):
        new_url = sharepoint.build_onedrive_url(SAMPLE_URL_AT_05, ["05"])
        decoded_id = _query_id(new_url)
        self.assertEqual(decoded_id.count("/05"), 1)
        self.assertFalse(decoded_id.endswith("/05/05"))
        # Root folder name must not be duplicated before /05
        root = urllib.parse.unquote(SAMPLE_ROOT)
        leaf = root.rsplit("/", 1)[-1]
        self.assertEqual(decoded_id.count("/" + leaf + "/"), 1)

    def test_root_refresh(self):
        root_url = SAMPLE_URL_AT_05.replace("%2F05", "")
        new_url = sharepoint.build_onedrive_url(root_url, [])
        self.assertNotIn("%252F", new_url)
        self.assertEqual(_query_id(new_url), urllib.parse.unquote(SAMPLE_ROOT))

    def test_user_reported_refresh_url(self):
        """Exact current URL from the bug report must refresh cleanly."""
        current = (
            "https://alltech-my.sharepoint.com/personal/nle_alltech_com/"
            "_layouts/15/onedrive.aspx?"
            "id=%2Fpersonal%2Fnle%5Falltech%5Fcom%2FDocuments%2FNgoc%20Nga%20Documents"
            "%20%2D%20PDMM%2FPDMM%2F3%2E%20DOMESTIC%2FDOMESTIC%2FDomestic%20%2D2026"
            "%2FVI%E1%BB%86T%20%C3%82U%2F05"
            "&viewid=d1d7e269%2D4e2a%2D4684%2D9d90%2D1abf7848ac9d"
            "&sharingv2=true&fromShare=true&at=9"
            "&CID=3d134348%2Da0e4%2D4f09%2Db0b1%2D576c4052d34e"
            "&FolderCTID=0x012000357D47895F012E4FA6DB93BD359D1324&view=0"
        )
        new_url = sharepoint.build_onedrive_url(current, ["05"])
        self.assertNotIn("%252F", new_url)
        decoded = _query_id(new_url)
        self.assertTrue(decoded.endswith("/05"))
        self.assertEqual(decoded.count("/05"), 1)
        self.assertNotIn("VI?T ?U/VI?T ?U", decoded)


if __name__ == "__main__":
    unittest.main()
