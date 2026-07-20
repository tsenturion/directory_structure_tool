import io
import importlib.util
import os
import tempfile
import unittest
import zipfile
from unittest.mock import patch

from directory_structure_tool import copy_text_to_clipboard, generate_report_text
from directory_structure_tool.archives import normalize_archive_member_parts
from directory_structure_tool.cli import write_report
from directory_structure_tool.paths import is_subpath, sanitize_text_for_report
from directory_structure_tool.repositories import (
    clone_repository,
    get_repository_report_path,
    parse_repository_reference,
    redact_url_secrets,
    resolve_remote_reference,
    write_git_blob_to_worktree,
)
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
    def test_clipboard_copy_is_public_api(self):
        self.assertTrue(callable(copy_text_to_clipboard))

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

    def test_save_directory_structure_respects_gitignore(self):
        with tempfile.TemporaryDirectory() as root:
            os.mkdir(os.path.join(root, "ignored_dir"))
            with open(os.path.join(root, ".gitignore"), "w", encoding="utf-8") as file:
                file.write("*.log\nignored_dir/\n!important.log\n")
            with open(os.path.join(root, "debug.log"), "w", encoding="utf-8") as file:
                file.write("debug\n")
            with open(os.path.join(root, "important.log"), "w", encoding="utf-8") as file:
                file.write("important\n")
            with open(os.path.join(root, "ignored_dir", "secret.txt"), "w", encoding="utf-8") as file:
                file.write("secret\n")

            output = io.StringIO()
            save_directory_structure(root, output)
            report = output.getvalue()

            self.assertNotIn("debug.log", report)
            self.assertNotIn("[Папка] ignored_dir/", report)
            self.assertIn("important.log", report)

    def test_save_directory_structure_respects_nested_gitignore(self):
        with tempfile.TemporaryDirectory() as root:
            nested_dir = os.path.join(root, "nested")
            os.mkdir(nested_dir)
            with open(os.path.join(root, ".gitignore"), "w", encoding="utf-8") as file:
                file.write("*.tmp\n")
            with open(os.path.join(nested_dir, ".gitignore"), "w", encoding="utf-8") as file:
                file.write("!keep.tmp\n")
            with open(os.path.join(nested_dir, "drop.tmp"), "w", encoding="utf-8") as file:
                file.write("drop\n")
            with open(os.path.join(nested_dir, "keep.tmp"), "w", encoding="utf-8") as file:
                file.write("keep\n")

            output = io.StringIO()
            save_directory_structure(root, output)
            report = output.getvalue()

            self.assertNotIn("drop.tmp", report)
            self.assertIn("keep.tmp", report)

    def test_save_directory_structure_uses_gitignore_above_selected_subfolder(self):
        with tempfile.TemporaryDirectory() as root:
            os.mkdir(os.path.join(root, ".git"))
            nested_dir = os.path.join(root, "nested")
            os.mkdir(nested_dir)
            with open(os.path.join(root, ".gitignore"), "w", encoding="utf-8") as file:
                file.write("*.tmp\n")
            with open(os.path.join(nested_dir, "ignored.tmp"), "w", encoding="utf-8") as file:
                file.write("ignored\n")
            with open(os.path.join(nested_dir, "included.txt"), "w", encoding="utf-8") as file:
                file.write("included\n")

            output = io.StringIO()
            save_directory_structure(nested_dir, output)
            report = output.getvalue()

            self.assertNotIn("ignored.tmp", report)
            self.assertIn("included.txt", report)

    def test_save_directory_structure_can_disable_gitignore(self):
        with tempfile.TemporaryDirectory() as root:
            with open(os.path.join(root, ".gitignore"), "w", encoding="utf-8") as file:
                file.write("ignored.txt\n")
            with open(os.path.join(root, "ignored.txt"), "w", encoding="utf-8") as file:
                file.write("visible when disabled\n")

            output = io.StringIO()
            with patch("directory_structure_tool.report.RESPECT_GITIGNORE", False):
                save_directory_structure(root, output)

            self.assertIn("ignored.txt", output.getvalue())

    def test_generate_report_text_supports_single_file(self):
        with tempfile.TemporaryDirectory() as root:
            file_path = os.path.join(root, "main.go")
            with open(file_path, "w", encoding="utf-8") as file:
                file.write("package main\n")

            report = generate_report_text(file_path)

            self.assertIn("- main.go", report)
            self.assertIn("package main", report)

    def test_generate_report_text_has_no_metadata_header(self):
        with tempfile.TemporaryDirectory() as root:
            file_path = os.path.join(root, "main.py")
            with open(file_path, "w", encoding="utf-8") as file:
                file.write("print('ok')\n")

            report = generate_report_text(root)

            self.assertTrue(report.startswith("- main.py\n"))
            self.assertNotIn("Структура папки:", report)
            self.assertNotIn("Режим:", report)
            self.assertNotIn("Без содержимого файлов для папок:", report)

    def test_write_report_has_no_metadata_header(self):
        with tempfile.TemporaryDirectory() as root:
            file_path = os.path.join(root, "main.py")
            output_path = os.path.join(root, "report.txt")
            with open(file_path, "w", encoding="utf-8") as file:
                file.write("print('ok')\n")

            write_report(root, output_path, [], False)

            with open(output_path, "r", encoding="utf-8") as file:
                report = file.read()

            self.assertTrue(report.startswith("- main.py\n"))
            self.assertNotIn("Структура папки:", report)
            self.assertNotIn("Режим:", report)
            self.assertNotIn("Без содержимого файлов для папок:", report)

    def test_generate_report_text_supports_zip_archive(self):
        with tempfile.TemporaryDirectory() as root:
            archive_path = os.path.join(root, "work.zip")
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("project/main.go", "package main\n")

            report = generate_report_text(archive_path)

            self.assertIn("- main.go", report)
            self.assertIn("package main", report)

    @unittest.skipUnless(importlib.util.find_spec("py7zr"), "py7zr не установлен")
    def test_generate_report_text_supports_7z_archive(self):
        import py7zr

        with tempfile.TemporaryDirectory() as root:
            source_dir = os.path.join(root, "project")
            os.makedirs(source_dir)
            source_file = os.path.join(source_dir, "main.go")
            with open(source_file, "w", encoding="utf-8") as file:
                file.write("package main\n")

            archive_path = os.path.join(root, "work.7z")
            with py7zr.SevenZipFile(archive_path, "w") as archive:
                archive.write(source_file, arcname="project/main.go")

            report = generate_report_text(archive_path)

            self.assertIn("- main.go", report)
            self.assertIn("package main", report)


