import io
import os
import tempfile
import unittest

from directory_structure_tool.archives import normalize_archive_member_parts
from directory_structure_tool.paths import is_subpath, sanitize_text_for_report
from directory_structure_tool.report import save_directory_structure


class PathTests(unittest.TestCase):
    def test_is_subpath_accepts_child_path(self):
        with tempfile.TemporaryDirectory() as root:
            child = os.path.join(root, "child")
            os.mkdir(child)

            self.assertTrue(is_subpath(child, root))

    def test_is_subpath_rejects_sibling_path(self):
        with tempfile.TemporaryDirectory() as parent:
            with tempfile.TemporaryDirectory() as sibling:
                self.assertFalse(is_subpath(sibling, parent))


class TextTests(unittest.TestCase):
    def test_sanitize_text_for_report_removes_control_chars(self):
        self.assertEqual(
            sanitize_text_for_report("a\x00b\x08\n\tc"),
            "ab\n\tc",
        )


class ArchivePathTests(unittest.TestCase):
    def test_normalize_archive_member_parts_rejects_unsafe_paths(self):
        self.assertIsNone(normalize_archive_member_parts("../secret.txt"))
        self.assertIsNone(normalize_archive_member_parts("C:/secret.txt"))
        self.assertIsNone(normalize_archive_member_parts("safe/\x00bad.txt"))

    def test_normalize_archive_member_parts_accepts_safe_paths(self):
        self.assertEqual(
            normalize_archive_member_parts("root\\folder/file.txt"),
            ["root", "folder", "file.txt"],
        )


class ReportTests(unittest.TestCase):
    def test_save_directory_structure_ignores_configured_names(self):
        with tempfile.TemporaryDirectory() as root:
            os.mkdir(os.path.join(root, ".git"))
            os.mkdir(os.path.join(root, "src"))
            with open(os.path.join(root, "package-lock.json"), "w", encoding="utf-8") as file:
                file.write("{}")
            with open(os.path.join(root, "src", "main.py"), "w", encoding="utf-8") as file:
                file.write("print('ok')\n")

            output = io.StringIO()
            save_directory_structure(root, output)
            report = output.getvalue()

            self.assertIn("[Папка] src/", report)
            self.assertIn("- main.py", report)
            self.assertNotIn(".git", report)
            self.assertNotIn("package-lock.json", report)


class CompatibilityTests(unittest.TestCase):
    def test_legacy_script_reexports_core_functions(self):
        import directory_structure

        self.assertIs(directory_structure.save_directory_structure, save_directory_structure)
        self.assertIs(directory_structure.normalize_archive_member_parts, normalize_archive_member_parts)


if __name__ == "__main__":
    unittest.main()
