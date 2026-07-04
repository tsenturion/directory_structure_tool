import unittest
from unittest.mock import patch

from directory_structure_tool import subprocess_utils


class FakeStartupInfo:
    def __init__(self):
        self.dwFlags = 0
        self.wShowWindow = None


class SubprocessUtilsTests(unittest.TestCase):
    def test_run_hidden_adds_windows_no_window_options(self):
        with patch.object(subprocess_utils.os, "name", "nt"), \
             patch.object(subprocess_utils.subprocess, "CREATE_NO_WINDOW", 0x08000000, create=True), \
             patch.object(subprocess_utils.subprocess, "STARTF_USESHOWWINDOW", 1, create=True), \
             patch.object(subprocess_utils.subprocess, "STARTUPINFO", FakeStartupInfo, create=True), \
             patch.object(subprocess_utils.subprocess, "run") as run:

            subprocess_utils.run_hidden(["git", "status"])

        kwargs = run.call_args.kwargs
        self.assertEqual(kwargs["creationflags"], 0x08000000)
        self.assertEqual(kwargs["startupinfo"].dwFlags, 1)
        self.assertEqual(kwargs["startupinfo"].wShowWindow, 0)

    def test_run_hidden_preserves_existing_creationflags(self):
        with patch.object(subprocess_utils.os, "name", "nt"), \
             patch.object(subprocess_utils.subprocess, "CREATE_NO_WINDOW", 0x08000000, create=True), \
             patch.object(subprocess_utils.subprocess, "STARTUPINFO", FakeStartupInfo, create=True), \
             patch.object(subprocess_utils.subprocess, "run") as run:

            subprocess_utils.run_hidden(["git", "status"], creationflags=0x2)

        self.assertEqual(run.call_args.kwargs["creationflags"], 0x08000002)


if __name__ == "__main__":
    unittest.main()