class RepositoryTests(unittest.TestCase):
    def test_write_git_blob_normalizes_trailing_space_without_losing_content(self):
        with tempfile.TemporaryDirectory() as root:
            content = b"class MockLLMClient:\n    pass\n"
            write_git_blob_to_worktree(root, "llm/mock_client.py ", content)

            extracted_path = os.path.join(root, "llm", "mock_client.py")
            with open(extracted_path, "rb") as extracted:
                self.assertEqual(extracted.read(), content)

    def test_write_git_blob_overwrites_normalized_name_collision(self):
        with tempfile.TemporaryDirectory() as root:
            write_git_blob_to_worktree(root, "mock_client.py", b"normal\n")
            write_git_blob_to_worktree(root, "mock_client.py ", b"trailing-space\n")

            self.assertEqual(os.listdir(root), ["mock_client.py"])
            with open(os.path.join(root, "mock_client.py"), "rb") as extracted:
                self.assertEqual(extracted.read(), b"trailing-space\n")

    def test_parse_github_repository_url(self):
        reference = parse_repository_reference("https://github.com/octocat/Hello-World")

        self.assertEqual(reference.provider, "GitHub")
        self.assertEqual(reference.clone_url, "https://github.com/octocat/Hello-World.git")
        self.assertEqual(reference.display_name, "Hello-World")
        self.assertEqual(reference.ref, "")
        self.assertEqual(reference.subpath, "")

    def test_parse_github_repository_subfolder_url(self):
        reference = parse_repository_reference("https://github.com/AlexanderV823/Go/tree/main/GoPro/hw_1")

        self.assertEqual(reference.provider, "GitHub")
        self.assertEqual(reference.clone_url, "https://github.com/AlexanderV823/Go.git")
        self.assertEqual(reference.display_name, "Go")
        self.assertEqual(reference.ref, "main")
        self.assertEqual(reference.subpath, "GoPro/hw_1")
        self.assertEqual(reference.subpath_kind, "directory")

    def test_resolve_remote_reference_uses_longest_branch_with_slash(self):
        reference = parse_repository_reference(
            "https://github.com/Dominnik/pipeline_final/tree/feature/llm-summary-service"
        )
        remote_heads = "\n".join([
            "dc767acd\trefs/heads/backup/main-complete",
            "792ec475\trefs/heads/feature/llm-summary-service",
            "e0ac69ed\trefs/heads/main",
        ])

        with patch("directory_structure_tool.repositories.run_git", return_value=remote_heads):
            resolved = resolve_remote_reference(reference)

        self.assertEqual(resolved.ref, "feature/llm-summary-service")
        self.assertEqual(resolved.subpath, "")

    def test_resolve_remote_reference_keeps_folder_after_simple_branch(self):
        reference = parse_repository_reference(
            "https://github.com/octocat/Hello-World/tree/main/homework"
        )

        with patch(
            "directory_structure_tool.repositories.run_git",
            return_value="e0ac69ed\trefs/heads/main",
        ):
            resolved = resolve_remote_reference(reference)

        self.assertEqual(resolved.ref, "main")
        self.assertEqual(resolved.subpath, "homework")

    def test_parse_github_repository_file_url(self):
        reference = parse_repository_reference("https://github.com/octocat/Hello-World/blob/main/main.go")

        self.assertEqual(reference.provider, "GitHub")
        self.assertEqual(reference.clone_url, "https://github.com/octocat/Hello-World.git")
        self.assertEqual(reference.display_name, "Hello-World")
        self.assertEqual(reference.ref, "main")
        self.assertEqual(reference.subpath, "main.go")
        self.assertEqual(reference.subpath_kind, "file")

    def test_parse_gitlab_nested_repository_url(self):
        reference = parse_repository_reference("https://gitlab.com/group/subgroup/project/-/tree/main")

        self.assertEqual(reference.provider, "GitLab")
        self.assertEqual(reference.clone_url, "https://gitlab.com/group/subgroup/project.git")
        self.assertEqual(reference.display_name, "project")
        self.assertEqual(reference.ref, "main")
        self.assertEqual(reference.subpath, "")

    def test_repository_report_path_uses_subfolder(self):
        reference = parse_repository_reference("https://github.com/AlexanderV823/Go/tree/main/GoPro/hw_1")
        with tempfile.TemporaryDirectory() as root:
            target_dir = os.path.join(root, "repo")
            report_dir = os.path.join(target_dir, "GoPro", "hw_1")
            os.makedirs(report_dir)

            self.assertEqual(get_repository_report_path(reference, target_dir), report_dir)

    def test_repository_report_path_uses_file_parent(self):
        reference = parse_repository_reference("https://github.com/octocat/Hello-World/blob/main/cmd/main.go")
        with tempfile.TemporaryDirectory() as root:
            target_dir = os.path.join(root, "repo")
            report_dir = os.path.join(target_dir, "cmd")
            os.makedirs(report_dir)
            with open(os.path.join(report_dir, "main.go"), "w", encoding="utf-8") as file:
                file.write("package main\n")

            self.assertEqual(get_repository_report_path(reference, target_dir), report_dir)

    def test_clone_repository_uses_non_cone_sparse_checkout_for_file(self):
        reference = parse_repository_reference("https://github.com/octocat/Hello-World/blob/main/main.go")

        with patch("directory_structure_tool.repositories.run_git") as run_git_mock:
            clone_repository(reference, "repo")

        commands = [call.args[0] for call in run_git_mock.call_args_list]
        self.assertIn(["sparse-checkout", "set", "--no-cone", "--", "main.go"], commands)

    def test_clone_repository_recovers_from_windows_invalid_path(self):
        reference = parse_repository_reference("https://github.com/example/project.git")
        with tempfile.TemporaryDirectory() as root:
            target_dir = os.path.join(root, "repo")

            def fail_checkout(*args, **kwargs):
                os.makedirs(os.path.join(target_dir, ".git"))
                raise RuntimeError("error: invalid path 'llm/mock_client.py '")

            with (
                patch("directory_structure_tool.repositories.run_git", side_effect=fail_checkout),
                patch("directory_structure_tool.repositories.materialize_repository_without_checkout") as materialize,
            ):
                clone_repository(reference, target_dir)

            materialize.assert_called_once_with(reference, target_dir)

    def test_parse_gitflic_repository_url(self):
        reference = parse_repository_reference("https://gitflic.ru/project/dbi471/git-switch")

        self.assertEqual(reference.provider, "GitFlic")
        self.assertEqual(reference.clone_url, "https://gitflic.ru/project/dbi471/git-switch.git")
        self.assertEqual(reference.display_name, "git-switch")

    def test_parse_gitverse_repository_url(self):
        reference = parse_repository_reference("https://gitverse.ru/owner/project")

        self.assertEqual(reference.provider, "GitVerse")
        self.assertEqual(reference.clone_url, "https://gitverse.ru/owner/project.git")
        self.assertEqual(reference.display_name, "project")

    def test_parse_sourcecraft_repository_url(self):
        reference = parse_repository_reference("https://sourcecraft.dev/examples/self-hosted-worker")

        self.assertEqual(reference.provider, "SourceCraft")
        self.assertEqual(reference.clone_url, "https://git@git.sourcecraft.dev/examples/self-hosted-worker.git")
        self.assertEqual(reference.display_name, "self-hosted-worker")

    def test_parse_scp_like_repository_url(self):
        reference = parse_repository_reference("git@github.com:octocat/Hello-World.git")

        self.assertEqual(reference.provider, "GitHub")
        self.assertEqual(reference.clone_url, "git@github.com:octocat/Hello-World.git")
        self.assertEqual(reference.display_name, "Hello-World")

    def test_parse_ssh_repository_url(self):
        reference = parse_repository_reference("ssh://git@gitlab.com/group/project.git")

        self.assertEqual(reference.provider, "GitLab")
        self.assertEqual(reference.clone_url, "ssh://git@gitlab.com/group/project.git")
        self.assertEqual(reference.display_name, "project")

    def test_redact_url_secrets(self):
        self.assertEqual(
            redact_url_secrets("fatal: https://token@example.com/repo.git failed"),
            "fatal: https://***@example.com/repo.git failed",
        )


if __name__ == "__main__":
    unittest.main()
