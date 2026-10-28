import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from student_manager.exceptions import DataExportError, DataImportError
from student_manager.reliable_io import atomic_text_writer, read_csv_rows


class ReliableBoundaryTests(unittest.TestCase):
    def test_cleanup_failure_is_logged_without_masking_original_error(self):
        with tempfile.TemporaryDirectory() as folder:
            destination = Path(folder) / "out.json"
            with (
                patch(
                    "student_manager.reliable_io.Path.unlink",
                    side_effect=PermissionError("cleanup denied"),
                ),
                self.assertLogs("student_manager", level="ERROR"),
                self.assertRaisesRegex(ValueError, "original failure"),
                atomic_text_writer(destination),
            ):
                raise ValueError("original failure")

    def test_replace_failure_cleans_temp_and_preserves_destination(self):
        with tempfile.TemporaryDirectory() as folder:
            destination = Path(folder) / "out.json"
            destination.write_text("old", encoding="utf-8")
            with (
                patch(
                    "student_manager.reliable_io.os.replace",
                    side_effect=PermissionError("denied"),
                ),
                self.assertRaises(DataExportError),
                atomic_text_writer(destination) as stream,
            ):
                stream.write("new")
            self.assertEqual(destination.read_text(encoding="utf-8"), "old")
            self.assertEqual(list(Path(folder).glob("*.tmp")), [])

    def test_unterminated_csv_quote_is_import_error(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "input.csv"
            path.write_text(
                'student_id,first_name,last_name,group,average_grade\n1,"Anna,Koval,A,90\n',
                encoding="utf-8",
            )
            with self.assertRaises(DataImportError):
                list(read_csv_rows(path))
