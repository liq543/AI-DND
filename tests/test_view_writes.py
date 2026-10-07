"""Regenerated views (state.md, sheets, the current map) must never crash a command when a reader holds the file."""
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from engine import views


class ViewWritesSurviveLockedFiles(unittest.TestCase):
    def test_a_locked_view_is_skipped_not_raised(self):
        with tempfile.TemporaryDirectory() as d:
            target = Path(d) / "current-map.svg"
            target.write_text("old", encoding="utf-8")
            with mock.patch("os.replace", side_effect=PermissionError("in use")), mock.patch("time.sleep"):
                self.assertFalse(views.write_view_file(target, "new"))
            self.assertEqual(target.read_text(encoding="utf-8"), "old")
            self.assertFalse((Path(d) / "current-map.svg.tmp").exists())

    def test_a_free_view_is_replaced(self):
        with tempfile.TemporaryDirectory() as d:
            target = Path(d) / "state.md"
            self.assertTrue(views.write_view_file(target, "fresh"))
            self.assertEqual(target.read_text(encoding="utf-8"), "fresh")


if __name__ == "__main__":
    unittest.main()
